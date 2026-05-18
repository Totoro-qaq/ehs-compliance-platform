from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging_setup import get_logger
from app.core.security import hash_password
from app.dao.account_dao import AccountDAO
from app.models import db_models  # noqa: F401
from app.models.db_models import AccountRole, Organization

_log = get_logger(__name__)


def init_db() -> None:
    """
    预置公司与管理账号（密码仅存哈希）。表结构：alembic upgrade head
    """
    try:
        with SessionLocal() as session:
            stmt = select(Organization).where(Organization.id == settings.default_organization_id)
            existing = session.scalars(
                stmt,
                execution_options={'include_deleted': True},
            ).one_or_none()
            if existing is None:
                session.add(Organization(id=settings.default_organization_id, name='默认公司'))
                session.commit()

            if settings.bootstrap_admin_password:
                acc_dao = AccountDAO(session)
                if acc_dao.get_by_username(settings.bootstrap_admin_username, include_deleted=True) is None:
                    acc_dao.create_user(
                        username=settings.bootstrap_admin_username,
                        password_hash=hash_password(settings.bootstrap_admin_password),
                        role=AccountRole.ADMIN,
                        organization_id=settings.default_organization_id,
                    )
    except Exception as exc:
        _log.warning(
            'init_db 预置数据跳过（数据库未就绪或未执行迁移）：%s；请创建库并执行 alembic upgrade head',
            exc,
        )
