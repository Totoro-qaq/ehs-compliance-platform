from __future__ import annotations

import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_setup import get_logger
from app.core.request_context import (
    REQUEST_ID_HEADER,
    TRACEPARENT_HEADER,
    get_request_id,
    get_traceparent,
    new_request_id,
    reset_request_id,
    reset_trace_context,
    set_request_id,
    set_trace_context,
)

_log = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request id to request-scoped logs and return it to clients."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        token = set_request_id(incoming or new_request_id())
        trace_token = set_trace_context(traceparent=request.headers.get(TRACEPARENT_HEADER))
        started = time.perf_counter()
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = get_request_id()
            traceparent = get_traceparent()
            if traceparent:
                response.headers[TRACEPARENT_HEADER] = traceparent
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            response.headers['X-Process-Time-Ms'] = str(elapsed_ms)
            _log.info(
                'HTTP request completed method=%s path=%s status=%s elapsed_ms=%s',
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            _log.exception(
                'HTTP request failed method=%s path=%s elapsed_ms=%s',
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        finally:
            reset_trace_context(trace_token)
            reset_request_id(token)
