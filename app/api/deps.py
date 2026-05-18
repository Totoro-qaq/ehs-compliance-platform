"""全局依赖：JWT 解析、管理员鉴权。"""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import PyJWTError

from app.core.config import settings
from app.core.exceptions import EHSException
from app.models.db_models import AccountRole
from app.schemas.auth_context import CurrentUser

security = HTTPBearer(
    auto_error=False,
    bearerFormat='JWT',
    description=(
        '使用 /api/v1/auth/login 或 /api/v1/auth/register 返回的访问令牌；'
        '成功响应经统一信封包装，令牌位于 `data.access_token`。'
        '请求头格式：`Authorization: Bearer <access_token>`。'
        '请勿在路径末尾多余 `/`，以免 307 重定向时部分客户端丢弃 Authorization。'
    ),
)

_API_KEY_ACCOUNT_ID = '00000000-0000-0000-0000-000000000001'


def current_user_from_token(token: str) -> CurrentUser:
    """解码访问令牌；异常转为 EHSException（走统一 Envelope）。"""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=['HS256'])
    except PyJWTError as exc:
        raise EHSException(
            '登录已失效或令牌无效',
            code='INVALID_TOKEN',
            status_code=401,
        ) from exc

    username = payload.get('sub')
    role_raw = payload.get('role')
    aid = payload.get('aid')
    if not username or not role_raw or not aid:
        raise EHSException(
            '令牌格式无效，请重新登录',
            code='INVALID_TOKEN',
            status_code=401,
        )
    try:
        role = AccountRole(role_raw)
    except ValueError as exc:
        raise EHSException('令牌角色无效', code='INVALID_TOKEN', status_code=401) from exc

    oid = payload.get('oid')
    if oid == '':
        oid = None

    return CurrentUser(
        account_id=str(aid),
        username=str(username),
        role=role,
        organization_id=str(oid) if oid is not None else None,
    )


def api_key_admin_actor() -> CurrentUser:
    """X-Admin-Key 通过时的合成主体（审计上视为内置管理员）。"""
    return CurrentUser(
        account_id=_API_KEY_ACCOUNT_ID,
        username='__x_admin_key__',
        role=AccountRole.ADMIN,
        organization_id=None,
    )


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> CurrentUser:
    """任何需要登录的业务接口 Depends 本函数，在 Service 层做公司/创建者校验防 IDOR。"""
    if creds is None or creds.scheme.lower() != 'bearer':
        raise EHSException(
            '未提供凭证：请在 Authorization 头携带 Bearer 访问令牌',
            code='UNAUTHORIZED',
            status_code=401,
        )
    return current_user_from_token(creds.credentials)


async def require_admin(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    x_admin_key: Annotated[str | None, Header(alias='X-Admin-Key')] = None,
) -> CurrentUser:
    """
    管理员接口：有效 X-Admin-Key（若配置）或 JWT 且 role=ADMIN。
    返回 CurrentUser 便于审计；API Key 路径使用合成账号。
    """
    if settings.admin_api_key and x_admin_key and x_admin_key == settings.admin_api_key:
        return api_key_admin_actor()
    if creds is None or creds.scheme.lower() != 'bearer':
        raise EHSException(
            '需要管理员权限：请使用管理员账号登录或提供有效 X-Admin-Key',
            code='UNAUTHORIZED',
            status_code=401,
        )
    user = current_user_from_token(creds.credentials)
    if user.role != AccountRole.ADMIN:
        raise EHSException(
            '禁止访问：需要管理员角色',
            code='FORBIDDEN',
            status_code=403,
            details={'reason': 'ADMIN_ROLE_REQUIRED'},
        )
    return user
