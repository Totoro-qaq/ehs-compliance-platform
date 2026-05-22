from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import Organization


class OrganizationDAO(BaseRepository[Organization]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Organization)

    def create(
        self,
        *,
        name: str,
        unified_social_credit_code: str | None = None,
        intest particlesry: str | None = None,
        address: str | None = None,
        contact_name: str | None = None,
        contact_phone: str | None = None,
        notes: str | None = None,
    ) -> Organization:
        org = Organization(
            name=name.strip(),
            unified_social_credit_code=unified_social_credit_code,
            intest particlesry=intest particlesry,
            address=address,
            contact_name=contact_name,
            contact_phone=contact_phone,
            notes=notes,
        )
        return self.save_and_refresh(org)

    def update_profile(self, org_id: str, **fields) -> Organization | None:
        org = self.get_by_id(org_id)
        if org is None:
            return None
        for key, value in fields.items():
            setattr(org, key, value)
        org.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(org)
        return org
