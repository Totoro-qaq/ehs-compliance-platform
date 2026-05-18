from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.dao.organization_dao import OrganizationDAO
from app.schemas.auth_context import CurrentUser
from app.schemas.organization_schema import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.schemas.pagination import Page
from app.services.access_control import ensure_admin, ensure_organization_scope


class OrganizationService:
    @staticmethod
    def create(*, db: Session, actor: CurrentUser, payload: OrganizationCreate) -> OrganizationOut:
        ensure_admin(actor)
        dao = OrganizationDAO(db)
        org = dao.create(name=payload.name)
        return OrganizationOut.model_validate(org)

    @staticmethod
    def get(*, db: Session, actor: CurrentUser, org_id: str) -> OrganizationOut:
        ensure_organization_scope(actor, org_id)
        dao = OrganizationDAO(db)
        org = dao.get_by_id(org_id)
        if org is None:
            raise EHSException('公司不存在', code='ORG_NOT_FOUND', status_code=404)
        return OrganizationOut.model_validate(org)

    @staticmethod
    def list_page(*, db: Session, actor: CurrentUser, page: int, page_size: int) -> Page[OrganizationOut]:
        ensure_admin(actor)
        dao = OrganizationDAO(db)
        items, total = dao.list_page(page=page, page_size=page_size)
        return Page[OrganizationOut](
            items=[OrganizationOut.model_validate(x) for x in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def update(
        *, db: Session, actor: CurrentUser, org_id: str, payload: OrganizationUpdate
    ) -> OrganizationOut:
        ensure_admin(actor)
        dao = OrganizationDAO(db)
        org = dao.update_by_id(org_id, name=payload.name.strip())
        if org is None:
            raise EHSException('公司不存在', code='ORG_NOT_FOUND', status_code=404)
        return OrganizationOut.model_validate(org)

    @staticmethod
    def soft_delete(*, db: Session, actor: CurrentUser, org_id: str) -> None:
        ensure_admin(actor)
        if org_id == settings.default_organization_id:
            raise EHSException('预置默认公司不可删除', code='ORG_PROTECTED', status_code=403)
        if not OrganizationDAO(db).soft_delete_by_id(org_id):
            raise EHSException('公司不存在或已删除', code='ORG_NOT_FOUND', status_code=404)
