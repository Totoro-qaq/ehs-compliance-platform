"""初始表结构：organizations、assessment_tasks

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-16

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None

task_status_enum = mysql.ENUM(
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
        'organizations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organizations_deleted_at'), 'organizations', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_organizations_name'), 'organizations', ['name'], unique=False)

    op.create_table(
        'assessment_tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('content_type', sa.String(length=100), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=False),
        sa.Column('status', task_status_enum, nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_assessment_tasks_deleted_at'), 'assessment_tasks', ['deleted_at'], unique=False
    )
    op.create_index(
        op.f('ix_assessment_tasks_organization_id'),
        'assessment_tasks',
        ['organization_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_assessment_tasks_organization_id'), table_name='assessment_tasks')
    op.drop_index(op.f('ix_assessment_tasks_deleted_at'), table_name='assessment_tasks')
    op.drop_table('assessment_tasks')
    op.drop_index(op.f('ix_organizations_name'), table_name='organizations')
    op.drop_index(op.f('ix_organizations_deleted_at'), table_name='organizations')
    op.drop_table('organizations')
