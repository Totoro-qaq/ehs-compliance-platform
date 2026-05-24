from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import (
    AgentMessage,
    AgentMessageRole,
    AgentRun,
    AgentRunStatus,
    AgentSession,
    AgentSessionStatus,
    AgentToolCall,
)


def _json_dump(value: dict[str, Any] | list[Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


class AgentSessionDAO(BaseRepository[AgentSession]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AgentSession)

    def create_session(
        self,
        *,
        account_id: str,
        organization_id: str | None,
        title: str,
    ) -> AgentSession:
        now = audit_now_naive()
        entity = AgentSession(
            account_id=account_id,
            organization_id=organization_id,
            title=title,
            status=AgentSessionStatus.OPEN,
            last_message_at=now,
        )
        return self.save_and_refresh(entity)

    def get_owned(self, *, session_id: str, account_id: str) -> AgentSession | None:
        stmt = select(AgentSession).where(
            AgentSession.id == session_id,
            AgentSession.account_id == account_id,
        )
        return self.session.scalars(stmt).one_or_none()

    def list_owned(
        self,
        *,
        account_id: str,
        page: int,
        page_size: int,
    ) -> tuple[list[AgentSession], int]:
        return self.list_page(
            page=page,
            page_size=page_size,
            filters=[AgentSession.account_id == account_id],
            order_by=[AgentSession.last_message_at.desc(), AgentSession.created_at.desc()],
        )

    def touch(self, entity: AgentSession, *, title: str | None = None) -> AgentSession:
        now = audit_now_naive()
        if title:
            entity.title = title
        entity.last_message_at = now
        entity.updated_at = now
        self.session.commit()
        self.session.refresh(entity)
        return entity


class AgentMessageDAO(BaseRepository[AgentMessage]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AgentMessage)

    def add_message(
        self,
        *,
        session_id: str,
        role: AgentMessageRole,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentMessage:
        entity = AgentMessage(
            session_id=session_id,
            role=role,
            content=content,
            metadata_json=_json_dump(metadata),
        )
        return self.save_and_refresh(entity)

    def list_for_session(self, session_id: str, *, limit: int = 50) -> list[AgentMessage]:
        stmt = (
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.created_at.asc(), AgentMessage.id.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())


class AgentRunDAO(BaseRepository[AgentRun]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AgentRun)

    def create_run(
        self,
        *,
        session_id: str,
        account_id: str,
        organization_id: str | None,
        user_message_id: str,
        provider: str,
        model_name: str,
    ) -> AgentRun:
        entity = AgentRun(
            session_id=session_id,
            account_id=account_id,
            organization_id=organization_id,
            user_message_id=user_message_id,
            provider=provider,
            model_name=model_name,
            status=AgentRunStatus.RUNNING,
            started_at=audit_now_naive(),
        )
        return self.save_and_refresh(entity)

    def finish_run(
        self,
        run: AgentRun,
        *,
        status: AgentRunStatus,
        assistant_message_id: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun:
        run.status = status
        run.assistant_message_id = assistant_message_id
        run.error_message = error_message
        run.finished_at = audit_now_naive()
        run.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(run)
        return run


class AgentToolCallDAO(BaseRepository[AgentToolCall]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AgentToolCall)

    def add_call(
        self,
        *,
        run_id: str,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None,
        result: dict[str, Any] | list[Any] | None,
        success: bool,
        elapsed_ms: int | None,
        error_message: str | None = None,
    ) -> AgentToolCall:
        entity = AgentToolCall(
            run_id=run_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments_json=_json_dump(arguments),
            result_json=_json_dump(result),
            success=1 if success else 0,
            error_message=error_message,
            elapsed_ms=elapsed_ms,
        )
        return self.save_and_refresh(entity)

    def list_for_run(self, run_id: str) -> list[AgentToolCall]:
        stmt = (
            select(AgentToolCall)
            .where(AgentToolCall.run_id == run_id)
            .order_by(AgentToolCall.created_at.asc(), AgentToolCall.id.asc())
        )
        return list(self.session.scalars(stmt).all())
