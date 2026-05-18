"""统一 API JSON 契约，便于前端拦截器与错误处理。"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')


class ApiEnvelope(BaseModel, Generic[T]):
    """成功与失败均使用同一顶层字段，HTTP 状态码仍表示 REST 语义。"""

    success: bool
    code: str = Field(description='业务码：成功为 0，失败为业务错误码字符串')
    message: str
    data: T | None = None
    details: dict[str, Any] | None = Field(default=None, description='扩展信息，如校验细节、调试字段')

    @classmethod
    def ok(cls, data: T | None = None, *, message: str = 'ok', code: str = '0') -> ApiEnvelope[T]:
        return cls(success=True, code=code, message=message, data=data, details=None)

    @classmethod
    def fail(
        cls,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> ApiEnvelope[None]:
        return cls(success=False, code=code, message=message, data=None, details=details)

    def dump(self) -> dict[str, Any]:
        """JSON 可序列化 dict（保留 data=null 等显式字段）。"""
        return self.model_dump(mode='json')
