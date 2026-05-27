from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import (
    AgentMemory,
    AgentMemoryEvent,
    AgentMemoryScopeType,
    AgentMemorySourceType,
    AgentMemoryType,
)


class AgentMemoryDAO(BaseRepository[AgentMemory]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AgentMemory)

    def find_existing(
        self,
        *,
        organization_id: str | None,
        scope_type: AgentMemoryScopeType,
        scope_id: str | None,
        memory_type: AgentMemoryType,
        source_type: AgentMemorySourceType,
        source_id: str | None,
    ) -> AgentMemory | None:
        stmt = select(AgentMemory).where(
            AgentMemory.organization_id.is_(None)
            if organization_id is None
            else AgentMemory.organization_id == organization_id,
            AgentMemory.scope_type == scope_type,
            AgentMemory.scope_id.is_(None) if scope_id is None else AgentMemory.scope_id == scope_id,
            AgentMemory.memory_type == memory_type,
            AgentMemory.source_type == source_type,
            AgentMemory.source_id.is_(None) if source_id is None else AgentMemory.source_id == source_id,
            AgentMemory.deleted_at.is_(None),
        )
        return self.session.scalars(stmt).one_or_none()

    def upsert(
        self,
        *,
        organization_id: str | None,
        account_id: str | None,
        scope_type: AgentMemoryScopeType,
        scope_id: str | None,
        memory_type: AgentMemoryType,
        content: str,
        source_type: AgentMemorySourceType,
        source_id: str | None,
        confidence: Decimal | None,
        is_verified: bool,
        expires_at: datetime | None,
        metadata_json: str | None,
    ) -> tuple[AgentMemory, bool]:
        existing = self.find_existing(
            organization_id=organization_id,
            scope_type=scope_type,
            scope_id=scope_id,
            memory_type=memory_type,
            source_type=source_type,
            source_id=source_id,
        )
        if existing is not None:
            existing.account_id = account_id
            existing.content = content
            existing.confidence = confidence
            existing.is_verified = 1 if is_verified else 0
            existing.expires_at = expires_at
            existing.metadata_json = metadata_json
            existing.updated_at = audit_now_naive()
            self.session.flush()
            return existing, False

        entity = AgentMemory(
            organization_id=organization_id,
            account_id=account_id,
            scope_type=scope_type,
            scope_id=scope_id,
            memory_type=memory_type,
            content=content,
            source_type=source_type,
            source_id=source_id,
            confidence=confidence,
            is_verified=1 if is_verified else 0,
            expires_at=expires_at,
            metadata_json=metadata_json,
        )
        self.session.add(entity)
        self.session.flush()
        return entity, True

    def list_visible(
        self,
        *,
        filters: Sequence[ColumnElement[bool]],
        limit: int,
    ) -> list[AgentMemory]:
        stmt = (
            select(AgentMemory)
            .where(*filters)
            .order_by(AgentMemory.updated_at.desc(), AgentMemory.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    @staticmethod
    def visible_filters(
        *,
        organization_id: str | None,
        account_id: str | None,
        include_all_organizations: bool = False,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [AgentMemory.deleted_at.is_(None)]
        if include_all_organizations:
            pass
        elif organization_id is not None:
            filters.append(AgentMemory.organization_id == organization_id)
        else:
            filters.append(AgentMemory.organization_id.is_(None))
        if account_id is not None:
            filters.append(or_(AgentMemory.account_id.is_(None), AgentMemory.account_id == account_id))
        return filters


class AgentMemoryEventDAO(BaseRepository[AgentMemoryEvent]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AgentMemoryEvent)

    def add_event(
        self,
        *,
        memory_id: str,
        event_type: str,
        actor_account_id: str | None,
        source_type: AgentMemorySourceType | None,
        source_id: str | None,
        metadata_json: str | None,
    ) -> AgentMemoryEvent:
        entity = AgentMemoryEvent(
            memory_id=memory_id,
            event_type=event_type,
            actor_account_id=actor_account_id,
            source_type=source_type,
            source_id=source_id,
            metadata_json=metadata_json,
        )
        self.session.add(entity)
        self.session.flush()
        return entity
