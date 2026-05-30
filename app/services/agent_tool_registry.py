from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.exceptions import EHSException
from app.models.db_models import AccountRole, ReportStatus, ReportType, TaskStatus
from app.schemas.auth_context import CurrentUser
from app.services.access_control import ensure_user_has_organization, is_system_admin


class AgentToolPermissionLevel(str, Enum):
    READ = 'READ'
    DRAFT = 'DRAFT'
    WRITE = 'WRITE'
    EXPORT = 'EXPORT'
    ADMIN = 'ADMIN'


class AgentToolSideEffectLevel(str, Enum):
    NONE = 'NONE'
    DRAFT = 'DRAFT'
    WRITE = 'WRITE'
    EXTERNAL = 'EXTERNAL'


class AgentToolTenantScope(str, Enum):
    ORGANIZATION = 'ORGANIZATION'
    GLOBAL = 'GLOBAL'


class AgentToolArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')


class NoToolArguments(AgentToolArguments):
    pass


class GetClientProjectContextArguments(AgentToolArguments):
    query: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)


class ListAssessmentTasksArguments(AgentToolArguments):
    status: TaskStatus | None = None
    context_query: str | None = Field(default=None, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)


class GetAssessmentTaskArguments(AgentToolArguments):
    task_id: str = Field(min_length=1, max_length=64)


class ListDetectionReportsArguments(AgentToolArguments):
    status: ReportStatus | Literal['PENDING_CALCULATION'] | None = None
    report_type: ReportType | None = None
    context_query: str | None = Field(default=None, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)


class GetDetectionReportArguments(AgentToolArguments):
    report_id: str = Field(min_length=1, max_length=64)


class SummarizeDetectionComplianceArguments(AgentToolArguments):
    context_query: str | None = Field(default=None, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)


class ListComplianceEvidenceArguments(AgentToolArguments):
    report_id: str | None = Field(default=None, min_length=1, max_length=64)
    result_id: str | None = Field(default=None, min_length=1, max_length=64)
    context_query: str | None = Field(default=None, max_length=8000)
    limit: int = Field(default=8, ge=1, le=20)


class SearchRegulatoryLimitsArguments(AgentToolArguments):
    query: str = Field(min_length=1, max_length=8000)
    limit: int = Field(default=5, ge=1, le=20)


class SearchStandardChunksArguments(AgentToolArguments):
    query: str = Field(min_length=1, max_length=8000)
    standard_code: str | None = Field(default=None, max_length=64)
    domain: str | None = Field(default=None, max_length=64)
    service_type: str | None = Field(default=None, max_length=64)
    include_sensitive: bool = False
    limit: int = Field(default=5, ge=1, le=20)


class SearchGuidelineChunksArguments(AgentToolArguments):
    query: str = Field(min_length=1, max_length=8000)
    standard_code: str | None = Field(default=None, max_length=64)
    domain: str | None = Field(default=None, max_length=64)
    service_type: str | None = Field(default=None, max_length=64)
    document_id: str | None = Field(default=None, max_length=128)
    limit: int = Field(default=5, ge=1, le=20)


class GetGuidelineClauseArguments(AgentToolArguments):
    standard_code: str = Field(min_length=1, max_length=64)
    clause: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=5, ge=1, le=20)


@dataclass(frozen=True, slots=True)
class AgentToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    permission_level: AgentToolPermissionLevel
    side_effect_level: AgentToolSideEffectLevel
    tool_version: str = 'v1'
    risk_level: str = 'LOW'
    tenant_scope: AgentToolTenantScope = AgentToolTenantScope.ORGANIZATION
    timeout_seconds: int = 10
    allowed_roles: frozenset[AccountRole] = field(default_factory=lambda: frozenset(AccountRole))
    requires_approval: bool = False
    agent_enabled: bool = True
    commercial_enabled: bool = True


class AgentToolRegistry:
    def __init__(self, specs: Iterable[AgentToolSpec] = ()) -> None:
        self._specs: dict[str, AgentToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: AgentToolSpec) -> None:
        tool_name = spec.name.strip()
        if not tool_name:
            raise ValueError('agent tool name is required')
        if tool_name in self._specs:
            raise ValueError(f'duplicate agent tool spec: {tool_name}')
        if tool_name != spec.name:
            spec = AgentToolSpec(
                name=tool_name,
                description=spec.description,
                input_model=spec.input_model,
                input_schema=spec.input_schema,
                output_schema=spec.output_schema,
                permission_level=spec.permission_level,
                side_effect_level=spec.side_effect_level,
                tool_version=spec.tool_version,
                risk_level=spec.risk_level,
                tenant_scope=spec.tenant_scope,
                timeout_seconds=spec.timeout_seconds,
                allowed_roles=spec.allowed_roles,
                requires_approval=spec.requires_approval,
                agent_enabled=spec.agent_enabled,
                commercial_enabled=spec.commercial_enabled,
            )
        self._specs[tool_name] = spec

    def get(self, tool_name: str) -> AgentToolSpec | None:
        return self._specs.get(tool_name.strip())

    def require(self, tool_name: str) -> AgentToolSpec:
        spec = self.get(tool_name)
        if spec is None:
            raise EHSException(
                'Agent 工具未注册',
                code='AGENT_TOOL_NOT_REGISTERED',
                status_code=400,
                details={'tool_name': tool_name},
            )
        return spec

    def list_specs(self) -> list[AgentToolSpec]:
        return list(self._specs.values())


class AgentToolPolicy:
    @staticmethod
    def prepare_call(
        *,
        actor: CurrentUser,
        tool_name: str,
        arguments: dict[str, Any],
        registry: AgentToolRegistry | None = None,
    ) -> dict[str, Any]:
        active_registry = registry or AGENT_TOOL_REGISTRY
        spec = active_registry.require(tool_name)
        validated_arguments = AgentToolPolicy.validate_arguments(
            spec=spec,
            arguments=arguments,
        )
        AgentToolPolicy.ensure_allowed(
            actor=actor,
            tool_name=tool_name,
            arguments=validated_arguments,
            registry=active_registry,
        )
        return validated_arguments

    @staticmethod
    def validate_arguments(
        *,
        spec: AgentToolSpec,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            model = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            raise EHSException(
                'Agent 工具入参无效',
                code='AGENT_TOOL_ARGUMENT_INVALID',
                status_code=400,
                details={
                    'tool_name': spec.name,
                    'errors': exc.errors(include_url=False),
                },
            ) from exc
        return model.model_dump(mode='json', exclude_none=True)

    @staticmethod
    def validate_result(
        *,
        tool_name: str,
        result: dict[str, Any],
        registry: AgentToolRegistry | None = None,
    ) -> dict[str, Any]:
        active_registry = registry or AGENT_TOOL_REGISTRY
        active_registry.require(tool_name)
        if not isinstance(result, dict):
            raise EHSException(
                'Agent 工具输出结构无效',
                code='AGENT_TOOL_RESULT_INVALID',
                status_code=500,
                details={'tool_name': tool_name},
            )
        return result

    @staticmethod
    def ensure_allowed(
        *,
        actor: CurrentUser,
        tool_name: str,
        arguments: dict[str, Any],
        registry: AgentToolRegistry | None = None,
    ) -> AgentToolSpec:
        active_registry = registry or AGENT_TOOL_REGISTRY
        spec = active_registry.require(tool_name)
        details = {
            'tool_name': spec.name,
            'tool_version': spec.tool_version,
            'permission_level': spec.permission_level.value,
            'side_effect_level': spec.side_effect_level.value,
            'risk_level': spec.risk_level,
            'argument_keys': sorted(arguments),
        }

        if not spec.agent_enabled:
            raise EHSException(
                'Agent 不允许直接调用该工具',
                code='AGENT_TOOL_FORBIDDEN',
                status_code=403,
                details=details,
            )
        if actor.role not in spec.allowed_roles:
            raise EHSException(
                '当前角色不允许调用该 Agent 工具',
                code='AGENT_TOOL_ROLE_FORBIDDEN',
                status_code=403,
                details=details | {'role': actor.role.value},
            )
        if _requires_human_approval(spec):
            raise EHSException(
                '该 Agent 工具需要人工确认后才能调用',
                code='AGENT_TOOL_APPROVAL_REQUIRED',
                status_code=403,
                details=details,
            )
        if spec.tenant_scope == AgentToolTenantScope.ORGANIZATION and not is_system_admin(actor):
            ensure_user_has_organization(actor)
        return spec


def _requires_human_approval(spec: AgentToolSpec) -> bool:
    if spec.requires_approval:
        return True
    if spec.permission_level in {
        AgentToolPermissionLevel.WRITE,
        AgentToolPermissionLevel.EXPORT,
        AgentToolPermissionLevel.ADMIN,
    }:
        return True
    return spec.side_effect_level in {
        AgentToolSideEffectLevel.WRITE,
        AgentToolSideEffectLevel.EXTERNAL,
    }


def _input_schema(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()


def _read_tool(
    *,
    name: str,
    description: str,
    input_model: type[BaseModel] = NoToolArguments,
    tenant_scope: AgentToolTenantScope = AgentToolTenantScope.ORGANIZATION,
) -> AgentToolSpec:
    return AgentToolSpec(
        name=name,
        description=description,
        input_model=input_model,
        input_schema=_input_schema(input_model),
        output_schema={'type': 'object'},
        permission_level=AgentToolPermissionLevel.READ,
        side_effect_level=AgentToolSideEffectLevel.NONE,
        tenant_scope=tenant_scope,
    )


_DEFAULT_TOOL_SPECS = [
    _read_tool(
        name='get_workbench_summary',
        description='Read visible workbench counts and recent records.',
    ),
    _read_tool(
        name='get_client_project_context',
        description='Read task and report context filtered by client or project terms.',
        input_model=GetClientProjectContextArguments,
    ),
    _read_tool(
        name='list_assessment_tasks',
        description='Read assessment task list for the current visible scope.',
        input_model=ListAssessmentTasksArguments,
    ),
    _read_tool(
        name='get_assessment_task',
        description='Read one assessment task by id after organization scope checks.',
        input_model=GetAssessmentTaskArguments,
    ),
    _read_tool(
        name='list_detection_reports',
        description='Read detection report list for the current visible scope.',
        input_model=ListDetectionReportsArguments,
    ),
    _read_tool(
        name='get_detection_report',
        description='Read one detection report by id after organization scope checks.',
        input_model=GetDetectionReportArguments,
    ),
    _read_tool(
        name='summarize_detection_compliance',
        description='Read detection compliance summary for the current visible scope.',
        input_model=SummarizeDetectionComplianceArguments,
    ),
    _read_tool(
        name='list_compliance_evidence',
        description='Read graph-lite compliance evidence chain for visible detection results.',
        input_model=ListComplianceEvidenceArguments,
    ),
    _read_tool(
        name='search_regulatory_limits',
        description='Search regulatory limit metadata available to the system.',
        input_model=SearchRegulatoryLimitsArguments,
        tenant_scope=AgentToolTenantScope.GLOBAL,
    ),
    _read_tool(
        name='search_standard_chunks',
        description='Search standard chunk metadata and permitted excerpts.',
        input_model=SearchStandardChunksArguments,
        tenant_scope=AgentToolTenantScope.GLOBAL,
    ),
    _read_tool(
        name='search_guideline_chunks',
        description='Search authorized external guideline chunks through RAGFlow.',
        input_model=SearchGuidelineChunksArguments,
        tenant_scope=AgentToolTenantScope.GLOBAL,
    ),
    _read_tool(
        name='get_guideline_clause',
        description='Search one authorized external guideline clause through RAGFlow.',
        input_model=GetGuidelineClauseArguments,
        tenant_scope=AgentToolTenantScope.GLOBAL,
    ),
    AgentToolSpec(
        name='import_standard_manifest',
        description='Import standard manifest metadata through the admin workflow.',
        input_model=NoToolArguments,
        input_schema=_input_schema(NoToolArguments),
        output_schema={'type': 'object'},
        permission_level=AgentToolPermissionLevel.ADMIN,
        side_effect_level=AgentToolSideEffectLevel.WRITE,
        risk_level='HIGH',
        tenant_scope=AgentToolTenantScope.GLOBAL,
        allowed_roles=frozenset({AccountRole.ADMIN}),
        requires_approval=True,
        agent_enabled=False,
    ),
]

AGENT_TOOL_REGISTRY = AgentToolRegistry(_DEFAULT_TOOL_SPECS)
