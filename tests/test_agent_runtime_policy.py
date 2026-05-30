from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import EHSException
from app.models.db_models import AccountRole, AgentRun, AgentSecurityEvent, AgentToolCall
from app.schemas.auth_context import CurrentUser
from app.services.agent_runtime_policy import AgentRuntimePolicy, AgentSandbox


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _actor() -> CurrentUser:
    return CurrentUser(
        account_id='agent-runtime-test-account',
        username='agent-runtime-test-user',
        role=AccountRole.USER,
        organization_id=settings.default_organization_id,
    )


def _policy(**overrides: object) -> AgentRuntimePolicy:
    values = {
        'account_id': 'agent-runtime-test-account',
        'organization_id': settings.default_organization_id,
        'allowed_tools': frozenset({'get_workbench_summary'}),
        'max_tool_calls': 3,
        'max_iterations': 1,
        'timeout_seconds': 30.0,
        'read_only': True,
        'can_write': False,
        'can_export': False,
        'requires_human_approval': False,
    }
    values.update(overrides)
    return AgentRuntimePolicy(**values)  # type: ignore[arg-type]


def test_agent_runtime_policy_defaults_to_read_only_registered_tools() -> None:
    policy = AgentRuntimePolicy.from_actor(_actor())

    assert policy.read_only is True
    assert policy.can_write is False
    assert policy.can_export is False
    assert 'get_workbench_summary' in policy.allowed_tools
    assert 'search_standard_chunks' in policy.allowed_tools
    assert 'import_standard_manifest' not in policy.allowed_tools


def test_agent_sandbox_blocks_disallowed_tool() -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentSandbox.before_tool_call(
            policy=_policy(),
            tool_name='search_standard_chunks',
            call_index=1,
            started_at=time.perf_counter(),
        )

    assert exc_info.value.code == 'AGENT_RUNTIME_TOOL_FORBIDDEN'


def test_agent_sandbox_blocks_tool_call_limit() -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentSandbox.before_tool_call(
            policy=_policy(max_tool_calls=1),
            tool_name='get_workbench_summary',
            call_index=2,
            started_at=time.perf_counter(),
        )

    assert exc_info.value.code == 'AGENT_RUNTIME_TOOL_LIMIT_EXCEEDED'


def test_agent_sandbox_blocks_iteration_limit() -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentSandbox.ensure_iteration_allowed(policy=_policy(max_iterations=1), iteration_index=2)

    assert exc_info.value.code == 'AGENT_RUNTIME_ITERATION_LIMIT_EXCEEDED'


def test_agent_sandbox_blocks_timeout() -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentSandbox.ensure_deadline(
            policy=_policy(timeout_seconds=0.001),
            started_at=time.perf_counter() - 1,
        )

    assert exc_info.value.code == 'AGENT_RUNTIME_TIMEOUT'


def test_agent_sandbox_blocks_read_only_side_effect_tool() -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentSandbox.before_tool_call(
            policy=_policy(allowed_tools=frozenset({'import_standard_manifest'})),
            tool_name='import_standard_manifest',
            call_index=1,
            started_at=time.perf_counter(),
        )

    assert exc_info.value.code == 'AGENT_RUNTIME_READ_ONLY'


def test_agent_chat_respects_runtime_tool_limit(
    client: TestClient,
    user_token: str,
    db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, 'agent_runtime_max_tool_calls', 1)

    response = client.post(
        '/api/v1/agent/chat',
        json={'content': '最近失败的任务是什么？'},
        headers=_auth(user_token),
    )

    assert response.status_code == 429
    body = response.json()
    assert body['code'] == 'AGENT_RUNTIME_TOOL_LIMIT_EXCEEDED'

    run = db.query(AgentRun).order_by(AgentRun.created_at.desc()).first()
    assert run is not None
    assert run.status.value == 'FAILED'
    tool_calls = db.query(AgentToolCall).filter_by(run_id=run.id).order_by(AgentToolCall.created_at).all()
    assert [item.policy_decision for item in tool_calls] == ['allowed', 'blocked']

    security_event = db.query(AgentSecurityEvent).filter_by(run_id=run.id).one()
    assert security_event.event_type == 'TOOL_BLOCKED'
    assert security_event.severity == 'HIGH'
    assert security_event.tool_name == 'list_assessment_tasks'

    events_response = client.get('/api/v1/agent/security-events', headers=_auth(user_token))
    assert events_response.status_code == 200
    events = events_response.json()['data']['items']
    assert any(item['id'] == security_event.id for item in events)
