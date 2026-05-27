from __future__ import annotations

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.db_models import AccountRole
from app.schemas.auth_context import CurrentUser
from app.services.agent_tools import AgentTools
from app.services.rag.provider import RagflowService
from app.services.rag.ragflow_client import RagflowClient


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _actor() -> CurrentUser:
    return CurrentUser(
        account_id='ragflow-shell-account',
        username='ragflow-shell-user',
        role=AccountRole.USER,
        organization_id=settings.default_organization_id,
    )


def test_ragflow_service_disabled_without_config(monkeypatch) -> None:
    monkeypatch.setattr(settings, 'ragflow_base_url', '')
    monkeypatch.setattr(settings, 'ragflow_api_key', '')
    monkeypatch.setattr(settings, 'ragflow_dataset_ids', '')

    health = RagflowService.healthcheck()
    result = RagflowService.search_chunks(query='authorized guideline', limit=3)

    assert health.configured is False
    assert health.ok is False
    assert result.configured is False
    assert result.items == []
    assert result.limit == 3
    assert result.error == 'RAGFLOW_BASE_URL is not configured'


def test_ragflow_health_endpoint_requires_auth(client: TestClient) -> None:
    response = client.get('/api/v1/ragflow/health')

    assert response.status_code == 401


def test_ragflow_health_endpoint_returns_disabled_state(
    client: TestClient,
    user_token: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, 'ragflow_base_url', '')
    monkeypatch.setattr(settings, 'ragflow_api_key', '')
    monkeypatch.setattr(settings, 'ragflow_dataset_ids', '')

    response = client.get('/api/v1/ragflow/health', headers=_auth(user_token))

    assert response.status_code == 200
    data = response.json()['data']
    assert data['configured'] is False
    assert data['ok'] is False
    assert data['error'] == 'RAGFLOW_BASE_URL is not configured'


def test_ragflow_client_maps_retrieval_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                'code': 0,
                'data': {
                    'chunks': [
                        {
                            'id': 'chunk-001',
                            'document_id': 'doc-001',
                            'content': 'authorized guideline excerpt',
                            'score': 0.91,
                            'metadata': {
                                'standard_code': 'GUIDE-001',
                                'standard_name': 'Guideline Test',
                                'clause': '3.1',
                                'page': 8,
                                'source_uri': 'ragflow://dataset-a/doc-001/chunk-001',
                            },
                        }
                    ]
                },
            },
        )

    client = RagflowClient(
        base_url='http://ragflow.test',
        api_key='test-key',
        dataset_ids=['dataset-a'],
        timeout_seconds=3.0,
        transport=httpx.MockTransport(handler),
    )

    result = client.search_chunks(
        query='guideline test',
        standard_code='GUIDE-001',
        clause='3.1',
        limit=2,
    )

    assert result.configured is True
    assert result.dataset_ids == ['dataset-a']
    assert len(result.items) == 1
    item = result.items[0]
    assert item.dataset_id == 'dataset-a'
    assert item.document_id == 'doc-001'
    assert item.chunk_id == 'chunk-001'
    assert item.standard_code == 'GUIDE-001'
    assert item.clause == '3.1'
    assert item.page == 8
    assert item.chunk_text == 'authorized guideline excerpt'
    assert item.score == 0.91
    assert requests[0].url.path == '/api/v1/retrieval'
    assert requests[0].headers['Authorization'] == 'Bearer test-key'


def test_agent_guideline_tool_returns_disabled_shell_result(
    db: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, 'ragflow_base_url', '')
    monkeypatch.setattr(settings, 'ragflow_api_key', '')
    monkeypatch.setattr(settings, 'ragflow_dataset_ids', '')

    result = AgentTools.run_tool(
        db=db,
        actor=_actor(),
        tool_name='search_guideline_chunks',
        arguments={'query': 'guideline lookup', 'limit': 4},
    )

    assert result.tool_name == 'search_guideline_chunks'
    assert result.result['configured'] is False
    assert result.result['items'] == []
    assert result.result['limit'] == 4
