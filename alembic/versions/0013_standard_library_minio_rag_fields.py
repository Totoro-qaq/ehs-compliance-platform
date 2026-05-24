"""add standard library minio and rag access fields

Revision ID: 0013_standard_library_minio_rag_fields
Revises: 0012_standard_library_metadata
Create Date: 2026-05-24 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0013_standard_library_minio_rag_fields'
down_revision: str | None = '0012_standard_library_metadata'
_unused_branch_labels: str | Sequence[str] | None = None
_unused_depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'standard_documents',
        sa.Column('storage_backend', sa.String(length=32), nullable=False, server_default='minio'),
    )
    op.add_column('standard_documents', sa.Column('bucket', sa.String(length=128), nullable=True))
    op.add_column('standard_documents', sa.Column('object_key', sa.String(length=1024), nullable=True))
    op.add_column('standard_documents', sa.Column('object_version', sa.String(length=128), nullable=True))
    op.add_column(
        'standard_documents',
        sa.Column('is_sensitive', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index(
        op.f('ix_standard_documents_storage_backend'),
        'standard_documents',
        ['storage_backend'],
        unique=False,
    )
    op.create_index(op.f('ix_standard_documents_bucket'), 'standard_documents', ['bucket'], unique=False)
    op.create_index(
        op.f('ix_standard_documents_is_sensitive'),
        'standard_documents',
        ['is_sensitive'],
        unique=False,
    )

    op.add_column(
        'standard_chunks',
        sa.Column('is_sensitive', sa.Integer(), nullable=False, server_default='0'),
    )
    op.create_index(
        op.f('ix_standard_chunks_is_sensitive'),
        'standard_chunks',
        ['is_sensitive'],
        unique=False,
    )

    op.alter_column('standard_documents', 'storage_backend', server_default=None)
    op.alter_column('standard_documents', 'is_sensitive', server_default=None)
    op.alter_column('standard_chunks', 'is_sensitive', server_default=None)


def downgrade() -> None:
    op.drop_index(op.f('ix_standard_chunks_is_sensitive'), table_name='standard_chunks')
    op.drop_column('standard_chunks', 'is_sensitive')

    op.drop_index(op.f('ix_standard_documents_is_sensitive'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_bucket'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_storage_backend'), table_name='standard_documents')
    op.drop_column('standard_documents', 'is_sensitive')
    op.drop_column('standard_documents', 'object_version')
    op.drop_column('standard_documents', 'object_key')
    op.drop_column('standard_documents', 'bucket')
    op.drop_column('standard_documents', 'storage_backend')
