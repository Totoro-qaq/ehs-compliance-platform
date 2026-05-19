from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.core.logging_setup import get_logger
from app.core.security import hash_password, verify_password
from app.dao.account_dao import AccountDAO
from app.models.db_models import AccountRole
from app.schemas.auth_schema import TokenOut

_log = get_logger(__name__)


def create_access_token(
    *,
    username: str,
    role: str,
    account_id: str,
    organization_id: str | None,
) -> TokenOut:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        'sub': username,
        'role': role,
        'aid': account_id,
        'oid': organization_id,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm='HS256')
    expires_in = int((exp - now).total_seconds())
    return TokenOut(access_token=token, expires_in=expires_in)


def login(db: Session, *, identifier: str, password: str) -> TokenOut:
    dao = AccountDAO(db)
    try:
        acc = dao.resolve_login_identifier(identifier)
    except SQLAlchemyError as exc:
        _log.exception('登录查询账户失败（常见原因：未建表或未执行 alembic upgrade head）')
        raise EHSException(
            '登录服务暂不可用，请检查数据库与迁移是否就绪',
            code='DB_UNAVAILABLE',
            status_code=503,
            details=(
                {'reason': str(exc.__cause__ or exc)}
                if settings.app_debug
                else {'reason': 'database_error'}
            ),
        ) from exc
    if acc is None:
        raise EHSException(
            '用户名/邮箱/手机号或密码错误',
            code='AUTH_FAILED',
            status_code=401,
        )
    try:
        password_ok = verify_password(password, acc.password_hash)
    except Exception:
        # 哈希损坏或 passlib 异常时不应变成未捕获 500，统一按鉴权失败处理
        password_ok = False
    if not password_ok:
        raise EHSException(
            '用户名/邮箱/手机号或密码错误',
            code='AUTH_FAILED',
            status_code=401,
        )
    return create_access_token(
        username=acc.username,
        role=acc.role.value,
        account_id=acc.id,
        organization_id=acc.organization_id,
    )


def register(
    db: Session,
    *,
    username: str,
    password: str,
    email: str,
    phone: str,
) -> TokenOut:
    dao = AccountDAO(db)
    if dao.get_by_username(username, include_deleted=True) is not None:
        raise EHSException('该用户名已被占用', code='USERNAME_EXISTS', status_code=409)
    if dao.get_by_email(email, include_deleted=True) is not None:
        raise EHSException('该邮箱已被注册', code='EMAIL_EXISTS', status_code=409)
    if dao.get_by_phone(phone, include_deleted=True) is not None:
        raise EHSException('该手机号已被注册', code='PHONE_EXISTS', status_code=409)
    acc = dao.create_user(
        username=username,
        password_hash=hash_password(password),
        role=AccountRole.USER,
        organization_id=settings.default_organization_id,
        email=email,
        phone=phone,
    )
    return create_access_token(
        username=acc.username,
        role=acc.role.value,
        account_id=acc.id,
        organization_id=acc.organization_id,
    )


def change_password(db: Session, *, account_id: str, old_password: str, new_password: str) -> None:
    """已登录用户修改密码：验证旧密码后更新。"""
    dao = AccountDAO(db)
    acc = dao.get_by_id(account_id)
    if acc is None:
        raise EHSException('账号不存在', code='ACCOUNT_NOT_FOUND', status_code=404)
    if not verify_password(old_password, acc.password_hash):
        raise EHSException('旧密码错误', code='OLD_PASSWORD_WRONG', status_code=400)
    if old_password == new_password:
        raise EHSException('新密码不能与旧密码相同', code='PASSWORD_UNCHANGED', status_code=400)
    dao.update_password_hash(account_id, hash_password(new_password))


def admin_reset_password(db: Session, *, target_account_id: str, new_password: str) -> None:
    """管理员重置指定用户密码（无需旧密码）。"""
    dao = AccountDAO(db)
    acc = dao.get_by_id(target_account_id)
    if acc is None:
        raise EHSException('目标账号不存在', code='ACCOUNT_NOT_FOUND', status_code=404)
    dao.update_password_hash(target_account_id, hash_password(new_password))
