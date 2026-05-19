from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.dao.assessment_dao import AssessmentDAO
from app.dao.organization_dao import OrganizationDAO
from app.models.db_models import AssessmentTask
from app.schemas.admin_schema import (
    AssessmentTaskAdminOut,
    DefaultOrganizationMeta,
    OrganizationAdminOut,
)
from app.schemas.pagination import Page


class AdminService:
    @staticmethod
    def get_default_organization_meta(*, db: Session) -> DefaultOrganizationMeta:
        oid = settings.default_organization_id
        org = OrganizationDAO(db).get_by_id_include_deleted(oid)
        if org is None:
            return DefaultOrganizationMeta(
                default_organization_id=oid,
                exists_in_db=False,
                deleted_at=None,
                name=None,
            )
        return DefaultOrganizationMeta(
            default_organization_id=oid,
            exists_in_db=True,
            deleted_at=org.deleted_at,
            name=org.name,
        )

    @staticmethod
    def list_organizations(
        *, db: Session, page: int, page_size: int, include_deleted: bool
    ) -> Page[OrganizationAdminOut]:
        dao = OrganizationDAO(db)
        items, total = dao.list_page(page=page, page_size=page_size, include_deleted=include_deleted)
        return Page[OrganizationAdminOut](
            items=[OrganizationAdminOut.model_validate(x) for x in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def list_assessment_tasks(
        *,
        db: Session,
        page: int,
        page_size: int,
        include_deleted: bool,
        organization_id: str | None,
    ) -> Page[AssessmentTaskAdminOut]:
        dao = AssessmentDAO(db)
        filters: tuple = ()
        if organization_id:
            filters = (AssessmentTask.organization_id == organization_id,)
        items, total = dao.list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            include_deleted=include_deleted,
        )
        return Page[AssessmentTaskAdminOut](
            items=[AssessmentTaskAdminOut.model_validate(x) for x in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def restore_organization(*, db: Session, org_id: str) -> None:
        if not OrganizationDAO(db).restore_soft_deleted(org_id):
            raise EHSException('公司不存在', code='ORG_NOT_FOUND', status_code=404)

    @staticmethod
    def restore_assessment_task(*, db: Session, task_id: str) -> None:
        if not AssessmentDAO(db).restore_soft_deleted(task_id):
            raise EHSException('任务不存在', code='TASK_NOT_FOUND', status_code=404)
