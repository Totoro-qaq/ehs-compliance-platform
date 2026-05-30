"""add agent audit snapshots and security events

Revision ID: 0018_agent_audit_security
Revises: 0017_assessment_needs_review_status
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0018_agent_audit_security'
down_revision: str | None = '0017_assessment_needs_review_status'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    with op.batch_alter_table('agent_runs') as batch_op:
        batch_op.add_column(sa.Column('policy_id', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('policy_version', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('policy_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('context_snapshot_json', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('prompt_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('output_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('risk_flags_json', sa.Text(), nullable=True))
        batch_op.create_index(op.f('ix_agent_runs_policy_id'), ['policy_id'])
        batch_op.create_index(op.f('ix_agent_runs_policy_version'), ['policy_version'])
        batch_op.create_index(op.f('ix_agent_runs_prompt_hash'), ['prompt_hash'])
        batch_op.create_index(op.f('ix_agent_runs_output_hash'), ['output_hash'])

    with op.batch_alter_table('agent_tool_calls') as batch_op:
        batch_op.add_column(sa.Column('tool_version', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('permission_level', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('side_effect_level', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('policy_decision', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('result_summary_json', sa.Text(), nullable=True))
        batch_op.create_index(op.f('ix_agent_tool_calls_permission_level'), ['permission_level'])
        batch_op.create_index(op.f('ix_agent_tool_calls_side_effect_level'), ['side_effect_level'])
        batch_op.create_index(op.f('ix_agent_tool_calls_policy_decision'), ['policy_decision'])

    op.create_table(
        'agent_security_events',
        *_audit_columns(),
        sa.Column('run_id', sa.String(length=36), nullable=True),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('account_id', sa.String(length=36), nullable=True),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=16), nullable=False),
        sa.Column('tool_name', sa.String(length=80), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['agent_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_agent_security_events_account_id'), 'agent_security_events', ['account_id'])
    op.create_index(op.f('ix_agent_security_events_deleted_at'), 'agent_security_events', ['deleted_at'])
    op.create_index(op.f('ix_agent_security_events_event_type'), 'agent_security_events', ['event_type'])
    op.create_index(op.f('ix_agent_security_events_organization_id'), 'agent_security_events', ['organization_id'])
    op.create_index(op.f('ix_agent_security_events_run_id'), 'agent_security_events', ['run_id'])
    op.create_index(op.f('ix_agent_security_events_session_id'), 'agent_security_events', ['session_id'])
    op.create_index(op.f('ix_agent_security_events_severity'), 'agent_security_events', ['severity'])
    op.create_index(op.f('ix_agent_security_events_tool_name'), 'agent_security_events', ['tool_name'])


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_security_events_tool_name'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_severity'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_session_id'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_run_id'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_organization_id'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_event_type'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_deleted_at'), table_name='agent_security_events')
    op.drop_index(op.f('ix_agent_security_events_account_id'), table_name='agent_security_events')
    op.drop_table('agent_security_events')

    with op.batch_alter_table('agent_tool_calls') as batch_op:
        batch_op.drop_index(op.f('ix_agent_tool_calls_policy_decision'))
        batch_op.drop_index(op.f('ix_agent_tool_calls_side_effect_level'))
        batch_op.drop_index(op.f('ix_agent_tool_calls_permission_level'))
        batch_op.drop_column('result_summary_json')
        batch_op.drop_column('policy_decision')
        batch_op.drop_column('side_effect_level')
        batch_op.drop_column('permission_level')
        batch_op.drop_column('tool_version')

    with op.batch_alter_table('agent_runs') as batch_op:
        batch_op.drop_index(op.f('ix_agent_runs_output_hash'))
        batch_op.drop_index(op.f('ix_agent_runs_prompt_hash'))
        batch_op.drop_index(op.f('ix_agent_runs_policy_version'))
        batch_op.drop_index(op.f('ix_agent_runs_policy_id'))
        batch_op.drop_column('risk_flags_json')
        batch_op.drop_column('output_hash')
        batch_op.drop_column('prompt_hash')
        batch_op.drop_column('context_snapshot_json')
        batch_op.drop_column('policy_json')
        batch_op.drop_column('policy_version')
        batch_op.drop_column('policy_id')
