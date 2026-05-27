from __future__ import annotations

import pytest

from app.core.request_context import (
    get_span_id,
    reset_trace_context,
    set_trace_context,
)
from app.core.tracing import capture_spans, start_span


def test_start_span_records_nested_spans_and_restores_context() -> None:
    trace_token = set_trace_context(trace_id='1234567890abcdef1234567890abcdef')
    root_span_id = get_span_id()
    try:
        with capture_spans() as spans:
            with start_span('outer', {'kind': 'test'}) as outer:
                assert get_span_id() == outer.span_id
                with start_span('inner') as inner:
                    assert get_span_id() == inner.span_id
                assert get_span_id() == outer.span_id
            assert get_span_id() == root_span_id
    finally:
        reset_trace_context(trace_token)

    assert [span.name for span in spans] == ['inner', 'outer']
    assert spans[0].parent_span_id == spans[1].span_id
    assert spans[1].parent_span_id == root_span_id
    assert spans[1].attributes == {'kind': 'test'}
    assert all(span.trace_id == '1234567890abcdef1234567890abcdef' for span in spans)
    assert all(span.status == 'OK' for span in spans)


def test_start_span_records_error_status() -> None:
    trace_token = set_trace_context(trace_id='1234567890abcdef1234567890abcdef')
    try:
        with capture_spans() as spans, pytest.raises(ValueError), start_span('failing'):
            raise ValueError('boom')
    finally:
        reset_trace_context(trace_token)

    assert len(spans) == 1
    assert spans[0].name == 'failing'
    assert spans[0].status == 'ERROR'
    assert spans[0].error_type == 'ValueError'
    assert spans[0].error_message == 'boom'
