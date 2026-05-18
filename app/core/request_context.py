from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

REQUEST_ID_HEADER = 'X-Request-Id'

_request_id: ContextVar[str] = ContextVar('request_id', default='-')


def new_request_id() -> str:
    return uuid.uuid4().hex


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str | None) -> Token[str]:
    rid = (request_id or '').strip() or new_request_id()
    return _request_id.set(rid)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)
