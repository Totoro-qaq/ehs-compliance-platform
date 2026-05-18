from __future__ import annotations

from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.core.patterns import is_uuid
from app.core.request_context import get_request_id
from app.core.upload_policy import (
    build_unique_storage_path,
    validate_file_magic,
    validate_original_filename,
)
from app.dao.assessment_dao import AssessmentDAO
from app.dao.organization_dao import OrganizationDAO
from app.models.db_models import AccountRole, AssessmentTask, TaskStatus
from app.schemas.auth_context import CurrentUser
from app.schemas.ehs_schema import AssessmentCreateResponse, AssessmentStatusResponse
from app.schemas.pagination import Page
from app.services.access_control import (
    ensure_client_org_id_allowed,
    ensure_organization_scope,
    ensure_task_author_for_mutation,
    ensure_user_has_organization,
)


class AssessmentService:
    @staticmethod
    async def create_assessment_task(
        *,
        db: Session,
        actor: CurrentUser,
        organization_id: str,
        filename: str | None,
        content_type: str,
        file_bytes: bytes,
    ) -> AssessmentCreateResponse:
        ensure_client_org_id_allowed(actor, requested_organization_id=organization_id)
        if not is_uuid(organization_id):
            raise EHSException(
                'organization_id 必须为公司主键 UUID（与 organizations.id 一致），不能填公司名称',
                code='INVALID_ORGANIZATION_ID',
                status_code=400,
                details={'hint': '从 GET /api/v1/organizations 或管理员接口取得 id 字段'},
            )
        if OrganizationDAO(db).get_by_id(organization_id) is None:
            raise EHSException('公司不存在', code='ORG_NOT_FOUND', status_code=404)

        if len(file_bytes) > settings.max_upload_bytes:
            raise EHSException(
                f'文件过大，单文件上限 {settings.max_upload_bytes // (1024 * 1024)} MB',
                code='FILE_TOO_LARGE',
                status_code=413,
            )

        upload_dir = Path(settings.upload_dir)
        file_path, display_name = build_unique_storage_path(upload_dir, filename or '')

        # 校验文件内容 magic bytes 与扩展名一致
        ext = validate_original_filename(filename or '')
        validate_file_magic(file_bytes, ext)

        file_path.write_bytes(file_bytes)

        dao = AssessmentDAO(db)
        task = dao.create_task(
            organization_id=organization_id,
            filename=display_name,
            content_type=content_type,
            file_path=str(file_path),
            created_by_id=actor.account_id,
        )

        try:
            from app.tasks.worker import run_assessment_task

            run_assessment_task.delay(task.id, get_request_id())
        except Exception as exc:
            raise EHSException(
                '异步任务投递失败，请确认 Redis 已启动且已执行 Celery Worker',
                code='TASK_ENQUEUE_FAILED',
                status_code=503,
                details={'reason': str(exc), 'exc_type': type(exc).__name__},
            ) from exc

        return AssessmentCreateResponse(task_id=task.id, status=task.status)

    @staticmethod
    def get_assessment_task(*, db: Session, actor: CurrentUser, task_id: str):
        dao = AssessmentDAO(db)
        task = dao.get_by_id(task_id)
        if task is None:
            raise EHSException('任务不存在', code='TASK_NOT_FOUND', status_code=404)
        ensure_organization_scope(actor, task.organization_id)
        return task

    @staticmethod
    def list_assessment_tasks(
        *,
        db: Session,
        actor: CurrentUser,
        organization_id: str | None,
        status: str | None,
        q: str | None,
        page: int,
        page_size: int,
    ) -> Page[AssessmentStatusResponse]:
        if organization_id and not is_uuid(organization_id):
            raise EHSException(
                'organization_id 须为有效的公司 UUID',
                code='INVALID_ORGANIZATION_ID',
                status_code=400,
            )
        if actor.role == AccountRole.ADMIN:
            oid = organization_id or settings.default_organization_id
        else:
            uid_org = ensure_user_has_organization(actor)
            if organization_id and organization_id != uid_org:
                raise EHSException(
                    '禁止查询其他公司的评价任务',
                    code='IDOR_ORG_FORGE',
                    status_code=403,
                    details={'hint': '普通用户仅能访问本 organization_id 的数据'},
            )
            oid = uid_org

        filters = [AssessmentTask.organization_id == oid]
        if status:
            try:
                parsed_status = TaskStatus(status)
            except ValueError as exc:
                raise EHSException(
                    'status 须为有效任务状态',
                    code='INVALID_TASK_STATUS',
                    status_code=400,
                    details={'allowed': [s.value for s in TaskStatus]},
                ) from exc
            filters.append(AssessmentTask.status == parsed_status)

        query = (q or '').strip()
        if query:
            like = f'%{query}%'
            filters.append(or_(AssessmentTask.filename.like(like), AssessmentTask.id == query))

        dao = AssessmentDAO(db)
        items, total = dao.list_page(
            page=page,
            page_size=page_size,
            filters=tuple(filters),
        )
        return Page[AssessmentStatusResponse](
            items=[AssessmentStatusResponse.model_validate(t) for t in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def soft_delete_task(*, db: Session, actor: CurrentUser, task_id: str) -> None:
        dao = AssessmentDAO(db)
        task = dao.get_by_id(task_id)
        if task is None:
            raise EHSException('任务不存在或已删除', code='TASK_NOT_FOUND', status_code=404)
        ensure_task_author_for_mutation(actor, task)
        dao.soft_delete_by_id(task_id)
