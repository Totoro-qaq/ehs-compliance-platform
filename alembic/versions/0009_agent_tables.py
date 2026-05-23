"""Add Agent session and audit tables.

Revision ID: 0009_agent_tables
Revises: 0008_organization_profile_fields
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = '0009_agent_tables'
down_revision = '0008_organization_profile_fields'
branch_labels = None
depends_on = None

agent_session_status = sa.Enum('OPEN', 'ARCHIVED', name='agent_session_status')
agent_message_role = sa.Enum('USER', 'ASSISTANT', 'SYSTEM', 'TOOL', name='agent_message_role')
agent_run_status = sa.Enum('RUNNING', 'SUCCEEDED', 'FAILED', name='agent_run_status')


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        'agent_sessions',
        *_audit_columns(),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('status', agent_session_status, nullable=False),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_sessions_account_id'), 'agent_sessions', ['account_id'])
    op.create_index(op.f('ix_agent_sessions_deleted_at'), 'agent_sessions', ['deleted_at'])
    op.create_index(
        op.f('ix_agent_sessions_last_message_at'), 'agent_sessions', ['last_message_at']
    )
    op.create_index(
        op.f('ix_agent_sessions_organization_id'), 'agent_sessions', ['organization_id']
    )
    op.create_index(op.f('ix_agent_sessions_status'), 'agent_sessions', ['status'])

    op.create_table(
        'agent_messages',
        *_audit_columns(),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('role', agent_message_role, nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_messages_deleted_at'), 'agent_messages', ['deleted_at'])
    op.create_index(op.f('ix_agent_messages_role'), 'agent_messages', ['role'])
    op.create_index(op.f('ix_agent_messages_session_id'), 'agent_messages', ['session_id'])

    op.create_table(
        'agent_runs',
        *_audit_columns(),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('account_id', sa.String(length=36), nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('user_message_id', sa.String(length=36), nullable=True),
        sa.Column('assistant_message_id', sa.String(length=36), nullable=True),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('status', agent_run_status, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assistant_message_id'], ['agent_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_message_id'], ['agent_messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_runs_account_id'), 'agent_runs', ['account_id'])
    op.create_index(
        op.f('ix_agent_runs_assistant_message_id'), 'agent_runs', ['assistant_message_id']
    )
    op.create_index(op.f('ix_agent_runs_deleted_at'), 'agent_runs', ['deleted_at'])
    op.create_index(op.f('ix_agent_runs_organization_id'), 'agent_runs', ['organization_id'])
    op.create_index(op.f('ix_agent_runs_session_id'), 'agent_runs', ['session_id'])
    op.create_index(op.f('ix_agent_runs_status'), 'agent_runs', ['status'])
    op.create_index(op.f('ix_agent_runs_user_message_id'), 'agent_runs', ['user_message_id'])

    op.create_table(
        'agent_tool_calls',
        *_audit_columns(),
        sa.Column('run_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('tool_name', sa.String(length=80), nullable=False),
        sa.Column('arguments_json', sa.Text(), nullable=True),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('success', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_tool_calls_deleted_at'), 'agent_tool_calls', ['deleted_at'])
    op.create_index(op.f('ix_agent_tool_calls_run_id'), 'agent_tool_calls', ['run_id'])
    op.create_index(op.f('ix_agent_tool_calls_session_id'), 'agent_tool_calls', ['session_id'])
    op.create_index(op.f('ix_agent_tool_calls_tool_name'), 'agent_tool_calls', ['tool_name'])


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_tool_calls_tool_name'), table_name='agent_tool_calls')
    op.drop_index(op.f('ix_agent_tool_calls_session_id'), table_name='agent_tool_calls')
    op.drop_index(op.f('ix_agent_tool_calls_run_id'), table_name='agent_tool_calls')
    op.drop_index(op.f('ix_agent_tool_calls_deleted_at'), table_name='agent_tool_calls')
    op.drop_table('agent_tool_calls')

    op.drop_index(op.f('ix_agent_runs_user_message_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_status'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_session_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_organization_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_deleted_at'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_assistant_message_id'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_account_id'), table_name='agent_runs')
    op.drop_table('agent_runs')

    op.drop_index(op.f('ix_agent_messages_session_id'), table_name='agent_messages')
    op.drop_index(op.f('ix_agent_messages_role'), table_name='agent_messages')
    op.drop_index(op.f('ix_agent_messages_deleted_at'), table_name='agent_messages')
    op.drop_table('agent_messages')

    op.drop_index(op.f('ix_agent_sessions_status'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_organization_id'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_last_message_at'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_deleted_at'), table_name='agent_sessions')
    op.drop_index(op.f('ix_agent_sessions_account_id'), table_name='agent_sessions')
    op.drop_table('agent_sessions')
