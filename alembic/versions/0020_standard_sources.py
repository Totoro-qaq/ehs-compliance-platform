"""add standard source authorization ledger

Revision ID: 0020_standard_sources
Revises: 0019_agent_prompt_registry
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0020_standard_sources'
down_revision: str | None = '0019_agent_prompt_registry'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

standard_source_type = sa.Enum(
    'OFFICIAL_PUBLIC',
    'AUTHORIZED_PURCHASE',
    'CUSTOMER_PROVIDED',
    'INTERNAL',
    name='standard_source_type',
)
standard_source_review_status = sa.Enum(
    'PENDING',
    'APPROVED',
    'REJECTED',
    'EXPIRED',
    name='standard_source_review_status',
)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        'standard_sources',
        *_audit_columns(),
        sa.Column('source_name', sa.String(length=255), nullable=False),
        sa.Column('source_type', standard_source_type, nullable=False),
        sa.Column('provider_name', sa.String(length=255), nullable=True),
        sa.Column('license_no', sa.String(length=128), nullable=True),
        sa.Column('license_scope', sa.Text(), nullable=True),
        sa.Column('organization_id', sa.String(length=36), nullable=True),
        sa.Column('allow_storage', sa.Integer(), nullable=False),
        sa.Column('allow_vectorization', sa.Integer(), nullable=False),
        sa.Column('allow_ai_retrieval', sa.Integer(), nullable=False),
        sa.Column('allow_excerpt_export', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('review_status', standard_source_review_status, nullable=False),
        sa.Column('reviewed_by_id', sa.String(length=36), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_standard_sources_allow_ai_retrieval'), 'standard_sources', ['allow_ai_retrieval']
    )
    op.create_index(
        op.f('ix_standard_sources_allow_excerpt_export'),
        'standard_sources',
        ['allow_excerpt_export'],
    )
    op.create_index(
        op.f('ix_standard_sources_allow_storage'), 'standard_sources', ['allow_storage']
    )
    op.create_index(
        op.f('ix_standard_sources_allow_vectorization'), 'standard_sources', ['allow_vectorization']
    )
    op.create_index(op.f('ix_standard_sources_deleted_at'), 'standard_sources', ['deleted_at'])
    op.create_index(op.f('ix_standard_sources_effective_to'), 'standard_sources', ['effective_to'])
    op.create_index(op.f('ix_standard_sources_license_no'), 'standard_sources', ['license_no'])
    op.create_index(
        op.f('ix_standard_sources_organization_id'), 'standard_sources', ['organization_id']
    )
    op.create_index(
        op.f('ix_standard_sources_review_status'), 'standard_sources', ['review_status']
    )
    op.create_index(
        op.f('ix_standard_sources_reviewed_by_id'), 'standard_sources', ['reviewed_by_id']
    )
    op.create_index(op.f('ix_standard_sources_source_name'), 'standard_sources', ['source_name'])
    op.create_index(op.f('ix_standard_sources_source_type'), 'standard_sources', ['source_type'])

    op.add_column(
        'standard_documents', sa.Column('organization_id', sa.String(length=36), nullable=True)
    )
    op.add_column('standard_documents', sa.Column('source_id', sa.String(length=36), nullable=True))
    op.add_column(
        'standard_documents', sa.Column('license_id', sa.String(length=128), nullable=True)
    )
    op.add_column(
        'standard_documents',
        sa.Column(
            'source_review_status',
            standard_source_review_status,
            nullable=False,
            server_default='PENDING',
        ),
    )
    op.add_column(
        'standard_documents',
        sa.Column('allow_ai_retrieval', sa.Integer(), nullable=False, server_default='0'),
    )
    op.add_column(
        'standard_documents',
        sa.Column('allow_excerpt_export', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_foreign_key(
        'fk_standard_documents_organization_id_organizations',
        'standard_documents',
        'organizations',
        ['organization_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_standard_documents_source_id_standard_sources',
        'standard_documents',
        'standard_sources',
        ['source_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_standard_documents_allow_ai_retrieval'),
        'standard_documents',
        ['allow_ai_retrieval'],
    )
    op.create_index(
        op.f('ix_standard_documents_allow_excerpt_export'),
        'standard_documents',
        ['allow_excerpt_export'],
    )
    op.create_index(op.f('ix_standard_documents_license_id'), 'standard_documents', ['license_id'])
    op.create_index(
        op.f('ix_standard_documents_organization_id'), 'standard_documents', ['organization_id']
    )
    op.create_index(
        op.f('ix_standard_documents_source_review_status'),
        'standard_documents',
        ['source_review_status'],
    )
    op.create_index(op.f('ix_standard_documents_source_id'), 'standard_documents', ['source_id'])
    op.alter_column('standard_documents', 'source_review_status', server_default=None)
    op.alter_column('standard_documents', 'allow_ai_retrieval', server_default=None)
    op.alter_column('standard_documents', 'allow_excerpt_export', server_default=None)


def downgrade() -> None:
    op.drop_index(op.f('ix_standard_documents_source_id'), table_name='standard_documents')
    op.drop_index(
        op.f('ix_standard_documents_source_review_status'), table_name='standard_documents'
    )
    op.drop_index(op.f('ix_standard_documents_organization_id'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_license_id'), table_name='standard_documents')
    op.drop_index(
        op.f('ix_standard_documents_allow_excerpt_export'), table_name='standard_documents'
    )
    op.drop_index(op.f('ix_standard_documents_allow_ai_retrieval'), table_name='standard_documents')
    op.drop_constraint(
        'fk_standard_documents_source_id_standard_sources',
        'standard_documents',
        type_='foreignkey',
    )
    op.drop_constraint(
        'fk_standard_documents_organization_id_organizations',
        'standard_documents',
        type_='foreignkey',
    )
    op.drop_column('standard_documents', 'allow_excerpt_export')
    op.drop_column('standard_documents', 'allow_ai_retrieval')
    op.drop_column('standard_documents', 'source_review_status')
    op.drop_column('standard_documents', 'license_id')
    op.drop_column('standard_documents', 'source_id')
    op.drop_column('standard_documents', 'organization_id')

    op.drop_index(op.f('ix_standard_sources_source_type'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_source_name'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_reviewed_by_id'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_review_status'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_organization_id'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_license_no'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_effective_to'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_deleted_at'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_allow_vectorization'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_allow_storage'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_allow_excerpt_export'), table_name='standard_sources')
    op.drop_index(op.f('ix_standard_sources_allow_ai_retrieval'), table_name='standard_sources')
    op.drop_table('standard_sources')
    standard_source_review_status.drop(op.get_bind(), checkfirst=True)
    standard_source_type.drop(op.get_bind(), checkfirst=True)
