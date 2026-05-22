from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.captcha import create_captcha, verify_captcha
from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import EHSException
from app.schemas.auth_context import CurrentUser
from app.schemas.auth_schema import ChangePasswordRequest, LoginRequest, RegisterRequest, TokenOut
from app.services import auth_service

router = APIRouter(prefix='/auth', tags=['认证'])


@router.get(
    '/captcha',
    summary='获取图形验证码',
    description='返回验证码图片（PNG）和 captcha_id（响应头 X-Captcha-Id）。登录时需携带此 ID 和用户输入。',
    responses={200: {'content': {'image/png': {}}}},
)
def get_captcha():
    captcha_id, image_bytes = create_captcha()
    return Response(
        content=image_bytes,
        media_type='image/png',
        headers={
            'X-Captcha-Id': captcha_id,
            'Cache-Control': 'no-store',
        },
    )


@router.post(
    '/register',
    response_model=TokenOut,
    summary='用户自助注册',
    description=(
        '创建普通用户账号（角色 USER），自动绑定系统默认公司。\n\n'
        '- 用户名 3–64 位，支持字母、数字、`_` `.` `-`\n'
        '- 密码 8–128 位，须含大小写字母与数字，不可含空白\n'
        '- 邮箱与手机号全局唯一\n'
        '- 注册成功后直接返回 JWT 访问令牌，无需再次登录'
    ),
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    return auth_service.register(
        db,
        username=payload.username,
        password=payload.password,
        email=str(payload.email),
        phone=payload.phone,
    )


def _validate_login_captcha(payload: LoginRequest) -> None:
    """
    登录验证码校验。

    默认强制校验；测试或内网部署可关闭 AUTH_CAPTCHA_REQUIRED。关闭时若客户端仍传了验证码，
    也按一次性验证码校验处理，避免前后端行为分叉。
    """
    has_any = bool(payload.captcha_id or payload.captcha_code)
    if not settings.auth_captcha_required and not has_any:
        return
    if not payload.captcha_id or not payload.captcha_code:
        raise EHSException('请同时提供验证码 ID 和验证码', code='CAPTCHA_REQUIRED', status_code=400)
    if not verify_captcha(payload.captcha_id, payload.captcha_code):
        raise EHSException('验证码错误或已过期', code='CAPTCHA_INVALID', status_code=400)


@router.post(
    '/login',
    response_model=TokenOut,
    summary='用户登录',
    description=(
        '支持用户名、邮箱或手机号任一方式登录。\n\n'
        '- 请求体字段 `identifier` 接受三种格式（也可用别名 `username`/`email`/`phone`）\n'
        '- 需携带 `captcha_id` 和 `captcha_code` 进行验证码校验\n'
        '- 返回 JWT 访问令牌，有效期 1 小时\n'
        '- 请求头使用方式：`Authorization: Bearer <access_token>`'
    ),
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    _validate_login_captcha(payload)
    return auth_service.login(db, identifier=payload.identifier, password=payload.password)


@router.post(
    '/refresh',
    response_model=TokenOut,
    summary='刷新访问令牌',
    description=(
        '用当前有效的 JWT 令牌换取新令牌，每次刷新重置 1 小时有效期（滑动窗口）。\n\n'
        '- 前端在用户活跃时自动调用，无需用户手动操作\n'
        '- 若用户不活跃超过 1 小时，前端停止刷新，令牌自然过期'
    ),
)
def refresh_token(actor: Annotated[CurrentUser, Depends(get_current_user)]):
    return auth_service.refresh_access_token(
        username=actor.username,
        role=actor.role,
        account_id=actor.account_id,
        organization_id=actor.organization_id,
    )


@router.post(
    '/change-password',
    status_code=204,
    summary='修改密码（当前用户）',
    description=(
        '已登录用户修改自身密码。\n\n'
        '- 需提供正确的旧密码\n'
        '- 新密码须符合复杂度要求且不能与旧密码相同\n'
        '- 修改成功后当前令牌仍有效，建议前端引导重新登录'
    ),
)
def change_password(
    payload: ChangePasswordRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    auth_service.change_password(
        db,
        account_id=actor.account_id,
        old_password=payload.old_password,
        new_password=payload.new_password,
    )
