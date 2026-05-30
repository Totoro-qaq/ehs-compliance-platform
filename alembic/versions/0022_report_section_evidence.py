"""add report section evidence bindings

Revision ID: 0022_report_section_evidence
Revises: 0021_graph_lite_tables
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '0022_report_section_evidence'
down_revision: str | None = '0021_graph_lite_tables'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

report_section_citation_check_status = sa.Enum(
    'PENDING',
    'PASSED',
    'FAILED',
    name='report_section_citation_check_status',
)


def upgrade() -> None:
    op.add_column('report_sections', sa.Column('evidence_ids_json', sa.Text(), nullable=True))
    op.add_column(
        'report_sections',
        sa.Column(
            'evidence_check_status',
            report_section_citation_check_status,
            nullable=False,
            server_default='PENDING',
        ),
    )
    op.add_column('report_sections', sa.Column('evidence_check_message', sa.Text(), nullable=True))
    op.create_index(
        op.f('ix_report_sections_evidence_check_status'),
        'report_sections',
        ['evidence_check_status'],
    )
    op.alter_column('report_sections', 'evidence_check_status', server_default=None)


def downgrade() -> None:
    op.drop_index(op.f('ix_report_sections_evidence_check_status'), table_name='report_sections')
    op.drop_column('report_sections', 'evidence_check_message')
    op.drop_column('report_sections', 'evidence_check_status')
    op.drop_column('report_sections', 'evidence_ids_json')
