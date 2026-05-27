"""add report pipeline section drafts

Revision ID: 0016_report_pipeline_sections
Revises: 0015_agent_memories
Create Date: 2026-05-27 21:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0016_report_pipeline_sections'
down_revision: str | None = '0015_agent_memories'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

report_section_citation_check_status = sa.Enum(
    'PENDING',
    'PASSED',
    'FAILED',
    name='report_section_citation_check_status',
)
report_section_review_status = sa.Enum(
    'DRAFT',
    'IN_REVIEW',
    'APPROVED',
    'REJECTED',
    name='report_section_review_status',
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
        'report_sections',
        *_audit_columns(),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('report_id', sa.String(length=36), nullable=False),
        sa.Column('section_key', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('draft_content', sa.Text(), nullable=False),
        sa.Column('citation_memory_ids_json', sa.Text(), nullable=True),
        sa.Column('citation_check_status', report_section_citation_check_status, nullable=False),
        sa.Column('citation_check_message', sa.Text(), nullable=True),
        sa.Column('review_status', report_section_review_status, nullable=False),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('reviewed_by_id', sa.String(length=36), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['report_id'], ['detection_reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('report_id', 'section_key', name='uq_report_sections_report_id_section_key'),
    )
    op.create_index(op.f('ix_report_sections_citation_check_status'), 'report_sections', ['citation_check_status'])
    op.create_index(op.f('ix_report_sections_created_by_id'), 'report_sections', ['created_by_id'])
    op.create_index(op.f('ix_report_sections_deleted_at'), 'report_sections', ['deleted_at'])
    op.create_index(op.f('ix_report_sections_organization_id'), 'report_sections', ['organization_id'])
    op.create_index(op.f('ix_report_sections_report_id'), 'report_sections', ['report_id'])
    op.create_index(op.f('ix_report_sections_review_status'), 'report_sections', ['review_status'])
    op.create_index(op.f('ix_report_sections_reviewed_by_id'), 'report_sections', ['reviewed_by_id'])
    op.create_index(op.f('ix_report_sections_section_key'), 'report_sections', ['section_key'])


def downgrade() -> None:
    op.drop_index(op.f('ix_report_sections_section_key'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_reviewed_by_id'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_review_status'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_report_id'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_organization_id'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_deleted_at'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_created_by_id'), table_name='report_sections')
    op.drop_index(op.f('ix_report_sections_citation_check_status'), table_name='report_sections')
    op.drop_table('report_sections')
