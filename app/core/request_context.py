from __future__ import annotations

import re
import secrets
import uuid
from contextvars import ContextVar, Token
from typing import NamedTuple

REQUEST_ID_HEADER = 'X-Request-Id'
TRACEPARENT_HEADER = 'traceparent'

_request_id: ContextVar[str] = ContextVar('request_id', default='-')
_trace_id: ContextVar[str] = ContextVar('trace_id', default='-')
_span_id: ContextVar[str] = ContextVar('span_id', default='-')

_TRACE_ID_RE = re.compile(r'^[0-9a-f]{32}$')
_SPAN_ID_RE = re.compile(r'^[0-9a-f]{16}$')


class TraceContextToken(NamedTuple):
    trace_id: Token[str]
    span_id: Token[str]


def new_request_id() -> str:
    return uuid.uuid4().hex


def new_trace_id() -> str:
    return uuid.uuid4().hex


def new_span_id() -> str:
    return secrets.token_hex(8)


def get_request_id() -> str:
    return _request_id.get()


def get_trace_id() -> str:
    return _trace_id.get()


def get_span_id() -> str:
    return _span_id.get()


def set_request_id(request_id: str | None) -> Token[str]:
    rid = (request_id or '').strip() or new_request_id()
    return _request_id.set(rid)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def _valid_trace_id(value: str) -> bool:
    return bool(_TRACE_ID_RE.fullmatch(value)) and value != '0' * 32


def _valid_span_id(value: str) -> bool:
    return bool(_SPAN_ID_RE.fullmatch(value)) and value != '0' * 16


def parse_traceparent(value: str | None) -> tuple[str, str] | None:
    """Parse a W3C traceparent header and return (trace_id, parent_span_id)."""
    if not value:
        return None
    parts = value.strip().split('-')
    if len(parts) != 4:
        return None
    version, trace_id, parent_span_id, _flags = parts
    if version != '00':
        return None
    if not _valid_trace_id(trace_id) or not _valid_span_id(parent_span_id):
        return None
    return trace_id, parent_span_id


def set_trace_context(
    *,
    traceparent: str | None = None,
    trace_id: str | None = None,
) -> TraceContextToken:
    parsed = parse_traceparent(traceparent)
    tid = (trace_id or '').strip().lower()
    if not _valid_trace_id(tid):
        tid = parsed[0] if parsed else new_trace_id()
    sid = new_span_id()
    return TraceContextToken(trace_id=_trace_id.set(tid), span_id=_span_id.set(sid))


def reset_trace_context(token: TraceContextToken) -> None:
    _span_id.reset(token.span_id)
    _trace_id.reset(token.trace_id)


def get_traceparent() -> str | None:
    trace_id = get_trace_id()
    span_id = get_span_id()
    if not _valid_trace_id(trace_id) or not _valid_span_id(span_id):
        return None
    return f'00-{trace_id}-{span_id}-01'
