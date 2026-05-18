"""accounts 增加 email、phone

Revision ID: 0003_account_email_phone
Revises: 0002_accounts_and_task_meta
"""

import sqlalchemy as sa

from alembic import op

revision = '0003_account_email_phone'
down_revision = '0002_accounts_and_task_meta'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('accounts', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('accounts', sa.Column('phone', sa.String(length=20), nullable=True))
    op.create_index(op.f('ix_accounts_email'), 'accounts', ['email'], unique=True)
    op.create_index(op.f('ix_accounts_phone'), 'accounts', ['phone'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_accounts_phone'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_email'), table_name='accounts')
    op.drop_column('accounts', 'phone')
    op.drop_column('accounts', 'email')
