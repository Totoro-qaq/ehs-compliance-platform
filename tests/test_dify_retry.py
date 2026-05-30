from __future__ import annotations

from typing import Any

import httpx
import pytest

from app.core.config import settings
from app.services.dify_service import (
    DifyResultStructureError,
    DifyWorkflowError,
    fetch_assessment_result,
    run_workflow_blocking,
)


class _FakeClient:
    calls = 0
    responses: list[httpx.Response | Exception] = []
    init_kwargs: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        type(self).init_kwargs.append(kwargs)

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
    monkeypatch.setattr(settings, 'dify_base_url', 'https://api.dify.ai/v1')
    monkeypatch.setattr(settings, 'dify_retry_max_attempts', 3)
    monkeypatch.setattr(settings, 'dify_retry_initial_delay_seconds', 0.1)
    monkeypatch.setattr(settings, 'dify_retry_max_delay_seconds', 0.1)
    monkeypatch.setattr(settings, 'dify_retry_jitter_seconds', 0.0)
    monkeypatch.setattr(settings, 'dify_retry_on_timeout', False)
    monkeypatch.setattr('app.services.dify_service.time.sleep', lambda _delay: None)


def test_run_workflow_retries_429_then_succeeds(monkeypatch):
    _FakeClient.calls = 0
    _FakeClient.init_kwargs = []
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
    _FakeClient.init_kwargs = []
    _FakeClient.responses = [_response(401, {'message': 'unauthorized'})]
    monkeypatch.setattr(httpx, 'Client', _FakeClient)

    with pytest.raises(DifyWorkflowError) as exc_info:
        run_workflow_blocking(inputs={'document_text': 'text'}, user='test-user')

    assert _FakeClient.calls == 1
    assert exc_info.value.status_code == 401
    assert exc_info.value.retryable is False


def test_run_workflow_does_not_retry_timeout_by_default(monkeypatch):
    _FakeClient.calls = 0
    _FakeClient.init_kwargs = []
    _FakeClient.responses = [httpx.TimeoutException('timeout')]
    monkeypatch.setattr(httpx, 'Client', _FakeClient)

    with pytest.raises(DifyWorkflowError) as exc_info:
        run_workflow_blocking(inputs={'document_text': 'text'}, user='test-user', timeout_sec=1)

    assert _FakeClient.calls == 1
    assert exc_info.value.retryable is False


def test_run_workflow_disables_proxy_env_for_local_dify(monkeypatch):
    _FakeClient.calls = 0
    _FakeClient.init_kwargs = []
    _FakeClient.responses = [
        _response(
            200,
            {
                'task_id': 'dify-task',
                'workflow_run_id': 'run-1',
                'data': {'status': 'succeeded', 'outputs': {'result': '{"risks": [], "summary": "ok"}'}},
            },
        )
    ]
    monkeypatch.setattr(settings, 'dify_base_url', 'http://localhost/v1')
    monkeypatch.setattr(httpx, 'Client', _FakeClient)

    run_workflow_blocking(inputs={'document_text': 'text'}, user='test-user')

    assert _FakeClient.init_kwargs[0]['trust_env'] is False


def test_fetch_assessment_result_raises_structure_error_with_raw_output(monkeypatch):
    monkeypatch.setattr(settings, 'dify_usage_mode', 'legacy_assessment')
    monkeypatch.setattr(settings, 'dify_enable_compliance_workflow', True)

    def _fake_run_workflow_blocking(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            'data': {
                'status': 'succeeded',
                'outputs': {'result': 'plain model answer without json'},
            }
        }

    monkeypatch.setattr('app.services.dify_service.run_workflow_blocking', _fake_run_workflow_blocking)

    with pytest.raises(DifyResultStructureError) as exc_info:
        fetch_assessment_result(document_text='text', filename='sample.txt', task_id='task-1')

    assert exc_info.value.raw_output == 'plain model answer without json'
    assert exc_info.value.retryable is False


def test_fetch_assessment_result_blocks_compliance_workflow_by_default(monkeypatch):
    called = False

    def _fake_run_workflow_blocking(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {'data': {'status': 'succeeded', 'outputs': {'result': '{"risks": [], "summary": "ok"}'}}}

    monkeypatch.setattr('app.services.dify_service.run_workflow_blocking', _fake_run_workflow_blocking)

    with pytest.raises(DifyResultStructureError) as exc_info:
        fetch_assessment_result(document_text='text', filename='sample.txt', task_id='task-1')

    assert called is False
    assert '合规评价' in str(exc_info.value)


def test_fetch_assessment_result_blocks_dify_retriever_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, 'dify_usage_mode', 'legacy_assessment')
    monkeypatch.setattr(settings, 'dify_enable_compliance_workflow', True)
    monkeypatch.setattr(settings, 'dify_allow_standard_retrieval', False)

    def _fake_run_workflow_blocking(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            'data': {
                'status': 'succeeded',
                'metadata': {'retriever_resources': [{'dataset_id': 'dataset-risk'}]},
                'outputs': {'result': '{"risks": [], "summary": "ok"}'},
            }
        }

    monkeypatch.setattr('app.services.dify_service.run_workflow_blocking', _fake_run_workflow_blocking)

    with pytest.raises(DifyResultStructureError) as exc_info:
        fetch_assessment_result(document_text='text', filename='sample.txt', task_id='task-1')

    assert '禁止 Dify 自带标准检索' in str(exc_info.value)
