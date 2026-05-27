from __future__ import annotations

import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.db_models import (
    Account,
    AccountRole,
    AgentMemory,
    AgentMemoryEvent,
    AgentMemoryScopeType,
    AgentMemorySourceType,
    AgentMemoryType,
    Organization,
)
from app.schemas.auth_context import CurrentUser
from app.services.agent_memory_service import AgentMemoryService


def _auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _create_actor(db: Session, *, org_name: str = 'Memory Test Org') -> CurrentUser:
    suffix = uuid4().hex
    organization = Organization(name=f'{org_name} {suffix}')
    db.add(organization)
    db.flush()
    account = Account(
        username=f'memory-user-{suffix}',
        password_hash='test-hash',
        role=AccountRole.USER,
        organization_id=organization.id,
    )
    db.add(account)
    db.flush()
    return CurrentUser(
        account_id=account.id,
        username=account.username,
        role=account.role,
        organization_id=organization.id,
    )


def test_agent_memory_upsert_creates_memory_and_event(db: Session) -> None:
    actor = _create_actor(db)

    result = AgentMemoryService.upsert_memory(
        db=db,
        actor=actor,
        scope_type=AgentMemoryScopeType.PROJECT,
        scope_id='project-memory-001',
        memory_type=AgentMemoryType.DECISION,
        content='Use concise compliance summary format.',
        source_type=AgentMemorySourceType.HUMAN,
        source_id='manual-memory-001',
        metadata={'format': 'concise'},
    )

    assert result.created is True
    assert result.memory.organization_id == actor.organization_id
    assert result.memory.account_id == actor.account_id
    assert result.memory.content == 'Use concise compliance summary format.'
    assert result.event.event_type == 'CREATED'
    assert db.query(AgentMemory).count() == 1
    assert db.query(AgentMemoryEvent).filter_by(memory_id=result.memory.id).count() == 1


def test_agent_memory_upsert_updates_same_source_and_records_event(db: Session) -> None:
    actor = _create_actor(db)
    common_kwargs = {
        'db': db,
        'actor': actor,
        'scope_type': AgentMemoryScopeType.PROJECT,
        'scope_id': 'project-memory-002',
        'memory_type': AgentMemoryType.FACT,
        'source_type': AgentMemorySourceType.TASK,
        'source_id': 'task-memory-001',
    }

    first = AgentMemoryService.upsert_memory(
        **common_kwargs,
        content='Initial fact.',
        metadata={'version': 1},
    )
    second = AgentMemoryService.upsert_memory(
        **common_kwargs,
        content='Updated fact.',
        metadata={'version': 2},
    )

    memories = db.query(AgentMemory).all()
    events = db.query(AgentMemoryEvent).order_by(AgentMemoryEvent.created_at.asc()).all()
    assert first.memory.id == second.memory.id
    assert len(memories) == 1
    assert memories[0].content == 'Updated fact.'
    assert [event.event_type for event in events] == ['CREATED', 'UPDATED']
    assert json.loads(memories[0].metadata_json or '{}') == {'version': 2}


def test_agent_memory_list_is_organization_scoped(db: Session) -> None:
    actor = _create_actor(db, org_name='Memory Visible Org')
    other_actor = _create_actor(db, org_name='Memory Hidden Org')

    AgentMemoryService.upsert_memory(
        db=db,
        actor=actor,
        scope_type=AgentMemoryScopeType.ORGANIZATION,
        scope_id=actor.organization_id,
        memory_type=AgentMemoryType.WARNING,
        content='Visible org warning.',
        source_type=AgentMemorySourceType.HUMAN,
        source_id='visible-warning',
    )
    AgentMemoryService.upsert_memory(
        db=db,
        actor=other_actor,
        scope_type=AgentMemoryScopeType.ORGANIZATION,
        scope_id=other_actor.organization_id,
        memory_type=AgentMemoryType.WARNING,
        content='Hidden org warning.',
        source_type=AgentMemorySourceType.HUMAN,
        source_id='hidden-warning',
    )

    visible = AgentMemoryService.list_memories(db=db, actor=actor, limit=10)

    assert [item.content for item in visible] == ['Visible org warning.']
    assert all(item.organization_id == actor.organization_id for item in visible)


def test_standard_chunk_search_records_citation_memory_without_full_text(
    client: TestClient,
    admin_token: str,
    user_token: str,
    db: Session,
) -> None:
    full_text = '测试因子甲的测试限值依据来自 TEST-MEM-001 第 5.2 条，不应完整写入 memory。'
    imported = client.post(
        '/api/v1/standards/manifest/import',
        json={
            'documents': [
                {
                    'standard_code': 'TEST-MEM-001',
                    'standard_name': '测试 Memory 引用标准',
                    'domain': 'occupational_health',
                    'object_key': 'raw/occupational_health/test-memory-001.pdf',
                    'file_hash': 'm' * 64,
                    'chunks': [
                        {
                            'chunk_index': 0,
                            'clause': '5.2',
                            'text_chunk': full_text,
                            'page_start': 12,
                            'page_end': 12,
                        }
                    ],
                }
            ]
        },
        headers=_auth(admin_token),
    )
    assert imported.status_code == 200

    response = client.post(
        '/api/v1/agent/chat',
        json={'content': '测试因子甲的测试限值依据是什么？'},
        headers=_auth(user_token),
    )

    assert response.status_code == 200
    data = response.json()['data']
    memories = (
        db.query(AgentMemory)
        .filter(
            AgentMemory.scope_id == data['session']['id'],
            AgentMemory.memory_type == AgentMemoryType.CITATION,
        )
        .all()
    )
    assert len(memories) == 1

    memory = memories[0]
    metadata = json.loads(memory.metadata_json or '{}')
    metadata_text = json.dumps(metadata, ensure_ascii=False)
    assert memory.scope_type == AgentMemoryScopeType.SESSION
    assert memory.source_type == AgentMemorySourceType.STANDARD_CHUNK
    assert memory.content == 'TEST-MEM-001 5.2 p.12'
    assert metadata['standard_code'] == 'TEST-MEM-001'
    assert metadata['standard_name'] == '测试 Memory 引用标准'
    assert metadata['clause'] == '5.2'
    assert metadata['page_start'] == 12
    assert metadata['page_end'] == 12
    assert 'text_chunk' not in metadata
    assert full_text not in memory.content
    assert full_text not in metadata_text

    event = db.query(AgentMemoryEvent).filter_by(memory_id=memory.id).one()
    tool_call_ids = {call['id'] for call in data['tool_calls'] if call['tool_name'] == 'search_standard_chunks'}
    assert event.source_type == AgentMemorySourceType.TOOL_CALL
    assert event.source_id in tool_call_ids
