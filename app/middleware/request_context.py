from __future__ import annotations

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.request_context import (
    REQUEST_ID_HEADER,
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id to request-scoped logs and return it to clients."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        token = set_request_id(incoming or new_request_id())
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = get_request_id()
            return response
        finally:
            reset_request_id(token)
