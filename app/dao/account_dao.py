"""账号数据访问。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.patterns import normalize_cn_mobile
from app.dao.base_repository import BaseRepository
from app.models.db_models import Account, AccountRole


class AccountDAO(BaseRepository[Account]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Account)

    def get_by_username(
        self, username: str, *, include_deleted: bool = False
    ) -> Account | None:
        stmt = select(Account).where(Account.username == username)
        opts = {'include_deleted': True} if include_deleted else {}
        # ORM 实体必须用 scalars()；scalar_one_or_none() 只取第一列会变成 id 字符串 → 后续属性访问 500
        return self.session.scalars(stmt, execution_options=opts).one_or_none()

    def resolve_login_identifier(
        self, raw: str, *, include_deleted: bool = False
    ) -> Account | None:
        """
        登录用账号解析：邮箱（含 @）→ 用户名 → 手机号（按大陆号规则规范化）。
        """
        s = raw.strip()
        if not s:
            return None
        if '@' in s:
            return self.get_by_email(s, include_deleted=include_deleted)
        acc = self.get_by_username(s, include_deleted=include_deleted)
        if acc is not None:
            return acc
        try:
            phone = normalize_cn_mobile(s)
        except ValueError:
            return None
        return self.get_by_phone(phone, include_deleted=include_deleted)

    def get_by_email(
        self, email: str, *, include_deleted: bool = False
    ) -> Account | None:
        stmt = select(Account).where(Account.email == email.strip().lower())
        opts = {'include_deleted': True} if include_deleted else {}
        return self.session.scalars(stmt, execution_options=opts).one_or_none()

    def get_by_phone(
        self, phone: str, *, include_deleted: bool = False
    ) -> Account | None:
        stmt = select(Account).where(Account.phone == phone)
        opts = {'include_deleted': True} if include_deleted else {}
        return self.session.scalars(stmt, execution_options=opts).one_or_none()

    def create_user(
        self,
        *,
        username: str,
        password_hash: str,
        role: AccountRole = AccountRole.USER,
        organization_id: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Account:
        acc = Account(
            username=username,
            password_hash=password_hash,
            role=role,
            organization_id=organization_id,
            email=email,
            phone=phone,
        )
        return self.save_and_refresh(acc)

    def update_password_hash(self, account_id: str, new_hash: str) -> Account | None:
        return self.update_by_id(account_id, password_hash=new_hash)
