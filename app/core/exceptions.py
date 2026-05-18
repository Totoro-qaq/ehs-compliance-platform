"""业务侧统一异常基类，便于 API 层统一返回与记录。"""

from __future__ import annotations

from typing import Any


class EHSException(Exception):
    """
    平台业务异常：携带错误码、HTTP 状态与可选结构化详情。
    在 API 层会被转换为 JSON，并写入日志（含堆栈）。
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = 'EHS_ERROR',
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)
