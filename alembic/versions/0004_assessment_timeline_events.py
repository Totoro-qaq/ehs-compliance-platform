"""assessment timeline events

Revision ID: 0004_assessment_timeline_events
Revises: 0003_account_email_phone
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = '0004_assessment_timeline_events'
down_revision = '0003_account_email_phone'
branch_labels = None
depends_on = None

task_status = mysql.ENUM(
    'PENDING',
    'PARSING',
    'AI_ANALYZING',
    'VALIDATING',
    'PERSISTING',
    'SUCCESS',
    'FAILED',
)


def upgrade() -> None:
    op.create_table(
        'assessment_timeline_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('status', task_status, nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('message', sa.String(length=255), nullable=True),
        sa.Column('elapsed_ms', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['assessment_tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_assessment_timeline_events_deleted_at'),
        'assessment_timeline_events',
        ['deleted_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_assessment_timeline_events_status'),
        'assessment_timeline_events',
        ['status'],
        unique=False,
    )
    op.create_index(
        op.f('ix_assessment_timeline_events_task_id'),
        'assessment_timeline_events',
        ['task_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_assessment_timeline_events_task_id'), table_name='assessment_timeline_events')
    op.drop_index(op.f('ix_assessment_timeline_events_status'), table_name='assessment_timeline_events')
    op.drop_index(
        op.f('ix_assessment_timeline_events_deleted_at'),
        table_name='assessment_timeline_events',
    )
    op.drop_table('assessment_timeline_events')
