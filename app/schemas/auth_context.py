"""认证上下文（由 Depends 注入，供 Service 做 IDOR 校验）。"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.db_models import AccountRole


@dataclass(frozen=True, slots=True)
class CurrentUser:
    """从 JWT 解析后的当前调用方（不信任客户端 body 中的 id）。

    ``organization_id``：登录用户所属公司；系统管理员可为空或绑定某公司以便审计。
    """

    account_id: str
    username: str
    role: AccountRole
    organization_id: str | None
