from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.db_models import AgentMemoryScopeType, AgentMemoryType
from app.schemas.auth_context import CurrentUser
from app.services.agent_memory_service import AgentMemoryService
from app.services.agent_runtime_policy import AgentRuntimePolicy
from app.services.agent_tools import AgentToolResult

_SUMMARY_ITEM_LIMIT = 5
_SUMMARY_TEXT_LIMIT = 160


@dataclass(frozen=True, slots=True)
class AgentContextSnapshot:
    payload: dict[str, Any]
    context_hash: str
    prompt_hash: str
    risk_flags: list[str]


class AgentContextService:
    @staticmethod
    def build_snapshot(
        *,
        db: Session,
        actor: CurrentUser,
        session_id: str,
        user_message_id: str,
        user_content: str,
        runtime_policy: AgentRuntimePolicy,
        prompt_metadata: dict[str, Any],
        tool_results: list[AgentToolResult],
        route: str,
    ) -> AgentContextSnapshot:
        citation_memory_ids = [
            item.id
            for item in AgentMemoryService.list_memories(
                db=db,
                actor=actor,
                scope_type=AgentMemoryScopeType.SESSION,
                scope_id=session_id,
                memory_type=AgentMemoryType.CITATION,
                include_expired=False,
                limit=50,
            )
        ]
        tool_summaries = [
            {
                'tool_name': item.tool_name,
                'argument_keys': sorted(item.arguments),
                'result_summary': summarize_tool_result(item.result),
            }
            for item in tool_results
        ]
        payload = {
            'version': 'agent-context-v1',
            'route': route,
            'session_id': session_id,
            'user_message_id': user_message_id,
            'account_id': actor.account_id,
            'organization_id': actor.organization_id,
            'context_providers': [
                'current_message',
                'tool_results',
                'citation_memory',
                'runtime_policy',
            ],
            'current_message': {
                'content_hash': hash_text(user_content),
                'content_chars': len(user_content),
            },
            'tool_results': tool_summaries,
            'citation_memory_ids': citation_memory_ids,
            'evidence_ids': [],
            'policy': runtime_policy.to_metadata(),
            'prompt': prompt_metadata,
            'limits': {
                'max_context_chars': runtime_policy.max_context_chars,
                'max_retrieval_results': runtime_policy.max_retrieval_results,
            },
        }
        risk_flags = _risk_flags(payload=payload, tool_results=tool_results)
        payload['risk_flags'] = risk_flags
        context_hash = stable_hash(payload)
        payload['context_hash'] = context_hash
        prompt_hash = stable_hash(
            {
                'system_policy': runtime_policy.to_metadata(),
                'prompt': prompt_metadata,
                'user_content_hash': hash_text(user_content),
                'tool_summaries': tool_summaries,
                'citation_memory_ids': citation_memory_ids,
            }
        )
        return AgentContextSnapshot(
            payload=payload,
            context_hash=context_hash,
            prompt_hash=prompt_hash,
            risk_flags=risk_flags,
        )


def summarize_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {'keys': sorted(result)[:20]}
    raw_items = result.get('items')
    if isinstance(raw_items, list):
        summary['item_count'] = len(raw_items)
        summary['item_refs'] = [_item_ref(item) for item in raw_items[:_SUMMARY_ITEM_LIMIT]]
    for key in ('configured', 'error', 'query', 'limit'):
        if key in result:
            summary[key] = _short_value(result.get(key))
    if 'counts' in result and isinstance(result['counts'], dict):
        summary['counts'] = result['counts']
    return summary


def stable_hash(value: Any) -> str:
    return hash_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _item_ref(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {'type': type(item).__name__}
    keys = (
        'id',
        'task_id',
        'report_id',
        'chunk_id',
        'document_id',
        'dataset_id',
        'standard_code',
        'standard_name',
        'clause',
        'source_uri',
        'status',
    )
    return {key: _short_value(item.get(key)) for key in keys if item.get(key) is not None}


def _short_value(value: Any) -> Any:
    if value is None:
        return None
    text = ' '.join(str(value).split())
    return text if len(text) <= _SUMMARY_TEXT_LIMIT else f'{text[:_SUMMARY_TEXT_LIMIT]}...'


def _risk_flags(*, payload: dict[str, Any], tool_results: list[AgentToolResult]) -> list[str]:
    flags: list[str] = []
    if payload['limits']['max_context_chars'] < payload['current_message']['content_chars']:
        flags.append('USER_MESSAGE_EXCEEDS_CONTEXT_LIMIT')
    for item in tool_results:
        if item.tool_name in {'search_guideline_chunks', 'get_guideline_clause'}:
            result = item.result
            if result.get('configured') is False:
                flags.append('RAGFLOW_DISABLED')
            if result.get('items'):
                flags.append('EXTERNAL_RETRIEVAL_USED')
    return sorted(set(flags))
