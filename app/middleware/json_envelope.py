"""将 2xx JSON 响应包装为 ApiEnvelope（跳过文档与健康检查等）。"""

from __future__ import annotations

import json
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.schemas.api_envelope import ApiEnvelope

# 不参与封装的路径前缀或全路径
_SKIP_PREFIXES: tuple[str, ...] = (
    '/docs',
    '/redoc',
    '/openapi.json',
)
_SKIP_PATHS: frozenset[str] = frozenset({'/docs/oauth2-redirect', '/healthz'})
_SKIP_SUFFIXES: tuple[str, ...] = ('/progress',)


class JsonEnvelopeMiddleware(BaseHTTPMiddleware):
    """
    - 2xx 且 Content-Type 为 JSON 的响应：若根对象不含 success，则包一层 ApiEnvelope
    - 204 No Content：改为 200 + ApiEnvelope(data=null)
    """

    def __init__(self, app: ASGIApp, *, enable: bool = True) -> None:
        super().__init__(app)
        self.enable = enable

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not self.enable:
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_PATHS or any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)
        if any(path.endswith(s) for s in _SKIP_SUFFIXES):
            return await call_next(request)

        response = await call_next(request)

        if 200 <= response.status_code < 300 and response.status_code == 204:
            return JSONResponse(
                status_code=200,
                content=ApiEnvelope.ok(None).dump(),
            )

        if not (200 <= response.status_code < 300):
            return response

        ct = response.headers.get('content-type', '')
        if 'application/json' not in ct:
            return response

        body = b''
        async for chunk in response.body_iterator:
            body += chunk

        try:
            payload = json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        if isinstance(payload, dict) and 'success' in payload:
            return JSONResponse(
                status_code=response.status_code,
                content=payload,
            )

        wrapped = ApiEnvelope.ok(payload).dump()
        out = JSONResponse(status_code=response.status_code, content=wrapped)
        # 透传部分安全头（若需可扩展）
        for k, v in response.headers.items():
            if k.lower() in {'cache-control', 'etag'}:
                out.headers[k] = v
        return out
