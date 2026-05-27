from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.db_models import (
    AssessmentTask,
    Organization,
    StandardChunk,
    StandardDocument,
    TaskStatus,
)

FixtureCase = dict[str, Any]

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / 'fixtures'
    / 'agent_harness'
    / 'basic_agent_harness.json'
)


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _load_cases() -> list[FixtureCase]:
    with FIXTURE_PATH.open(encoding='utf-8') as file:
        data = json.load(file)
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise TypeError('agent harness fixture must be a list of objects')
    return cast(list[FixtureCase], data)


def _seed_standard_chunks(db: Session) -> None:
    text_chunk = '测试因子甲的测试限值依据来自 TEST-RAG-001 第 5.2 条。'
    document = StandardDocument(
        standard_code='TEST-RAG-001',
        standard_name='Agent Harness Test Standard',
        domain='occupational_health',
        storage_backend='minio',
        bucket='ehs-standard-library',
        object_key='raw/agent_harness/test-rag-001.pdf',
        source_path='minio://ehs-standard-library/raw/agent_harness/test-rag-001.pdf',
        source_filename='test-rag-001.pdf',
        source_format='pdf',
        file_hash='h' * 64,
        is_sensitive=0,
    )
    db.add(document)
    db.flush()
    db.add(
        StandardChunk(
            document_id=document.id,
            chunk_id='agent-harness-rag-001-0',
            chunk_index=0,
            standard_code=document.standard_code,
            standard_name=document.standard_name,
            clause='5.2',
            domain=document.domain,
            service_type=document.service_type,
            text_chunk=text_chunk,
            text_hash=hashlib.sha256(text_chunk.encode('utf-8')).hexdigest(),
            page_start=5,
            page_end=5,
            is_sensitive=0,
        )
    )
    db.commit()


def _seed_tenant_isolation_tasks(db: Session) -> None:
    own_org = db.get(Organization, settings.default_organization_id)
    assert own_org is not None

    other_org = Organization(name='Agent Harness Other Org')
    db.add(other_org)
    db.flush()
    db.add_all(
        [
            AssessmentTask(
                organization_id=own_org.id,
                task_name='AGENT_HARNESS_OWN_FAILED_TASK',
                filename='own-agent-harness.txt',
                content_type='text/plain',
                file_path='uploads/own-agent-harness.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message='own failed',
            ),
            AssessmentTask(
                organization_id=other_org.id,
                task_name='AGENT_HARNESS_OTHER_FAILED_TASK',
                filename='other-agent-harness.txt',
                content_type='text/plain',
                file_path='uploads/other-agent-harness.txt',
                status=TaskStatus.FAILED,
                progress=100,
                error_message='other failed',
            ),
        ]
    )
    db.commit()


SETUP_REGISTRY: dict[str, Callable[[Session], None]] = {
    'standard_chunks': _seed_standard_chunks,
    'tenant_isolation_tasks': _seed_tenant_isolation_tasks,
}


def _prepare_case(case: FixtureCase, db: Session) -> None:
    setup_name = case.get('setup')
    if setup_name is None:
        return
    if not isinstance(setup_name, str) or setup_name not in SETUP_REGISTRY:
        raise AssertionError(f'unknown agent harness setup: {setup_name!r}')
    SETUP_REGISTRY[setup_name](db)


def _tool_result_text(tool_calls: list[dict[str, Any]]) -> str:
    payloads: list[Any] = []
    for tool_call in tool_calls:
        raw_result = tool_call.get('result_json')
        if not raw_result:
            continue
        try:
            payloads.append(json.loads(str(raw_result)))
        except json.JSONDecodeError:
            payloads.append(raw_result)
    return json.dumps(payloads, ensure_ascii=False, default=str)


def _assert_expected_response(
    *,
    data: dict[str, Any],
    expected: dict[str, Any],
    call_model: AsyncMock,
) -> None:
    run = data['run']
    assistant_content = data['assistant_message']['content']
    tool_calls = data['tool_calls']
    tool_names = [tool_call['tool_name'] for tool_call in tool_calls]

    if 'provider' in expected:
        assert run['provider'] == expected['provider']
    if 'model_name' in expected:
        assert run['model_name'] == expected['model_name']
    if 'assistant_content' in expected:
        assert assistant_content == expected['assistant_content']
    if 'tool_names' in expected:
        assert tool_names == expected['tool_names']

    for tool_name in expected.get('required_tools', []):
        assert tool_name in tool_names
    for text in expected.get('assistant_contains', []):
        assert text in assistant_content
    for text in expected.get('assistant_not_contains', []):
        assert text not in assistant_content

    tool_result_text = _tool_result_text(tool_calls)
    for text in expected.get('tool_result_not_contains', []):
        assert text not in tool_result_text

    if expected.get('model_called') is True:
        call_model.assert_awaited_once()
    elif expected.get('model_called') is False:
        call_model.assert_not_called()


@pytest.mark.parametrize('case', _load_cases(), ids=lambda case: str(case['id']))
def test_agent_basic_harness_cases(
    case: FixtureCase,
    client: TestClient,
    user_token: str,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_case(case, db)

    llm_config = case.get('llm') or {}
    if llm_config.get('mode') == 'mock':
        call_model = AsyncMock(return_value=llm_config.get('response', 'AGENT_HARNESS_MODEL_RESPONSE'))
    else:
        call_model = AsyncMock(side_effect=RuntimeError('agent harness forbids LLM call'))
    monkeypatch.setattr('app.services.agent_service.AgentService._call_model', call_model)

    response = client.post(
        '/api/v1/agent/chat',
        json={'content': case['content']},
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    data = response.json()['data']
    _assert_expected_response(
        data=data,
        expected=case['expected'],
        call_model=call_model,
    )
