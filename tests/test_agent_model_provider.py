from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import EHSException
from app.services.agent_model_provider import (
    MockAgentModelProvider,
    get_configured_agent_model_metadata,
    get_configured_agent_model_provider,
)


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_mock_agent_model_provider_returns_configured_response() -> None:
    provider = MockAgentModelProvider(response='mock response')

    response = asyncio.run(provider.generate(messages=[{'role': 'user', 'content': 'hello'}]))

    assert response == 'mock response'


def test_agent_model_provider_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, 'agent_llm_provider', 'unknown-provider')

    metadata = get_configured_agent_model_metadata()

    assert metadata.provider_name == 'unknown-provider'
    assert metadata.model_name == 'unsupported'
    with pytest.raises(EHSException) as exc_info:
        get_configured_agent_model_provider()
    assert exc_info.value.code == 'AGENT_PROVIDER_NOT_SUPPORTED'


def test_agent_chat_uses_mock_provider(
    client: TestClient,
    user_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, 'agent_llm_provider', 'mock')

    response = client.post(
        '/api/v1/agent/chat',
        json={'content': '请解释一下职业卫生评价的整改思路'},
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    data = response.json()['data']
    assert data['degraded'] is False
    assert data['run']['provider'] == 'mock'
    assert data['run']['model_name'] == 'mock-agent-model'
    assert data['assistant_message']['content'] == 'AGENT_MOCK_RESPONSE'


def test_agent_chat_falls_back_for_unknown_provider(
    client: TestClient,
    user_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, 'agent_llm_provider', 'unknown-provider')

    response = client.post(
        '/api/v1/agent/chat',
        json={'content': '请解释一下职业卫生评价的整改思路'},
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    data = response.json()['data']
    assert data['degraded'] is True
    assert data['run']['provider'] == 'fallback'
    assert data['run']['model_name'] == 'rules'
    assert '本次模型未响应' in data['assistant_message']['content']
