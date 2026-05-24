"""add organization administrator account role

Revision ID: 0014_account_org_admin_role
Revises: 0013_standard_library_minio_rag_fields
Create Date: 2026-05-24 12:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = '0014_account_org_admin_role'
down_revision: str | None = '0013_standard_library_minio_rag_fields'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.execute("ALTER TABLE accounts MODIFY COLUMN role ENUM('ADMIN','ORG_ADMIN','USER') NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.execute("UPDATE accounts SET role = 'USER' WHERE role = 'ORG_ADMIN'")
        op.execute("ALTER TABLE accounts MODIFY COLUMN role ENUM('ADMIN','USER') NOT NULL")
