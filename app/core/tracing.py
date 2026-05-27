from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

from app.core.logging_setup import get_logger
from app.core.request_context import (
    get_span_id,
    get_trace_id,
    new_span_id,
    reset_span_id,
    set_span_id,
)

_logger = get_logger(__name__)
_span_sink: ContextVar[list['CompletedSpan'] | None] = ContextVar('trace_span_sink', default=None)


@dataclass(frozen=True, slots=True)
class CompletedSpan:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str
    attributes: dict[str, Any]
    status: str
    duration_ms: int
    error_type: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class SpanHandle:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    trace_id: str = field(default_factory=get_trace_id)
    parent_span_id: str = field(default_factory=get_span_id)
    span_id: str = field(default_factory=new_span_id)
    _started_at: float = field(default_factory=time.perf_counter)
    _span_token: Token[str] | None = None
    _finished: bool = False

    def __post_init__(self) -> None:
        self._span_token = set_span_id(self.span_id)
        _logger.info(
            'trace.span started name=%s trace_id=%s span_id=%s parent_span_id=%s attributes=%s',
            self.name,
            self.trace_id,
            self.span_id,
            self.parent_span_id,
            _json_attributes(self.attributes),
        )

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def finish(self, error: BaseException | None = None) -> CompletedSpan:
        if self._finished:
            return CompletedSpan(
                name=self.name,
                trace_id=self.trace_id,
                span_id=self.span_id,
                parent_span_id=self.parent_span_id,
                attributes=dict(self.attributes),
                status='OK' if error is None else 'ERROR',
                duration_ms=0,
                error_type=type(error).__name__ if error else None,
                error_message=str(error) if error else None,
            )

        self._finished = True
        duration_ms = int((time.perf_counter() - self._started_at) * 1000)
        completed = CompletedSpan(
            name=self.name,
            trace_id=self.trace_id,
            span_id=self.span_id,
            parent_span_id=self.parent_span_id,
            attributes=dict(self.attributes),
            status='OK' if error is None else 'ERROR',
            duration_ms=duration_ms,
            error_type=type(error).__name__ if error else None,
            error_message=str(error)[:500] if error else None,
        )
        sink = _span_sink.get()
        if sink is not None:
            sink.append(completed)
        _logger.info(
            'trace.span completed name=%s trace_id=%s span_id=%s parent_span_id=%s '
            'status=%s duration_ms=%s error_type=%s attributes=%s',
            completed.name,
            completed.trace_id,
            completed.span_id,
            completed.parent_span_id,
            completed.status,
            completed.duration_ms,
            completed.error_type,
            _json_attributes(completed.attributes),
        )
        if self._span_token is not None:
            reset_span_id(self._span_token)
            self._span_token = None
        return completed


def begin_span(name: str, attributes: dict[str, Any] | None = None) -> SpanHandle:
    return SpanHandle(name=name, attributes=dict(attributes or {}))


@contextmanager
def start_span(name: str, attributes: dict[str, Any] | None = None) -> Iterator[SpanHandle]:
    span = begin_span(name, attributes)
    try:
        yield span
    except Exception as exc:
        span.finish(exc)
        raise
    else:
        span.finish()


@contextmanager
def capture_spans() -> Iterator[list[CompletedSpan]]:
    spans: list[CompletedSpan] = []
    token = _span_sink.set(spans)
    try:
        yield spans
    finally:
        _span_sink.reset(token)


def _json_attributes(attributes: dict[str, Any]) -> str:
    return json.dumps(attributes, ensure_ascii=False, default=str, sort_keys=True)
