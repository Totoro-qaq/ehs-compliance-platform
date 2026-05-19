from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.db import get_db
from app.schemas.admin_schema import (
    AssessmentTaskAdminOut,
    DefaultOrganizationMeta,
    OrganizationAdminOut,
)
from app.schemas.auth_schema import AdminResetPasswordRequest
from app.schemas.pagination import Page
from app.services import auth_service
from app.services.admin_service import AdminService

router = APIRouter(prefix='/admin', tags=['系统管理（仅管理员）'], dependencies=[Depends(require_admin)])


@router.get(
    '/meta/default-organization',
    response_model=DefaultOrganizationMeta,
    summary='查看默认公司配置',
    description='返回系统配置的默认公司 ID 及其在数据库中的实际状态（是否存在、是否已软删除）。用于运维排查。',
)
def admin_default_organization_meta(db: Session = Depends(get_db)):
    return AdminService.get_default_organization_meta(db=db)


@router.get(
    '/organizations',
    response_model=Page[OrganizationAdminOut],
    summary='管理员查询公司列表',
    description='分页查询所有公司，支持 `include_deleted=true` 查看已软删除的记录。',
)
def admin_list_organizations(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=20, ge=1, le=200, description='每页条数'),
    include_deleted: bool = Query(default=False, description='为 true 时包含已软删公司'),
):
    return AdminService.list_organizations(
        db=db, page=page, page_size=page_size, include_deleted=include_deleted
    )


@router.post(
    '/organizations/{org_id}/restore',
    status_code=204,
    summary='恢复已删除的公司',
    description='将软删除的公司恢复为正常状态。若公司不存在或未被删除则返回错误。',
)
def admin_restore_organization(org_id: str, db: Session = Depends(get_db)):
    AdminService.restore_organization(db=db, org_id=org_id)


@router.get(
    '/assessment-tasks',
    response_model=Page[AssessmentTaskAdminOut],
    summary='管理员查询评价任务列表',
    description='跨公司分页查询评价任务，支持按公司筛选和查看已删除记录。',
)
def admin_list_assessment_tasks(
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=20, ge=1, le=200, description='每页条数'),
    include_deleted: bool = Query(default=False, description='为 true 时包含已软删任务'),
    organization_id: str | None = Query(default=None, description='按公司 ID 筛选'),
):
    return AdminService.list_assessment_tasks(
        db=db,
        page=page,
        page_size=page_size,
        include_deleted=include_deleted,
        organization_id=organization_id,
    )


@router.post(
    '/assessment-tasks/{task_id}/restore',
    status_code=204,
    summary='恢复已删除的评价任务',
    description='将软删除的评价任务恢复为正常状态。关联文件若已被清理则无法恢复。',
)
def admin_restore_assessment_task(task_id: str, db: Session = Depends(get_db)):
    AdminService.restore_assessment_task(db=db, task_id=task_id)


@router.post(
    '/reset-password',
    status_code=204,
    summary='重置用户密码',
    description=(
        '管理员为指定用户重置密码，无需提供旧密码。\n\n'
        '- 新密码须符合复杂度要求（大小写字母 + 数字，8–128 位）\n'
        '- 重置后用户现有令牌仍有效直到过期'
    ),
)
def admin_reset_password(payload: AdminResetPasswordRequest, db: Session = Depends(get_db)):
    auth_service.admin_reset_password(
        db, target_account_id=payload.account_id, new_password=payload.new_password
    )
