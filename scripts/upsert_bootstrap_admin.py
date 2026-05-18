"""
将预置管理员写入数据库：不存在则创建，已存在则重置密码（bcrypt，明文仅来自配置）。

前置：已创建库、已执行 `alembic upgrade head`。

用法（读取项目根 .env）：
    python scripts/upsert_bootstrap_admin.py

依赖 .env 中的 BOOTSTRAP_ADMIN_PASSWORD（及可选 BOOTSTRAP_ADMIN_USERNAME）。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 保证从项目根加载 app 与 .env
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.dao.account_dao import AccountDAO  # noqa: E402
from app.models.db_models import AccountRole, Organization  # noqa: E402


def main() -> None:
    if not settings.bootstrap_admin_password:
        print('请在 .env 中设置 BOOTSTRAP_ADMIN_PASSWORD 后再运行', file=sys.stderr)
        sys.exit(1)

    uname = settings.bootstrap_admin_username
    pwd_hash = hash_password(settings.bootstrap_admin_password)

    with SessionLocal() as session:
        stmt = select(Organization).where(Organization.id == settings.default_organization_id)
        org = session.scalars(stmt, execution_options={'include_deleted': True}).one_or_none()
        if org is None:
            session.add(Organization(id=settings.default_organization_id, name='默认公司'))
            session.commit()

        dao = AccountDAO(session)
        acc = dao.get_by_username(uname, include_deleted=True)
        if acc is None:
            dao.create_user(
                username=uname,
                password_hash=pwd_hash,
                role=AccountRole.ADMIN,
                organization_id=settings.default_organization_id,
            )
            print(f'已创建管理员账号: {uname}（密码已写入 bcrypt 哈希）')
            return

        acc.password_hash = pwd_hash
        acc.role = AccountRole.ADMIN
        if acc.deleted_at is not None:
            acc.deleted_at = None
        if acc.organization_id is None:
            acc.organization_id = settings.default_organization_id
        session.commit()
        print(f'已更新管理员 {uname} 的密码哈希（bcrypt）')


if __name__ == '__main__':
    main()
