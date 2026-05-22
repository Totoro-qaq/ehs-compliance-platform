"""Add organization profile fields.

Revision ID: 0008_organization_profile_fields
Revises: 0007_business_display_names
Create Date: 2026-05-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = '0008_organization_profile_fields'
down_revision = '0007_business_display_names'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organizations', sa.Column('unified_social_credit_code', sa.String(length=32), nullable=True))
    op.add_column('organizations', sa.Column('intest particlesry', sa.String(length=128), nullable=True))
    op.add_column('organizations', sa.Column('address', sa.String(length=500), nullable=True))
    op.add_column('organizations', sa.Column('contact_name', sa.String(length=64), nullable=True))
    op.add_column('organizations', sa.Column('contact_phone', sa.String(length=32), nullable=True))
    op.add_column('organizations', sa.Column('notes', sa.Text(), nullable=True))
    op.create_index(
        'ix_organizations_unified_social_credit_code',
        'organizations',
        ['unified_social_credit_code'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_organizations_unified_social_credit_code', table_name='organizations')
    op.drop_column('organizations', 'notes')
    op.drop_column('organizations', 'contact_phone')
    op.drop_column('organizations', 'contact_name')
    op.drop_column('organizations', 'address')
    op.drop_column('organizations', 'intest particlesry')
    op.drop_column('organizations', 'unified_social_credit_code')
