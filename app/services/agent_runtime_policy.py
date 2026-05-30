from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.exceptions import EHSException
from app.schemas.auth_context import CurrentUser
from app.services.agent_tool_registry import (
    AGENT_TOOL_REGISTRY,
    AgentToolPermissionLevel,
    AgentToolRegistry,
    AgentToolSideEffectLevel,
)


@dataclass(frozen=True, slots=True)
class AgentRuntimePolicy:
    account_id: str
    organization_id: str | None
    allowed_tools: frozenset[str]
    max_tool_calls: int
    max_iterations: int
    timeout_seconds: float
    policy_id: str = 'agent-readonly-default'
    policy_version: str = 'v1'
    allowed_context_providers: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                'current_message',
                'recent_messages',
                'tool_results',
                'citation_memory',
                'runtime_policy',
            }
        )
    )
    allowed_retrieval_providers: frozenset[str] = field(
        default_factory=lambda: frozenset({'local_standard', 'ragflow'})
    )
    max_context_chars: int = 16000
    max_retrieval_results: int = 20
    read_only: bool = True
    can_write: bool = False
    can_export: bool = False
    requires_human_approval: bool = False

    def __post_init__(self) -> None:
        if self.max_tool_calls < 1:
            raise ValueError('max_tool_calls must be >= 1')
        if self.max_iterations < 1:
            raise ValueError('max_iterations must be >= 1')
        if self.timeout_seconds <= 0:
            raise ValueError('timeout_seconds must be > 0')
        if self.max_context_chars < 1:
            raise ValueError('max_context_chars must be >= 1')
        if self.max_retrieval_results < 1:
            raise ValueError('max_retrieval_results must be >= 1')

    @classmethod
    def from_actor(
        cls,
        actor: CurrentUser,
        *,
        registry: AgentToolRegistry | None = None,
    ) -> AgentRuntimePolicy:
        active_registry = registry or AGENT_TOOL_REGISTRY
        return cls(
            account_id=actor.account_id,
            organization_id=actor.organization_id,
            allowed_tools=_default_allowed_tools(active_registry),
            max_tool_calls=settings.agent_runtime_max_tool_calls,
            max_iterations=1,
            timeout_seconds=settings.agent_runtime_timeout_seconds,
            policy_id=settings.agent_runtime_policy_id.strip() or 'agent-readonly-default',
            policy_version=settings.agent_runtime_policy_version.strip() or 'v1',
            max_context_chars=settings.agent_runtime_max_context_chars,
            max_retrieval_results=settings.agent_runtime_max_retrieval_results,
            read_only=True,
            can_write=False,
            can_export=False,
            requires_human_approval=False,
        )

    def to_metadata(self) -> dict[str, object]:
        return {
            'policy_id': self.policy_id,
            'policy_version': self.policy_version,
            'account_id': self.account_id,
            'organization_id': self.organization_id,
            'allowed_tools': sorted(self.allowed_tools),
            'allowed_context_providers': sorted(self.allowed_context_providers),
            'allowed_retrieval_providers': sorted(self.allowed_retrieval_providers),
            'max_tool_calls': self.max_tool_calls,
            'max_iterations': self.max_iterations,
            'timeout_seconds': self.timeout_seconds,
            'max_context_chars': self.max_context_chars,
            'max_retrieval_results': self.max_retrieval_results,
            'read_only': self.read_only,
            'can_write': self.can_write,
            'can_export': self.can_export,
            'requires_human_approval': self.requires_human_approval,
        }


class AgentSandbox:
    @staticmethod
    def ensure_run_allowed(policy: AgentRuntimePolicy) -> None:
        if policy.requires_human_approval:
            raise EHSException(
                '当前 Agent 运行策略需要人工确认',
                code='AGENT_RUNTIME_APPROVAL_REQUIRED',
                status_code=403,
            )

    @staticmethod
    def ensure_iteration_allowed(*, policy: AgentRuntimePolicy, iteration_index: int) -> None:
        if iteration_index > policy.max_iterations:
            raise EHSException(
                'Agent 运行轮次超过策略限制',
                code='AGENT_RUNTIME_ITERATION_LIMIT_EXCEEDED',
                status_code=429,
                details={
                    'max_iterations': policy.max_iterations,
                    'iteration_index': iteration_index,
                },
            )

    @staticmethod
    def ensure_deadline(*, policy: AgentRuntimePolicy, started_at: float) -> None:
        elapsed_seconds = time.perf_counter() - started_at
        if elapsed_seconds <= policy.timeout_seconds:
            return
        raise EHSException(
            'Agent 运行超时',
            code='AGENT_RUNTIME_TIMEOUT',
            status_code=504,
            details={
                'timeout_seconds': policy.timeout_seconds,
                'elapsed_seconds': round(elapsed_seconds, 3),
            },
        )

    @staticmethod
    def before_tool_call(
        *,
        policy: AgentRuntimePolicy,
        tool_name: str,
        call_index: int,
        started_at: float,
        registry: AgentToolRegistry | None = None,
    ) -> None:
        AgentSandbox.ensure_deadline(policy=policy, started_at=started_at)
        if call_index > policy.max_tool_calls:
            raise EHSException(
                'Agent 工具调用次数超过策略限制',
                code='AGENT_RUNTIME_TOOL_LIMIT_EXCEEDED',
                status_code=429,
                details={'max_tool_calls': policy.max_tool_calls, 'tool_name': tool_name},
            )

        active_registry = registry or AGENT_TOOL_REGISTRY
        spec = active_registry.require(tool_name)
        details = {
            'tool_name': tool_name,
            'permission_level': spec.permission_level.value,
            'side_effect_level': spec.side_effect_level.value,
        }

        if tool_name not in policy.allowed_tools:
            raise EHSException(
                'Agent 运行策略不允许调用该工具',
                code='AGENT_RUNTIME_TOOL_FORBIDDEN',
                status_code=403,
                details=details,
            )
        if policy.read_only and (
            spec.permission_level != AgentToolPermissionLevel.READ
            or spec.side_effect_level != AgentToolSideEffectLevel.NONE
        ):
            raise EHSException(
                '当前 Agent 运行策略为只读，禁止调用有副作用工具',
                code='AGENT_RUNTIME_READ_ONLY',
                status_code=403,
                details=details,
            )
        if not policy.can_write and (
            spec.permission_level == AgentToolPermissionLevel.WRITE
            or spec.side_effect_level == AgentToolSideEffectLevel.WRITE
        ):
            raise EHSException(
                '当前 Agent 运行策略禁止写操作',
                code='AGENT_RUNTIME_WRITE_FORBIDDEN',
                status_code=403,
                details=details,
            )
        if not policy.can_export and (
            spec.permission_level == AgentToolPermissionLevel.EXPORT
            or spec.side_effect_level == AgentToolSideEffectLevel.EXTERNAL
        ):
            raise EHSException(
                '当前 Agent 运行策略禁止导出或外部副作用操作',
                code='AGENT_RUNTIME_EXPORT_FORBIDDEN',
                status_code=403,
                details=details,
            )
        if spec.requires_approval:
            raise EHSException(
                '该工具需要人工确认后才能调用',
                code='AGENT_RUNTIME_TOOL_APPROVAL_REQUIRED',
                status_code=403,
                details=details,
            )


def _default_allowed_tools(registry: AgentToolRegistry) -> frozenset[str]:
    return frozenset(
        spec.name
        for spec in registry.list_specs()
        if spec.agent_enabled
        and not spec.requires_approval
        and spec.permission_level == AgentToolPermissionLevel.READ
        and spec.side_effect_level == AgentToolSideEffectLevel.NONE
    )
