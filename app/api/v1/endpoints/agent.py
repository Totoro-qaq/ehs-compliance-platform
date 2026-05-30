from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.models.db_models import (
    AgentMemoryScopeType,
    AgentMemoryType,
    AgentPromptScenario,
    AgentRunStatus,
)
from app.schemas.agent_schema import (
    AgentChatRequest,
    AgentChatResponse,
    AgentMemoryDeleteResponse,
    AgentMemoryExpireRequest,
    AgentMemoryOut,
    AgentMemoryVerifyRequest,
    AgentMessageCreate,
    AgentMessageOut,
    AgentPromptOut,
    AgentRunOut,
    AgentRuntimeControlStateOut,
    AgentSecurityEventOut,
    AgentSessionCreate,
    AgentSessionDeleteResponse,
    AgentSessionOut,
    AgentToolCallOut,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.pagination import Page
from app.services.agent_memory_service import AgentMemoryService
from app.services.agent_service import AgentService

router = APIRouter(prefix='/agent', tags=['Agent 助手'])


@router.get(
    '/control-state',
    response_model=AgentRuntimeControlStateOut,
    summary='查询当前 Agent 运行策略与工具注册表',
)
def get_agent_control_state(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
):
    return AgentService.get_runtime_control_state(actor=actor)


@router.get(
    '/runs',
    response_model=Page[AgentRunOut],
    summary='查询 Agent 运行记录',
)
def list_agent_runs(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: AgentRunStatus | None = Query(default=None),
    provider: str | None = Query(default=None, max_length=32),
    session_id: str | None = Query(default=None, max_length=36),
):
    return AgentService.list_runs(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        status=status,
        provider=provider,
        session_id=session_id,
    )


@router.get(
    '/tool-calls',
    response_model=Page[AgentToolCallOut],
    summary='查询 Agent 工具调用记录',
)
def list_agent_tool_calls(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    run_id: str | None = Query(default=None, max_length=36),
    tool_name: str | None = Query(default=None, max_length=80),
    policy_decision: str | None = Query(default=None, max_length=32),
    success: bool | None = Query(default=None),
):
    return AgentService.list_tool_calls(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        run_id=run_id,
        tool_name=tool_name,
        policy_decision=policy_decision,
        success=success,
    )


@router.get(
    '/security-events',
    response_model=Page[AgentSecurityEventOut],
    summary='查询 Agent 安全审计事件',
)
def list_agent_security_events(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    event_type: str | None = Query(default=None, max_length=64),
    severity: str | None = Query(default=None, max_length=16),
    run_id: str | None = Query(default=None, max_length=36),
):
    return AgentService.list_security_events(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        event_type=event_type,
        severity=severity,
        run_id=run_id,
    )


@router.get(
    '/prompts',
    response_model=Page[AgentPromptOut],
    summary='查询 Agent 提示词注册表',
)
def list_agent_prompts(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    scenario: AgentPromptScenario | None = Query(default=None),
    active_only: bool = Query(default=False),
):
    return AgentService.list_prompts(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        scenario=scenario,
        active_only=active_only,
    )


@router.get(
    '/memories',
    response_model=list[AgentMemoryOut],
    summary='查询当前账号可见的 Agent memory',
)
def list_agent_memories(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    scope_type: AgentMemoryScopeType | None = Query(default=None),
    scope_id: str | None = Query(default=None, max_length=128),
    memory_type: AgentMemoryType | None = Query(default=None),
    include_expired: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
):
    return AgentMemoryService.list_memories(
        db=db,
        actor=actor,
        scope_type=scope_type,
        scope_id=scope_id,
        memory_type=memory_type,
        include_expired=include_expired,
        limit=limit,
    )


@router.patch(
    '/memories/{memory_id}/verify',
    response_model=AgentMemoryOut,
    summary='人工确认或取消确认 Agent memory',
)
def verify_agent_memory(
    memory_id: str,
    payload: AgentMemoryVerifyRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return AgentMemoryService.verify_memory(
        db=db,
        actor=actor,
        memory_id=memory_id,
        is_verified=payload.is_verified,
    )


@router.patch(
    '/memories/{memory_id}/expiration',
    response_model=AgentMemoryOut,
    summary='设置或清除 Agent memory 过期时间',
)
def update_agent_memory_expiration(
    memory_id: str,
    payload: AgentMemoryExpireRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return AgentMemoryService.set_memory_expiration(
        db=db,
        actor=actor,
        memory_id=memory_id,
        expires_at=payload.expires_at,
    )


@router.delete(
    '/memories/{memory_id}',
    response_model=AgentMemoryDeleteResponse,
    summary='软删除 Agent memory',
)
def delete_agent_memory(
    memory_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    deleted = AgentMemoryService.delete_memory(db=db, actor=actor, memory_id=memory_id)
    return AgentMemoryDeleteResponse(deleted=deleted)


@router.post(
    '/sessions',
    response_model=AgentSessionOut,
    summary='创建 Agent 会话',
)
def create_agent_session(
    payload: AgentSessionCreate,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return AgentService.create_session(db=db, actor=actor, title=payload.title)


@router.get(
    '/sessions',
    response_model=Page[AgentSessionOut],
    summary='查询 Agent 会话列表',
)
def list_agent_sessions(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    return AgentService.list_sessions(db=db, actor=actor, page=page, page_size=page_size)


@router.delete(
    '/sessions',
    response_model=AgentSessionDeleteResponse,
    summary='清空当前账号的 Agent 会话历史',
)
def clear_agent_sessions(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    deleted = AgentService.clear_sessions(db=db, actor=actor)
    return AgentSessionDeleteResponse(deleted=deleted)


@router.delete(
    '/sessions/{session_id}',
    response_model=AgentSessionDeleteResponse,
    summary='删除当前账号的 Agent 会话',
)
def delete_agent_session(
    session_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    deleted = AgentService.delete_session(db=db, actor=actor, session_id=session_id)
    return AgentSessionDeleteResponse(deleted=deleted)


@router.get(
    '/sessions/{session_id}/messages',
    response_model=list[AgentMessageOut],
    summary='查询 Agent 会话消息',
)
def list_agent_messages(
    session_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return AgentService.list_messages(db=db, actor=actor, session_id=session_id)


@router.post(
    '/sessions/{session_id}/messages',
    response_model=AgentChatResponse,
    summary='向 Agent 会话发送消息',
)
async def send_agent_message(
    session_id: str,
    payload: AgentMessageCreate,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return await AgentService.chat(
        db=db,
        actor=actor,
        session_id=session_id,
        content=payload.content,
    )


@router.post(
    '/chat',
    response_model=AgentChatResponse,
    summary='Agent 快捷聊天',
    description='工作台嵌入使用；session_id 为空时自动创建会话。',
)
async def agent_chat(
    payload: AgentChatRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return await AgentService.chat(
        db=db,
        actor=actor,
        session_id=payload.session_id,
        content=payload.content,
    )
