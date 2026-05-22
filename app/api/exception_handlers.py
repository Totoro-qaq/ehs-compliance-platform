"""全局异常处理：统一 ApiEnvelope + 日志。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import EHSException
from app.core.logging_setup import get_logger
from app.schemas.api_envelope import ApiEnvelope

_log = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=ApiEnvelope.fail(
                code='VALIDATION_ERROR',
                message='请求参数校验失败',
                details={'errors': exc.errors()},
            ).dump(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else str(detail)
        code = f'HTTP_{exc.status_code}'
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiEnvelope.fail(code=code, message=message).dump(),
        )

    @app.exception_handler(EHSException)
    async def ehs_exception_handler(request: Request, exc: EHSException) -> JSONResponse:
        _log.warning(
            '业务异常 [%s] status=%s path=%s message=%s',
            exc.code,
            exc.status_code,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiEnvelope.fail(
                code=exc.code,
                message=exc.message,
                details=exc.details if exc.details else None,
            ).dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _log.error('未捕获异常: %s', exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content=ApiEnvelope.fail(
                code='INTERNAL_ERROR',
                message='内部服务器错误',
            ).dump(),
        )
