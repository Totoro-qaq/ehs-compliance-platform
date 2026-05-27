from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.tracing import capture_spans


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_agent_chat_records_runtime_tool_and_run_spans(
    client: TestClient,
    user_token: str,
) -> None:
    with capture_spans() as spans:
        response = client.post(
            '/api/v1/agent/chat',
            json={'content': '总结当前工作台'},
            headers=_auth(user_token),
        )

    assert response.status_code == 200
    span_names = [span.name for span in spans]
    assert 'agent.runtime_policy' in span_names
    assert 'agent.tool_call.get_workbench_summary' in span_names
    assert 'agent.run' in span_names

    run_span = next(span for span in spans if span.name == 'agent.run')
    assert run_span.attributes['agent.provider'] == 'rules'
    assert run_span.attributes['agent.model_name'] == 'fast-summary'
    assert run_span.attributes['agent.fast_summary'] is True


def test_agent_chat_records_llm_span_for_model_route(
    client: TestClient,
    user_token: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, 'agent_llm_provider', 'mock')

    with capture_spans() as spans:
        response = client.post(
            '/api/v1/agent/chat',
            json={'content': '请解释一下职业卫生评价的整改思路'},
            headers=_auth(user_token),
        )

    assert response.status_code == 200
    assert response.json()['data']['assistant_message']['content'] == 'AGENT_MOCK_RESPONSE'
    llm_span = next(span for span in spans if span.name == 'agent.llm.call')
    assert llm_span.attributes['agent.provider'] == 'mock'
    assert llm_span.attributes['agent.model_name'] == 'mock-agent-model'
