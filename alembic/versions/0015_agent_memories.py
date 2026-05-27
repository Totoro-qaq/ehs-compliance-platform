"""add agent memory and citation audit tables

Revision ID: 0015_agent_memories
Revises: 0014_account_org_admin_role
Create Date: 2026-05-27 15:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0015_agent_memories'
down_revision: str | None = '0014_account_org_admin_role'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

agent_memory_scope_type = sa.Enum(
    'SESSION',
    'PROJECT',
    'ORGANIZATION',
    'STANDARD',
    name='agent_memory_scope_type',
)
agent_memory_type = sa.Enum(
    'PREFERENCE',
    'FACT',
    'DECISION',
    'WARNING',
    'CITATION',
    name='agent_memory_type',
)
agent_memory_source_type = sa.Enum(
    'MESSAGE',
    'TASK',
    'REPORT',
    'STANDARD_CHUNK',
    'HUMAN',
    'TOOL_CALL',
    name='agent_memory_source_type',
)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        'agent_memories',
        *_audit_columns(),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('account_id', sa.String(length=36), nullable=True),
        sa.Column('scope_type', agent_memory_scope_type, nullable=False),
        sa.Column('scope_id', sa.String(length=128), nullable=True),
        sa.Column('memory_type', agent_memory_type, nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source_type', agent_memory_source_type, nullable=False),
        sa.Column('source_id', sa.String(length=128), nullable=True),
        sa.Column('confidence', sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column('is_verified', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_memories_account_id'), 'agent_memories', ['account_id'])
    op.create_index(op.f('ix_agent_memories_deleted_at'), 'agent_memories', ['deleted_at'])
    op.create_index(op.f('ix_agent_memories_expires_at'), 'agent_memories', ['expires_at'])
    op.create_index(op.f('ix_agent_memories_is_verified'), 'agent_memories', ['is_verified'])
    op.create_index(op.f('ix_agent_memories_memory_type'), 'agent_memories', ['memory_type'])
    op.create_index(op.f('ix_agent_memories_organization_id'), 'agent_memories', ['organization_id'])
    op.create_index(op.f('ix_agent_memories_scope_id'), 'agent_memories', ['scope_id'])
    op.create_index(op.f('ix_agent_memories_scope_type'), 'agent_memories', ['scope_type'])
    op.create_index(op.f('ix_agent_memories_source_id'), 'agent_memories', ['source_id'])
    op.create_index(op.f('ix_agent_memories_source_type'), 'agent_memories', ['source_type'])
    op.create_index(
        'ix_agent_memories_scope_source',
        'agent_memories',
        ['organization_id', 'scope_type', 'scope_id', 'memory_type', 'source_type', 'source_id'],
    )

    op.create_table(
        'agent_memory_events',
        *_audit_columns(),
        sa.Column('memory_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('actor_account_id', sa.String(length=36), nullable=True),
        sa.Column('source_type', agent_memory_source_type, nullable=True),
        sa.Column('source_id', sa.String(length=128), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['actor_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['memory_id'], ['agent_memories.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_memory_events_actor_account_id'), 'agent_memory_events', ['actor_account_id'])
    op.create_index(op.f('ix_agent_memory_events_deleted_at'), 'agent_memory_events', ['deleted_at'])
    op.create_index(op.f('ix_agent_memory_events_event_type'), 'agent_memory_events', ['event_type'])
    op.create_index(op.f('ix_agent_memory_events_memory_id'), 'agent_memory_events', ['memory_id'])
    op.create_index(op.f('ix_agent_memory_events_source_id'), 'agent_memory_events', ['source_id'])
    op.create_index(op.f('ix_agent_memory_events_source_type'), 'agent_memory_events', ['source_type'])

    op.alter_column('agent_memories', 'is_verified', server_default=None)


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_memory_events_source_type'), table_name='agent_memory_events')
    op.drop_index(op.f('ix_agent_memory_events_source_id'), table_name='agent_memory_events')
    op.drop_index(op.f('ix_agent_memory_events_memory_id'), table_name='agent_memory_events')
    op.drop_index(op.f('ix_agent_memory_events_event_type'), table_name='agent_memory_events')
    op.drop_index(op.f('ix_agent_memory_events_deleted_at'), table_name='agent_memory_events')
    op.drop_index(op.f('ix_agent_memory_events_actor_account_id'), table_name='agent_memory_events')
    op.drop_table('agent_memory_events')

    op.drop_index('ix_agent_memories_scope_source', table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_source_type'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_source_id'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_scope_type'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_scope_id'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_organization_id'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_memory_type'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_is_verified'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_expires_at'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_deleted_at'), table_name='agent_memories')
    op.drop_index(op.f('ix_agent_memories_account_id'), table_name='agent_memories')
    op.drop_table('agent_memories')
