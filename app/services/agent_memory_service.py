from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import EHSException
from app.dao.agent_memory_dao import AgentMemoryDAO, AgentMemoryEventDAO
from app.models.base import audit_now_naive
from app.models.db_models import (
    AgentMemory,
    AgentMemoryEvent,
    AgentMemoryScopeType,
    AgentMemorySourceType,
    AgentMemoryType,
)
from app.schemas.auth_context import CurrentUser
from app.services.access_control import (
    ensure_organization_scope,
    ensure_user_has_organization,
    is_system_admin,
)


@dataclass(frozen=True, slots=True)
class AgentMemoryUpsertResult:
    memory: AgentMemory
    event: AgentMemoryEvent
    created: bool


class AgentMemoryService:
    @staticmethod
    def upsert_memory(
        *,
        db: Session,
        actor: CurrentUser,
        scope_type: AgentMemoryScopeType,
        scope_id: str | None,
        memory_type: AgentMemoryType,
        content: str,
        source_type: AgentMemorySourceType,
        source_id: str | None,
        organization_id: str | None = None,
        account_id: str | None = None,
        confidence: Decimal | None = None,
        is_verified: bool = False,
        expires_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        event_source_type: AgentMemorySourceType | None = None,
        event_source_id: str | None = None,
        event_metadata: dict[str, Any] | None = None,
    ) -> AgentMemoryUpsertResult:
        normalized_content = _compact_text(content)
        if not normalized_content:
            raise EHSException(
                'Agent memory content is required',
                code='AGENT_MEMORY_CONTENT_REQUIRED',
                status_code=400,
            )

        memory_organization_id = _resolve_memory_organization_id(
            actor=actor,
            organization_id=organization_id,
        )
        if not is_system_admin(actor) and account_id not in (None, actor.account_id):
            raise EHSException(
                'Agent memory account scope is forbidden',
                code='AGENT_MEMORY_ACCOUNT_FORBIDDEN',
                status_code=403,
            )
        memory_account_id = actor.account_id if account_id is None else account_id
        memory, created = AgentMemoryDAO(db).upsert(
            organization_id=memory_organization_id,
            account_id=memory_account_id,
            scope_type=scope_type,
            scope_id=scope_id,
            memory_type=memory_type,
            content=normalized_content,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            is_verified=is_verified,
            expires_at=expires_at,
            metadata_json=_json_dump(metadata),
        )
        event = AgentMemoryEventDAO(db).add_event(
            memory_id=memory.id,
            event_type='CREATED' if created else 'UPDATED',
            actor_account_id=actor.account_id,
            source_type=event_source_type or source_type,
            source_id=event_source_id if event_source_type is not None else source_id,
            metadata_json=_json_dump(event_metadata),
        )
        db.commit()
        db.refresh(memory)
        db.refresh(event)
        return AgentMemoryUpsertResult(memory=memory, event=event, created=created)

    @staticmethod
    def list_memories(
        *,
        db: Session,
        actor: CurrentUser,
        organization_id: str | None = None,
        scope_type: AgentMemoryScopeType | None = None,
        scope_id: str | None = None,
        memory_type: AgentMemoryType | None = None,
        limit: int = 50,
    ) -> list[AgentMemory]:
        visible_organization_id = _resolve_memory_organization_id(
            actor=actor,
            organization_id=organization_id,
        )
        include_all_organizations = is_system_admin(actor) and organization_id is None
        filters = AgentMemoryDAO.visible_filters(
            organization_id=visible_organization_id,
            account_id=None if is_system_admin(actor) else actor.account_id,
            include_all_organizations=include_all_organizations,
        )
        filters.append(
            or_(
                AgentMemory.expires_at.is_(None),
                AgentMemory.expires_at > audit_now_naive(),
            )
        )
        if scope_type is not None:
            filters.append(AgentMemory.scope_type == scope_type)
        if scope_id is not None:
            filters.append(AgentMemory.scope_id == scope_id)
        if memory_type is not None:
            filters.append(AgentMemory.memory_type == memory_type)

        return AgentMemoryDAO(db).list_visible(
            filters=filters,
            limit=max(1, min(limit, 100)),
        )

    @staticmethod
    def record_standard_chunk_citations(
        *,
        db: Session,
        actor: CurrentUser,
        session_id: str,
        tool_result: dict[str, Any],
        tool_call_id: str,
        run_id: str,
    ) -> list[AgentMemory]:
        raw_items = tool_result.get('items')
        if not isinstance(raw_items, list):
            return []

        memories: list[AgentMemory] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            metadata = _standard_chunk_citation_metadata(raw_item)
            source_id = metadata.get('source_id')
            content = _standard_chunk_citation_content(metadata)
            if not source_id or not content:
                continue
            result = AgentMemoryService.upsert_memory(
                db=db,
                actor=actor,
                organization_id=actor.organization_id,
                scope_type=AgentMemoryScopeType.SESSION,
                scope_id=session_id,
                memory_type=AgentMemoryType.CITATION,
                content=content,
                source_type=AgentMemorySourceType.STANDARD_CHUNK,
                source_id=source_id,
                confidence=Decimal('1.0000'),
                is_verified=False,
                metadata=metadata,
                event_source_type=AgentMemorySourceType.TOOL_CALL,
                event_source_id=tool_call_id,
                event_metadata={
                    'run_id': run_id,
                    'tool_call_id': tool_call_id,
                    'tool_name': 'search_standard_chunks',
                },
            )
            memories.append(result.memory)
        return memories

    @staticmethod
    def record_ragflow_chunk_citations(
        *,
        db: Session,
        actor: CurrentUser,
        session_id: str,
        tool_result: dict[str, Any],
        tool_call_id: str,
        run_id: str,
        tool_name: str,
    ) -> list[AgentMemory]:
        raw_items = tool_result.get('items')
        if not isinstance(raw_items, list):
            return []

        memories: list[AgentMemory] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            metadata = _ragflow_chunk_citation_metadata(raw_item)
            source_id = metadata.get('source_id')
            content = _ragflow_chunk_citation_content(metadata)
            if not source_id or not content:
                continue
            result = AgentMemoryService.upsert_memory(
                db=db,
                actor=actor,
                organization_id=actor.organization_id,
                scope_type=AgentMemoryScopeType.SESSION,
                scope_id=session_id,
                memory_type=AgentMemoryType.CITATION,
                content=content,
                source_type=AgentMemorySourceType.STANDARD_CHUNK,
                source_id=source_id,
                confidence=Decimal('1.0000'),
                is_verified=False,
                metadata=metadata,
                event_source_type=AgentMemorySourceType.TOOL_CALL,
                event_source_id=tool_call_id,
                event_metadata={
                    'run_id': run_id,
                    'tool_call_id': tool_call_id,
                    'tool_name': tool_name,
                },
            )
            memories.append(result.memory)
        return memories


def _resolve_memory_organization_id(
    *,
    actor: CurrentUser,
    organization_id: str | None,
) -> str | None:
    if is_system_admin(actor):
        return organization_id
    if organization_id is None:
        return ensure_user_has_organization(actor)
    ensure_organization_scope(actor, organization_id)
    return organization_id


def _standard_chunk_citation_metadata(item: dict[str, Any]) -> dict[str, Any]:
    chunk_id = _str_or_none(item.get('chunk_id'))
    standard_chunk_id = _str_or_none(item.get('id'))
    source_id = chunk_id or standard_chunk_id
    return _drop_none(
        {
            'standard_code': _str_or_none(item.get('standard_code')),
            'standard_name': _str_or_none(item.get('standard_name')),
            'clause': _str_or_none(item.get('clause')),
            'page_start': _int_or_none(item.get('page_start')),
            'page_end': _int_or_none(item.get('page_end')),
            'document_id': _str_or_none(item.get('document_id')),
            'chunk_id': chunk_id,
            'standard_chunk_id': standard_chunk_id,
            'source_type': AgentMemorySourceType.STANDARD_CHUNK.value,
            'source_id': source_id,
        }
    )


def _standard_chunk_citation_content(metadata: dict[str, Any]) -> str:
    parts = [
        _compact_text(metadata.get('standard_code')),
        _compact_text(metadata.get('clause')),
        _page_label(
            page_start=metadata.get('page_start'),
            page_end=metadata.get('page_end'),
        ),
    ]
    content = ' '.join(part for part in parts if part)
    if content:
        return content[:500]
    return _compact_text(metadata.get('source_id'))[:500]


def _ragflow_chunk_citation_metadata(item: dict[str, Any]) -> dict[str, Any]:
    provider = _str_or_none(item.get('provider')) or 'ragflow'
    dataset_id = _str_or_none(item.get('dataset_id'))
    document_id = _str_or_none(item.get('document_id'))
    chunk_id = _str_or_none(item.get('chunk_id'))
    source_uri = _str_or_none(item.get('source_uri'))
    source_id = _ragflow_source_id(
        provider=provider,
        dataset_id=dataset_id,
        document_id=document_id,
        chunk_id=chunk_id,
        source_uri=source_uri,
    )
    return _drop_none(
        {
            'provider': provider,
            'rag_provider': provider,
            'dataset_id': dataset_id,
            'document_id': document_id,
            'chunk_id': chunk_id,
            'standard_code': _str_or_none(item.get('standard_code')),
            'standard_name': _str_or_none(item.get('standard_name')),
            'clause': _str_or_none(item.get('clause')),
            'page': _int_or_none(item.get('page')),
            'version': _str_or_none(item.get('version')),
            'effective_date': _str_or_none(item.get('effective_date')),
            'source_uri': source_uri,
            'score': _float_or_none(item.get('score')),
            'source_type': 'RAGFLOW_CHUNK',
            'source_id': source_id,
        }
    )


def _ragflow_chunk_citation_content(metadata: dict[str, Any]) -> str:
    parts = [
        _compact_text(metadata.get('standard_code')),
        _compact_text(metadata.get('clause')),
        _page_label(page_start=metadata.get('page'), page_end=None),
    ]
    content = ' '.join(part for part in parts if part)
    if content:
        return content[:500]
    fallback = ' '.join(
        part
        for part in [
            _compact_text(metadata.get('document_id')),
            _compact_text(metadata.get('chunk_id')),
        ]
        if part
    )
    return (fallback or _compact_text(metadata.get('source_id')))[:500]


def _ragflow_source_id(
    *,
    provider: str,
    dataset_id: str | None,
    document_id: str | None,
    chunk_id: str | None,
    source_uri: str | None,
) -> str | None:
    raw = ':'.join(
        part
        for part in [provider, dataset_id, document_id, chunk_id]
        if part
    )
    if not raw:
        raw = source_uri or ''
    if not raw:
        return None
    return raw if len(raw) <= 128 else f'{provider}:{sha256(raw.encode("utf-8")).hexdigest()}'


def _page_label(*, page_start: Any, page_end: Any) -> str:
    if page_start is None:
        return ''
    if page_end is None or page_end == page_start:
        return f'p.{page_start}'
    return f'p.{page_start}-{page_end}'


def _json_dump(value: dict[str, Any] | None) -> str | None:
    if not value:
        return None
    return json.dumps(_drop_none(value), ensure_ascii=False, sort_keys=True, default=str)


def _compact_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _str_or_none(value: Any) -> str | None:
    text = _compact_text(value)
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
