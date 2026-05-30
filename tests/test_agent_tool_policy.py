from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.models.db_models import AccountRole, TaskStatus
from app.schemas.auth_context import CurrentUser
from app.services.agent_tool_registry import (
    AGENT_TOOL_REGISTRY,
    AgentToolPermissionLevel,
    AgentToolPolicy,
    AgentToolSideEffectLevel,
    AgentToolTenantScope,
)
from app.services.agent_tools import AgentTools


def _actor(
    *,
    role: AccountRole = AccountRole.USER,
    organization_id: str | None = settings.default_organization_id,
) -> CurrentUser:
    return CurrentUser(
        account_id='agent-policy-test-account',
        username='agent-policy-test-user',
        role=role,
        organization_id=organization_id,
    )


def test_agent_tool_registry_contains_all_dispatched_tools() -> None:
    dispatched_tool_names = {
        'get_workbench_summary',
        'get_client_project_context',
        'list_assessment_tasks',
        'get_assessment_task',
        'list_detection_reports',
        'get_detection_report',
        'summarize_detection_compliance',
        'list_compliance_evidence',
        'search_regulatory_limits',
        'search_standard_chunks',
        'search_guideline_chunks',
        'get_guideline_clause',
    }

    registered_tool_names = {spec.name for spec in AGENT_TOOL_REGISTRY.list_specs()}

    assert dispatched_tool_names <= registered_tool_names


def test_agent_tool_policy_allows_read_tool_for_user(db: Session) -> None:
    result = AgentTools.run_tool(
        db=db,
        actor=_actor(),
        tool_name='get_workbench_summary',
        arguments={},
    )

    assert result.tool_name == 'get_workbench_summary'
    assert result.result['scope']['organization_id'] == settings.default_organization_id


def test_agent_tool_policy_blocks_unregistered_tool(db: Session) -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentTools.run_tool(
            db=db,
            actor=_actor(),
            tool_name='missing_tool',
            arguments={},
        )

    assert exc_info.value.code == 'AGENT_TOOL_NOT_REGISTERED'


def test_agent_tool_policy_blocks_agent_disabled_admin_tool(db: Session) -> None:
    spec = AGENT_TOOL_REGISTRY.require('import_standard_manifest')

    assert spec.permission_level == AgentToolPermissionLevel.ADMIN
    assert spec.side_effect_level == AgentToolSideEffectLevel.WRITE
    assert spec.tenant_scope == AgentToolTenantScope.GLOBAL
    assert spec.agent_enabled is False

    with pytest.raises(EHSException) as exc_info:
        AgentTools.run_tool(
            db=db,
            actor=_actor(role=AccountRole.ADMIN, organization_id=None),
            tool_name='import_standard_manifest',
            arguments={},
        )

    assert exc_info.value.code == 'AGENT_TOOL_FORBIDDEN'


def test_agent_tool_policy_requires_organization_for_org_scoped_user_tool(db: Session) -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentTools.run_tool(
            db=db,
            actor=_actor(organization_id=None),
            tool_name='get_workbench_summary',
            arguments={},
        )

    assert exc_info.value.code == 'ACCOUNT_NO_ORG'


def test_agent_tool_schema_rejects_extra_arguments(db: Session) -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentTools.run_tool(
            db=db,
            actor=_actor(),
            tool_name='get_workbench_summary',
            arguments={'unexpected': True},
        )

    assert exc_info.value.code == 'AGENT_TOOL_ARGUMENT_INVALID'


def test_agent_tool_schema_rejects_invalid_limit(db: Session) -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentTools.run_tool(
            db=db,
            actor=_actor(),
            tool_name='list_assessment_tasks',
            arguments={'limit': 99},
        )

    assert exc_info.value.code == 'AGENT_TOOL_ARGUMENT_INVALID'


def test_agent_tool_schema_rejects_invalid_enum(db: Session) -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentTools.run_tool(
            db=db,
            actor=_actor(),
            tool_name='list_assessment_tasks',
            arguments={'status': 'BAD_STATUS'},
        )

    assert exc_info.value.code == 'AGENT_TOOL_ARGUMENT_INVALID'


def test_agent_tool_schema_normalizes_valid_arguments(db: Session) -> None:
    result = AgentTools.run_tool(
        db=db,
        actor=_actor(),
        tool_name='list_assessment_tasks',
        arguments={'status': TaskStatus.FAILED.value, 'limit': '3'},
    )

    assert result.arguments == {'status': TaskStatus.FAILED.value, 'limit': 3}


def test_agent_tool_result_schema_rejects_non_dict_output() -> None:
    with pytest.raises(EHSException) as exc_info:
        AgentToolPolicy.validate_result(
            tool_name='get_workbench_summary',
            result=[],  # type: ignore[arg-type]
        )

    assert exc_info.value.code == 'AGENT_TOOL_RESULT_INVALID'
