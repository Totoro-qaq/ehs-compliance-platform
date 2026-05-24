"""add standard library metadata tables

Revision ID: 0012_standard_library_metadata
Revises: 0011_client_company_project_tables
Create Date: 2026-05-23 18:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0012_standard_library_metadata'
down_revision: str | None = '0011_client_company_project_tables'
_unused_branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'standard_documents',
        sa.Column('standard_code', sa.String(length=64), nullable=False),
        sa.Column('standard_name', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=False),
        sa.Column('service_type', sa.String(length=64), nullable=True),
        sa.Column('source_path', sa.String(length=1024), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=False),
        sa.Column('source_format', sa.String(length=32), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('version', sa.String(length=64), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_standard_documents_deleted_at'),
        'standard_documents',
        ['deleted_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_documents_domain'),
        'standard_documents',
        ['domain'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_documents_file_hash'),
        'standard_documents',
        ['file_hash'],
        unique=True,
    )
    op.create_index(
        op.f('ix_standard_documents_service_type'),
        'standard_documents',
        ['service_type'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_documents_standard_code'),
        'standard_documents',
        ['standard_code'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_documents_status'),
        'standard_documents',
        ['status'],
        unique=False,
    )

    op.create_table(
        'standard_chunks',
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_id', sa.String(length=128), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('standard_code', sa.String(length=64), nullable=False),
        sa.Column('standard_name', sa.String(length=255), nullable=False),
        sa.Column('clause', sa.String(length=128), nullable=True),
        sa.Column('domain', sa.String(length=64), nullable=False),
        sa.Column('service_type', sa.String(length=64), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('text_chunk', sa.Text(), nullable=False),
        sa.Column('text_hash', sa.String(length=64), nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('milvus_collection', sa.String(length=128), nullable=True),
        sa.Column('milvus_id', sa.String(length=128), nullable=True),
        sa.Column('embedding_model', sa.String(length=128), nullable=True),
        sa.Column('indexed_at', sa.DateTime(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['standard_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_standard_chunks_chunk_id'),
        'standard_chunks',
        ['chunk_id'],
        unique=True,
    )
    op.create_index(
        op.f('ix_standard_chunks_clause'),
        'standard_chunks',
        ['clause'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_deleted_at'),
        'standard_chunks',
        ['deleted_at'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_document_id'),
        'standard_chunks',
        ['document_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_domain'),
        'standard_chunks',
        ['domain'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_milvus_collection'),
        'standard_chunks',
        ['milvus_collection'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_milvus_id'),
        'standard_chunks',
        ['milvus_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_service_type'),
        'standard_chunks',
        ['service_type'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_standard_code'),
        'standard_chunks',
        ['standard_code'],
        unique=False,
    )
    op.create_index(
        op.f('ix_standard_chunks_text_hash'),
        'standard_chunks',
        ['text_hash'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_standard_chunks_text_hash'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_standard_code'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_service_type'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_milvus_id'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_milvus_collection'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_domain'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_document_id'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_deleted_at'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_clause'), table_name='standard_chunks')
    op.drop_index(op.f('ix_standard_chunks_chunk_id'), table_name='standard_chunks')
    op.drop_table('standard_chunks')

    op.drop_index(op.f('ix_standard_documents_status'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_standard_code'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_service_type'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_file_hash'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_domain'), table_name='standard_documents')
    op.drop_index(op.f('ix_standard_documents_deleted_at'), table_name='standard_documents')
    op.drop_table('standard_documents')
