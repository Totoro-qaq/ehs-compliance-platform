"""add assessment needs review status

Revision ID: 0017_assessment_needs_review_status
Revises: 0016_report_pipeline_sections
Create Date: 2026-05-28 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = '0017_assessment_needs_review_status'
down_revision: str | None = '0016_report_pipeline_sections'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

OLD_TASK_STATUS_VALUES = (
    'PENDING',
    'PARSING',
    'AI_ANALYZING',
    'VALIDATING',
    'PERSISTING',
    'SUCCESS',
    'FAILED',
)
NEW_TASK_STATUS_VALUES = (
    'PENDING',
    'PARSING',
    'AI_ANALYZING',
    'VALIDATING',
    'PERSISTING',
    'SUCCESS',
    'NEEDS_REVIEW',
    'FAILED',
)


def _task_status_enum(values: tuple[str, ...]) -> mysql.ENUM:
    return mysql.ENUM(*values)


def _alter_status_columns(*, from_values: tuple[str, ...], to_values: tuple[str, ...]) -> None:
    existing_type = _task_status_enum(from_values)
    target_type = _task_status_enum(to_values)
    op.alter_column(
        'assessment_tasks',
        'status',
        existing_type=existing_type,
        type_=target_type,
        existing_nullable=False,
    )
    op.alter_column(
        'assessment_timeline_events',
        'status',
        existing_type=existing_type,
        type_=target_type,
        existing_nullable=False,
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == 'mysql':
        _alter_status_columns(from_values=OLD_TASK_STATUS_VALUES, to_values=NEW_TASK_STATUS_VALUES)
        return

    with op.batch_alter_table('assessment_tasks') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*OLD_TASK_STATUS_VALUES),
            type_=sa.Enum(*NEW_TASK_STATUS_VALUES),
            existing_nullable=False,
        )
    with op.batch_alter_table('assessment_timeline_events') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*OLD_TASK_STATUS_VALUES),
            type_=sa.Enum(*NEW_TASK_STATUS_VALUES),
            existing_nullable=False,
        )


def downgrade() -> None:
    op.execute("UPDATE assessment_tasks SET status = 'FAILED' WHERE status = 'NEEDS_REVIEW'")
    op.execute("UPDATE assessment_timeline_events SET status = 'FAILED' WHERE status = 'NEEDS_REVIEW'")
    if op.get_bind().dialect.name == 'mysql':
        _alter_status_columns(from_values=NEW_TASK_STATUS_VALUES, to_values=OLD_TASK_STATUS_VALUES)
        return

    with op.batch_alter_table('assessment_tasks') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*NEW_TASK_STATUS_VALUES),
            type_=sa.Enum(*OLD_TASK_STATUS_VALUES),
            existing_nullable=False,
        )
    with op.batch_alter_table('assessment_timeline_events') as batch_op:
        batch_op.alter_column(
            'status',
            existing_type=sa.Enum(*NEW_TASK_STATUS_VALUES),
            type_=sa.Enum(*OLD_TASK_STATUS_VALUES),
            existing_nullable=False,
        )
