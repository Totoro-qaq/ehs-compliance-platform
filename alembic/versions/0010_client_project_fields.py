"""add lightweight client project fields

Revision ID: 0010_client_project_fields
Revises: 0009_agent_tables
Create Date: 2026-05-23 14:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0010_client_project_fields'
down_revision: str | None = '0009_agent_tables'
_unused_branch_labels: str | Sequence[str] | None = None
_unused_depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('assessment_tasks', sa.Column('client_name', sa.String(length=255), nullable=True))
    op.add_column('assessment_tasks', sa.Column('project_name', sa.String(length=255), nullable=True))
    op.add_column('assessment_tasks', sa.Column('project_code', sa.String(length=64), nullable=True))
    op.add_column('assessment_tasks', sa.Column('service_type', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_assessment_tasks_client_name'), 'assessment_tasks', ['client_name'], unique=False)
    op.create_index(op.f('ix_assessment_tasks_project_name'), 'assessment_tasks', ['project_name'], unique=False)
    op.create_index(op.f('ix_assessment_tasks_project_code'), 'assessment_tasks', ['project_code'], unique=False)
    op.create_index(op.f('ix_assessment_tasks_service_type'), 'assessment_tasks', ['service_type'], unique=False)

    op.add_column('detection_reports', sa.Column('client_name', sa.String(length=255), nullable=True))
    op.add_column('detection_reports', sa.Column('project_name', sa.String(length=255), nullable=True))
    op.add_column('detection_reports', sa.Column('project_code', sa.String(length=64), nullable=True))
    op.add_column('detection_reports', sa.Column('service_type', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_detection_reports_client_name'), 'detection_reports', ['client_name'], unique=False)
    op.create_index(op.f('ix_detection_reports_project_name'), 'detection_reports', ['project_name'], unique=False)
    op.create_index(op.f('ix_detection_reports_project_code'), 'detection_reports', ['project_code'], unique=False)
    op.create_index(op.f('ix_detection_reports_service_type'), 'detection_reports', ['service_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_detection_reports_service_type'), table_name='detection_reports')
    op.drop_index(op.f('ix_detection_reports_project_code'), table_name='detection_reports')
    op.drop_index(op.f('ix_detection_reports_project_name'), table_name='detection_reports')
    op.drop_index(op.f('ix_detection_reports_client_name'), table_name='detection_reports')
    op.drop_column('detection_reports', 'service_type')
    op.drop_column('detection_reports', 'project_code')
    op.drop_column('detection_reports', 'project_name')
    op.drop_column('detection_reports', 'client_name')

    op.drop_index(op.f('ix_assessment_tasks_service_type'), table_name='assessment_tasks')
    op.drop_index(op.f('ix_assessment_tasks_project_code'), table_name='assessment_tasks')
    op.drop_index(op.f('ix_assessment_tasks_project_name'), table_name='assessment_tasks')
    op.drop_index(op.f('ix_assessment_tasks_client_name'), table_name='assessment_tasks')
    op.drop_column('assessment_tasks', 'service_type')
    op.drop_column('assessment_tasks', 'project_code')
    op.drop_column('assessment_tasks', 'project_name')
    op.drop_column('assessment_tasks', 'client_name')
