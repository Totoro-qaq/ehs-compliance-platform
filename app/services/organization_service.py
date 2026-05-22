from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.dao.organization_dao import OrganizationDAO
from app.models.db_models import AccountRole
from app.schemas.auth_context import CurrentUser
from app.schemas.organization_schema import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.schemas.pagination import Page
from app.services.access_control import (
    ensure_admin,
    ensure_organization_scope,
    ensure_user_has_organization,
)


class OrganizationService:
    @staticmethod
    def create(*, db: Session, actor: CurrentUser, payload: OrganizationCreate) -> OrganizationOut:
        ensure_admin(actor)
        dao = OrganizationDAO(db)
        org = dao.create(
            name=payload.name,
            unified_social_credit_code=payload.unified_social_credit_code,
            intest particlesry=payload.intest particlesry,
            address=payload.address,
            contact_name=payload.contact_name,
            contact_phone=payload.contact_phone,
            notes=payload.notes,
        )
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
    def list_page(
        *, db: Session, actor: CurrentUser, page: int, page_size: int
    ) -> Page[OrganizationOut]:
        dao = OrganizationDAO(db)
        if actor.role == AccountRole.ADMIN:
            items, total = dao.list_page(page=page, page_size=page_size)
        else:
            org_id = ensure_user_has_organization(actor)
            org = dao.get_by_id(org_id)
            if org is None:
                raise EHSException('公司不存在', code='ORG_NOT_FOUND', status_code=404)
            items = [org] if page == 1 else []
            total = 1
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
        fields = payload.model_dump(exclude_unset=True)
        if 'name' in fields and fields['name'] is not None:
            fields['name'] = fields['name'].strip()
        org = dao.update_profile(org_id, **fields) if fields else dao.get_by_id(org_id)
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
