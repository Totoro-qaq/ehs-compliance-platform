"""accounts 表、任务 parsed_text / created_by_id

Revision ID: 0002_accounts_and_task_meta
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0002_accounts_and_task_meta'
down_revision = '0001_initial'
branch_labels = None
depends_on = None

account_role = mysql.ENUM('ADMIN', 'USER')


def upgrade() -> None:
    op.create_table(
        'accounts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', account_role, nullable=False),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_accounts_deleted_at'), 'accounts', ['deleted_at'], unique=False)
    op.create_index(op.f('ix_accounts_organization_id'), 'accounts', ['organization_id'], unique=False)
    op.create_index(op.f('ix_accounts_username'), 'accounts', ['username'], unique=True)

    op.add_column('assessment_tasks', sa.Column('parsed_text', sa.Text(), nullable=True))
    op.add_column(
        'assessment_tasks',
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f('ix_assessment_tasks_created_by_id'),
        'assessment_tasks',
        ['created_by_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_assessment_tasks_created_by_id',
        'assessment_tasks',
        'accounts',
        ['created_by_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_assessment_tasks_created_by_id', 'assessment_tasks', type_='foreignkey')
    op.drop_index(op.f('ix_assessment_tasks_created_by_id'), table_name='assessment_tasks')
    op.drop_column('assessment_tasks', 'created_by_id')
    op.drop_column('assessment_tasks', 'parsed_text')

    op.drop_index(op.f('ix_accounts_username'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_organization_id'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_deleted_at'), table_name='accounts')
    op.drop_table('accounts')
