from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.db_models import Organization


class OrganizationDAO(BaseRepository[Organization]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Organization)

    def create(self, *, name: str) -> Organization:
        org = Organization(name=name.strip())
        return self.save_and_refresh(org)
