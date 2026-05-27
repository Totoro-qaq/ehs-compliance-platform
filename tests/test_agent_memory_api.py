from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import current_user_from_token
from app.models.db_models import (
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


def _create_memory(
    *,
    db: Session,
    actor: CurrentUser,
    content: str,
    source_id: str,
) -> AgentMemory:
    result = AgentMemoryService.upsert_memory(
        db=db,
        actor=actor,
        scope_type=AgentMemoryScopeType.SESSION,
        scope_id='api-memory-session',
        memory_type=AgentMemoryType.CITATION,
        content=content,
        source_type=AgentMemorySourceType.HUMAN,
        source_id=source_id,
    )
    return result.memory


def test_agent_memory_api_lists_only_visible_memories(
    client: TestClient,
    user_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    visible_memory = _create_memory(
        db=db,
        actor=actor,
        content='Visible API memory.',
        source_id='visible-api-memory',
    )

    other_org = Organization(name='Memory API Hidden Org')
    db.add(other_org)
    db.flush()
    db.add(
        AgentMemory(
            organization_id=other_org.id,
            account_id='other-account',
            scope_type=AgentMemoryScopeType.SESSION,
            scope_id='api-memory-session',
            memory_type=AgentMemoryType.CITATION,
            content='Hidden API memory.',
            source_type=AgentMemorySourceType.HUMAN,
            source_id='hidden-api-memory',
        )
    )
    db.commit()

    response = client.get('/api/v1/agent/memories', headers=_auth(user_token))

    assert response.status_code == 200
    items = response.json()['data']
    ids = {item['id'] for item in items}
    assert visible_memory.id in ids
    assert all(item['content'] != 'Hidden API memory.' for item in items)


def test_agent_memory_api_verify_expire_and_delete_owned_memory(
    client: TestClient,
    user_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    memory = _create_memory(
        db=db,
        actor=actor,
        content='Owned API memory.',
        source_id='owned-api-memory',
    )

    verified = client.patch(
        f'/api/v1/agent/memories/{memory.id}/verify',
        json={'is_verified': True},
        headers=_auth(user_token),
    )
    assert verified.status_code == 200
    assert verified.json()['data']['is_verified'] is True

    expired_at = '2000-01-01T00:00:00'
    expired = client.patch(
        f'/api/v1/agent/memories/{memory.id}/expiration',
        json={'expires_at': expired_at},
        headers=_auth(user_token),
    )
    assert expired.status_code == 200
    assert expired.json()['data']['expires_at'].startswith('2000-01-01T00:00:00')

    visible = client.get('/api/v1/agent/memories', headers=_auth(user_token))
    assert visible.status_code == 200
    assert all(item['id'] != memory.id for item in visible.json()['data'])

    visible_with_expired = client.get(
        '/api/v1/agent/memories',
        params={'include_expired': True},
        headers=_auth(user_token),
    )
    assert visible_with_expired.status_code == 200
    assert any(item['id'] == memory.id for item in visible_with_expired.json()['data'])

    deleted = client.delete(f'/api/v1/agent/memories/{memory.id}', headers=_auth(user_token))
    assert deleted.status_code == 200
    assert deleted.json()['data']['deleted'] == 1

    deleted_memory = (
        db.query(AgentMemory)
        .filter_by(id=memory.id)
        .execution_options(include_deleted=True)
        .one()
    )
    assert deleted_memory.deleted_at is not None

    event_types = {
        event.event_type
        for event in db.query(AgentMemoryEvent).filter_by(memory_id=memory.id).all()
    }
    assert {'CREATED', 'VERIFIED', 'EXPIRATION_UPDATED', 'DELETED'} <= event_types


def test_agent_memory_api_protects_shared_memory_mutation(
    client: TestClient,
    user_token: str,
    org_admin_token: str,
    db: Session,
) -> None:
    actor = current_user_from_token(user_token)
    assert actor.organization_id is not None
    shared_memory = AgentMemory(
        organization_id=actor.organization_id,
        account_id=None,
        scope_type=AgentMemoryScopeType.ORGANIZATION,
        scope_id=actor.organization_id,
        memory_type=AgentMemoryType.WARNING,
        content='Shared organization memory.',
        source_type=AgentMemorySourceType.HUMAN,
        source_id='shared-api-memory',
        expires_at=datetime(2099, 1, 1),
    )
    db.add(shared_memory)
    db.commit()
    db.refresh(shared_memory)

    user_delete = client.delete(
        f'/api/v1/agent/memories/{shared_memory.id}',
        headers=_auth(user_token),
    )
    assert user_delete.status_code == 403

    org_admin_verify = client.patch(
        f'/api/v1/agent/memories/{shared_memory.id}/verify',
        json={'is_verified': True},
        headers=_auth(org_admin_token),
    )
    assert org_admin_verify.status_code == 200
    assert org_admin_verify.json()['data']['is_verified'] is True
