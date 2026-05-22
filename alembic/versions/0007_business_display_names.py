"""business display names

Revision ID: 0007_business_display_names
Revises: 0006_detection_physical_and_source_limits
Create Date: 2026-05-22
"""

import sqlalchemy as sa

from alembic import op

revision = '0007_business_display_names'
down_revision = '0006_detection_physical_and_source_limits'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('assessment_tasks', sa.Column('task_name', sa.String(length=255), nullable=True))
    op.add_column('detection_reports', sa.Column('report_name', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('detection_reports', 'report_name')
    op.drop_column('assessment_tasks', 'task_name')
