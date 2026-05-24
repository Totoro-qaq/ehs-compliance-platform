from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.db_models import AgentMessageRole, AgentRunStatus, AgentSessionStatus


class AgentSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class AgentSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    organization_id: str | None = None
    title: str
    status: AgentSessionStatus
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)


class AgentChatRequest(AgentMessageCreate):
    session_id: str | None = None


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    role: AgentMessageRole
    content: str
    metadata_json: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    account_id: str
    organization_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    provider: str
    model_name: str
    status: AgentRunStatus
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AgentToolCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    session_id: str
    tool_name: str
    arguments_json: str | None = None
    result_json: str | None = None
    success: bool
    error_message: str | None = None
    elapsed_ms: int | None = None
    created_at: datetime
    updated_at: datetime


class AgentSessionDeleteResponse(BaseModel):
    deleted: int = Field(ge=0)


class AgentChatResponse(BaseModel):
    session: AgentSessionOut
    user_message: AgentMessageOut
    assistant_message: AgentMessageOut
    run: AgentRunOut
    tool_calls: list[AgentToolCallOut] = Field(default_factory=list)
    degraded: bool = False
