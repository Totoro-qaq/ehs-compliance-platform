import re

from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.patterns import USERNAME, normalize_cn_mobile


def _validate_password_complexity(v: str) -> str:
    if re.search(r'\s', v):
        raise ValueError('密码不能含空白字符')
    if not re.search(r'[a-z]', v) or not re.search(r'[A-Z]', v) or not re.search(r'\d', v):
        raise ValueError('密码须同时包含小写字母、大写字母与数字')
    return v


class LoginRequest(BaseModel):
    """登录：`identifier` 与 `username` / `email` / `phone` 四选一（值均为同一登录账号字符串）。"""

    model_config = ConfigDict(populate_by_name=True)

    identifier: str = Field(
        min_length=3,
        max_length=255,
        description='用户名、邮箱或手机号（也可使用同义字段 username / email / phone）',
        validation_alias=AliasChoices('identifier', 'username', 'email', 'phone'),
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description='登录密码，须含大小写字母与数字，8–128 位，不可含空白',
    )
    captcha_id: str | None = Field(default=None, description='验证码 ID（从 GET /auth/captcha 响应头获取）')
    captcha_code: str | None = Field(default=None, description='用户输入的验证码')

    @field_validator('identifier')
    @classmethod
    def identifier_strip(cls, v: str) -> str:
        return v.strip()

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class RegisterRequest(BaseModel):
    """自助注册：写入 accounts，角色 USER，默认公司；邮箱、电话校验后入库且唯一。"""

    username: str = Field(pattern=USERNAME, description='登录用户名：3–64 位，含字母、数字及 _ . -')
    password: str = Field(
        min_length=8,
        max_length=128,
        description='注册密码，须含大小写字母与数字，8–128 位，不可含空白',
    )
    email: EmailStr = Field(max_length=255, description='电子邮箱，唯一；入库前会规范为小写')
    phone: str = Field(min_length=11, max_length=20, description='中国大陆手机号，可带 +86')

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)

    @field_validator('email', mode='before')
    @classmethod
    def email_normalize(cls, v) -> str:
        if v is None:
            raise ValueError('邮箱不能为空')
        if isinstance(v, str):
            return v.strip().lower()
        return v

    @field_validator('phone')
    @classmethod
    def phone_normalize(cls, v: str) -> str:
        return normalize_cn_mobile(v)


class TokenOut(BaseModel):
    """登录/注册成功时返回的访问令牌。"""

    access_token: str = Field(description='JWT 访问令牌；请求头：`Authorization: Bearer <access_token>`')
    token_type: str = Field(default='bearer', description='令牌类型，固定为 bearer')
    expires_in: int = Field(description='访问令牌有效时长（秒）')


class ChangePasswordRequest(BaseModel):
    """已登录用户修改密码：需验证旧密码。"""

    old_password: str = Field(min_length=8, max_length=128, description='当前密码')
    new_password: str = Field(min_length=8, max_length=128, description='新密码，须符合复杂度要求')

    @field_validator('new_password')
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)


class AdminResetPasswordRequest(BaseModel):
    """管理员重置指定用户密码（无需旧密码）。"""

    account_id: str = Field(description='目标用户 ID')
    new_password: str = Field(min_length=8, max_length=128, description='新密码，须符合复杂度要求')

    @field_validator('new_password')
    @classmethod
    def new_password_complexity(cls, v: str) -> str:
        return _validate_password_complexity(v)
