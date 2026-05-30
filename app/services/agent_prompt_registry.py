from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import EHSException
from app.dao.agent_dao import AgentPromptDAO
from app.models.db_models import AgentPrompt, AgentPromptScenario
from app.schemas.auth_context import CurrentUser
from app.schemas.pagination import Page
from app.services.access_control import is_org_admin, is_system_admin

DEFAULT_AGENT_SYSTEM_PROMPT = """你是 EHS 合规管理平台助手，服务对象包括企业和第三方检测机构。
你只能基于后端工具提供的数据回答，不允许编造任务、报告、标准或法规条款。
当前阶段你只能做只读分析，不能声称已经创建、删除、修改或重跑任何业务数据。
如果数据不足，请说明需要用户进入对应页面复核。
回答使用中文，结构清晰，优先给出可执行的下一步建议。"""

DEFAULT_AGENT_OUTPUT_CONTRACT = {
    'language': 'zh-CN',
    'must_use_tool_results_only': True,
    'must_not_create_formal_compliance_conclusion': True,
    'must_request_human_review_when_evidence_missing': True,
}


@dataclass(frozen=True, slots=True)
class AgentPromptDefinition:
    prompt_id: str
    name: str
    version: str
    scenario: str
    system_prompt: str
    developer_prompt: str | None
    output_contract: dict[str, Any]
    risk_notes: str | None
    is_registered: bool

    def to_metadata(self) -> dict[str, Any]:
        return {
            'prompt_id': self.prompt_id,
            'name': self.name,
            'version': self.version,
            'scenario': self.scenario,
            'output_contract': self.output_contract,
            'risk_notes': self.risk_notes,
            'is_registered': self.is_registered,
        }


class AgentPromptRegistry:
    @staticmethod
    def get_active_prompt(
        *,
        db: Session,
        scenario: AgentPromptScenario = AgentPromptScenario.AGENT_CHAT,
    ) -> AgentPromptDefinition:
        prompt = AgentPromptDAO(db).get_active_by_scenario(scenario.value)
        if prompt is None:
            return _fallback_prompt(scenario)
        return _prompt_definition(prompt)

    @staticmethod
    def list_prompts(
        *,
        db: Session,
        actor: CurrentUser,
        page: int,
        page_size: int,
        scenario: AgentPromptScenario | None = None,
        active_only: bool = False,
    ) -> Page[AgentPrompt]:
        if not (is_system_admin(actor) or is_org_admin(actor)):
            raise EHSException(
                '需要管理员权限查看 Agent 提示词注册表',
                code='AGENT_PROMPT_REGISTRY_FORBIDDEN',
                status_code=403,
            )
        filters: list[Any] = []
        if scenario is not None:
            filters.append(AgentPrompt.scenario == scenario)
        if active_only:
            filters.append(AgentPrompt.is_active == 1)
        items, total = AgentPromptDAO(db).list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[AgentPrompt.scenario.asc(), AgentPrompt.created_at.desc()],
            max_page_size=100,
        )
        return Page(items=items, total=total, page=page, page_size=page_size)


def _fallback_prompt(scenario: AgentPromptScenario) -> AgentPromptDefinition:
    return AgentPromptDefinition(
        prompt_id='fallback-agent-chat-v1',
        name='Agent Chat Default Prompt',
        version='v1',
        scenario=scenario.value,
        system_prompt=DEFAULT_AGENT_SYSTEM_PROMPT,
        developer_prompt=None,
        output_contract=DEFAULT_AGENT_OUTPUT_CONTRACT,
        risk_notes='Fallback prompt used when agent_prompts has no active row.',
        is_registered=False,
    )


def _prompt_definition(prompt: AgentPrompt) -> AgentPromptDefinition:
    return AgentPromptDefinition(
        prompt_id=prompt.id,
        name=prompt.name,
        version=prompt.version,
        scenario=prompt.scenario.value,
        system_prompt=prompt.system_prompt,
        developer_prompt=prompt.developer_prompt,
        output_contract=_parse_output_contract(prompt.output_contract_json),
        risk_notes=prompt.risk_notes,
        is_registered=True,
    )


def _parse_output_contract(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {'raw': value}
    return parsed if isinstance(parsed, dict) else {'value': parsed}
