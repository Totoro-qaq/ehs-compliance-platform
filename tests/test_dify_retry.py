from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services.dify_service import DifyWorkflowError, run_workflow_blocking


class _FakeClient:
    calls = 0
    responses: list[httpx.Response | Exception] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
        type(self).calls += 1
        item = type(self).responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(status_code: int, payload: dict[str, Any] | None = None) -> httpx.Response:
    request = httpx.Request('POST', 'https://api.dify.ai/v1/workflows/run')
    return httpx.Response(status_code, json=payload or {'error': 'failed'}, request=request)


@pytest.fixture(autouse=True)
def _dify_settings(monkeypatch):
    monkeypatch.setattr(settings, 'dify_api_key', 'test-key')
    monkeypatch.setattr(settings, 'dify_retry_max_attempts', 3)
    monkeypatch.setattr(settings, 'dify_retry_initial_delay_seconds', 0.1)
    monkeypatch.setattr(settings, 'dify_retry_max_delay_seconds', 0.1)
    monkeypatch.setattr(settings, 'dify_retry_jitter_seconds', 0.0)
    monkeypatch.setattr(settings, 'dify_retry_on_timeout', False)
    monkeypatch.setattr('app.services.dify_service.time.sleep', lambda _delay: None)


def test_run_workflow_retries_429_then_succeeds(monkeypatch):
    _FakeClient.calls = 0
    _FakeClient.responses = [
        _response(429, {'message': 'rate limited'}),
        _response(
            200,
            {
                'task_id': 'dify-task',
                'workflow_run_id': 'run-1',
                'data': {'status': 'succeeded', 'outputs': {'result': '{"risks": [], "summary": "ok"}'}},
            },
        ),
    ]
    monkeypatch.setattr(httpx, 'Client', _FakeClient)

    result = run_workflow_blocking(inputs={'document_text': 'text'}, user='test-user')

    assert _FakeClient.calls == 2
    assert result['task_id'] == 'dify-task'


def test_run_workflow_does_not_retry_401(monkeypatch):
    _FakeClient.calls = 0
    _FakeClient.responses = [_response(401, {'message': 'unauthorized'})]
    monkeypatch.setattr(httpx, 'Client', _FakeClient)

    with pytest.raises(DifyWorkflowError) as exc_info:
        run_workflow_blocking(inputs={'document_text': 'text'}, user='test-user')

    assert _FakeClient.calls == 1
    assert exc_info.value.status_code == 401
    assert exc_info.value.retryable is False


def test_run_workflow_does_not_retry_timeout_by_default(monkeypatch):
    _FakeClient.calls = 0
    _FakeClient.responses = [httpx.TimeoutException('timeout')]
    monkeypatch.setattr(httpx, 'Client', _FakeClient)

    with pytest.raises(DifyWorkflowError) as exc_info:
        run_workflow_blocking(inputs={'document_text': 'text'}, user='test-user', timeout_sec=1)

    assert _FakeClient.calls == 1
    assert exc_info.value.retryable is False
