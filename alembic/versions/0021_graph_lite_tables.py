"""add graph-lite standard rules and compliance evidence

Revision ID: 0021_graph_lite_tables
Revises: 0020_standard_sources
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision: str = '0021_graph_lite_tables'
down_revision: str | None = '0020_standard_sources'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

standard_clause_type = sa.Enum(
    'DEFINITION',
    'REQUIREMENT',
    'LIMIT',
    'METHOD',
    'APPENDIX',
    'TABLE',
    'OTHER',
    name='standard_clause_type',
)
standard_clause_status = sa.Enum('ACTIVE', 'DEPRECATED', name='standard_clause_status')
standard_graph_node_type = sa.Enum(
    'STANDARD',
    'CLAUSE',
    'LIMIT',
    'INDICATOR',
    'INDUSTRY',
    'REGION',
    'MEDIUM',
    'RULE',
    name='standard_graph_node_type',
)
standard_relation_type = sa.Enum(
    'REPLACES',
    'REPLACED_BY',
    'CITES',
    'REFINES',
    'APPLIES_TO',
    'EXCLUDES',
    'REQUIRES',
    'RELATED_TO',
    name='standard_relation_type',
)
standard_relation_source_type = sa.Enum(
    'HUMAN',
    'IMPORT',
    'LLM_SUGGESTED',
    name='standard_relation_source_type',
)
standard_rule_review_status = sa.Enum(
    'PENDING',
    'APPROVED',
    'REJECTED',
    'EXPIRED',
    name='standard_rule_review_status',
)
compliance_evidence_type = sa.Enum(
    'LIMIT_MATCH',
    'APPLICABILITY',
    'PRECEDENCE',
    'CALCULATION',
    'CITATION',
    name='compliance_evidence_type',
)
report_type_enum = mysql.ENUM(
    'OCCUPATIONAL_HEALTH',
    'WASTEWATER',
    'EXHAUST_GAS',
    'NOISE',
    'HIGH_TEMPERATURE',
)
sample_medium_enum = mysql.ENUM(
    'WORKPLACE_AIR',
    'WASTEWATER',
    'EXHAUST_GAS',
    'NOISE',
    'HIGH_TEMPERATURE',
    'PHYSICAL_FACTOR',
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
        'standard_clauses',
        *_audit_columns(),
        sa.Column('document_id', sa.String(length=36), nullable=True),
        sa.Column('standard_code', sa.String(length=64), nullable=False),
        sa.Column('standard_name', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=64), nullable=True),
        sa.Column('clause_code', sa.String(length=128), nullable=False),
        sa.Column('clause_title', sa.String(length=255), nullable=True),
        sa.Column('clause_type', standard_clause_type, nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('text_hash', sa.String(length=64), nullable=True),
        sa.Column('source_uri', sa.String(length=1024), nullable=True),
        sa.Column('status', standard_clause_status, nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['standard_documents.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'standard_code',
            'version',
            'clause_code',
            name='uq_standard_clauses_code_version_clause',
        ),
    )
    op.create_index(op.f('ix_standard_clauses_clause_code'), 'standard_clauses', ['clause_code'])
    op.create_index(op.f('ix_standard_clauses_clause_type'), 'standard_clauses', ['clause_type'])
    op.create_index(op.f('ix_standard_clauses_deleted_at'), 'standard_clauses', ['deleted_at'])
    op.create_index(op.f('ix_standard_clauses_document_id'), 'standard_clauses', ['document_id'])
    op.create_index(op.f('ix_standard_clauses_effective_to'), 'standard_clauses', ['effective_to'])
    op.create_index(op.f('ix_standard_clauses_standard_code'), 'standard_clauses', ['standard_code'])
    op.create_index(op.f('ix_standard_clauses_status'), 'standard_clauses', ['status'])
    op.create_index(op.f('ix_standard_clauses_text_hash'), 'standard_clauses', ['text_hash'])
    op.create_index(op.f('ix_standard_clauses_version'), 'standard_clauses', ['version'])

    op.create_table(
        'standard_relations',
        *_audit_columns(),
        sa.Column('subject_type', standard_graph_node_type, nullable=False),
        sa.Column('subject_id', sa.String(length=128), nullable=False),
        sa.Column('relation_type', standard_relation_type, nullable=False),
        sa.Column('object_type', standard_graph_node_type, nullable=False),
        sa.Column('object_id', sa.String(length=128), nullable=False),
        sa.Column('confidence', sa.Numeric(5, 4), nullable=True),
        sa.Column('source_type', standard_relation_source_type, nullable=False),
        sa.Column('is_verified', sa.Integer(), nullable=False),
        sa.Column('verified_by_id', sa.String(length=36), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['verified_by_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_standard_relations_deleted_at'), 'standard_relations', ['deleted_at'])
    op.create_index(op.f('ix_standard_relations_is_verified'), 'standard_relations', ['is_verified'])
    op.create_index(op.f('ix_standard_relations_object_id'), 'standard_relations', ['object_id'])
    op.create_index(op.f('ix_standard_relations_object_type'), 'standard_relations', ['object_type'])
    op.create_index(
        op.f('ix_standard_relations_relation_type'), 'standard_relations', ['relation_type']
    )
    op.create_index(op.f('ix_standard_relations_source_type'), 'standard_relations', ['source_type'])
    op.create_index(op.f('ix_standard_relations_subject_id'), 'standard_relations', ['subject_id'])
    op.create_index(
        op.f('ix_standard_relations_subject_type'), 'standard_relations', ['subject_type']
    )
    op.create_index(
        op.f('ix_standard_relations_verified_by_id'), 'standard_relations', ['verified_by_id']
    )

    op.create_table(
        'standard_applicability_rules',
        *_audit_columns(),
        sa.Column('standard_code', sa.String(length=64), nullable=False),
        sa.Column('clause_id', sa.String(length=36), nullable=True),
        sa.Column('report_type', report_type_enum, nullable=True),
        sa.Column('medium', sample_medium_enum, nullable=True),
        sa.Column('industry', sa.String(length=128), nullable=True),
        sa.Column('region', sa.String(length=64), nullable=True),
        sa.Column('pollutant_category', sa.String(length=128), nullable=True),
        sa.Column('indicator_name', sa.String(length=128), nullable=True),
        sa.Column('cas_no', sa.String(length=32), nullable=True),
        sa.Column('process_type', sa.String(length=128), nullable=True),
        sa.Column('applicability_json', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('review_status', standard_rule_review_status, nullable=False),
        sa.ForeignKeyConstraint(['clause_id'], ['standard_clauses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_cas_no'),
        'standard_applicability_rules',
        ['cas_no'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_clause_id'),
        'standard_applicability_rules',
        ['clause_id'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_deleted_at'),
        'standard_applicability_rules',
        ['deleted_at'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_effective_to'),
        'standard_applicability_rules',
        ['effective_to'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_indicator_name'),
        'standard_applicability_rules',
        ['indicator_name'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_industry'),
        'standard_applicability_rules',
        ['industry'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_medium'),
        'standard_applicability_rules',
        ['medium'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_pollutant_category'),
        'standard_applicability_rules',
        ['pollutant_category'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_priority'),
        'standard_applicability_rules',
        ['priority'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_process_type'),
        'standard_applicability_rules',
        ['process_type'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_region'),
        'standard_applicability_rules',
        ['region'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_report_type'),
        'standard_applicability_rules',
        ['report_type'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_review_status'),
        'standard_applicability_rules',
        ['review_status'],
    )
    op.create_index(
        op.f('ix_standard_applicability_rules_standard_code'),
        'standard_applicability_rules',
        ['standard_code'],
    )

    op.create_table(
        'standard_precedence_rules',
        *_audit_columns(),
        sa.Column('rule_name', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=64), nullable=True),
        sa.Column('region', sa.String(length=64), nullable=True),
        sa.Column('industry', sa.String(length=128), nullable=True),
        sa.Column('higher_standard_code', sa.String(length=64), nullable=False),
        sa.Column('lower_standard_code', sa.String(length=64), nullable=False),
        sa.Column('condition_json', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('source_clause_id', sa.String(length=36), nullable=True),
        sa.Column('review_status', standard_rule_review_status, nullable=False),
        sa.ForeignKeyConstraint(['source_clause_id'], ['standard_clauses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_standard_precedence_rules_deleted_at'),
        'standard_precedence_rules',
        ['deleted_at'],
    )
    op.create_index(op.f('ix_standard_precedence_rules_domain'), 'standard_precedence_rules', ['domain'])
    op.create_index(
        op.f('ix_standard_precedence_rules_higher_standard_code'),
        'standard_precedence_rules',
        ['higher_standard_code'],
    )
    op.create_index(
        op.f('ix_standard_precedence_rules_industry'),
        'standard_precedence_rules',
        ['industry'],
    )
    op.create_index(
        op.f('ix_standard_precedence_rules_lower_standard_code'),
        'standard_precedence_rules',
        ['lower_standard_code'],
    )
    op.create_index(
        op.f('ix_standard_precedence_rules_priority'), 'standard_precedence_rules', ['priority']
    )
    op.create_index(op.f('ix_standard_precedence_rules_region'), 'standard_precedence_rules', ['region'])
    op.create_index(
        op.f('ix_standard_precedence_rules_review_status'),
        'standard_precedence_rules',
        ['review_status'],
    )
    op.create_index(
        op.f('ix_standard_precedence_rules_rule_name'),
        'standard_precedence_rules',
        ['rule_name'],
    )
    op.create_index(
        op.f('ix_standard_precedence_rules_source_clause_id'),
        'standard_precedence_rules',
        ['source_clause_id'],
    )

    op.create_table(
        'compliance_evidence',
        *_audit_columns(),
        sa.Column('report_id', sa.String(length=36), nullable=False),
        sa.Column('sample_id', sa.String(length=36), nullable=True),
        sa.Column('measurement_id', sa.String(length=36), nullable=True),
        sa.Column('result_id', sa.String(length=36), nullable=True),
        sa.Column('standard_code', sa.String(length=64), nullable=True),
        sa.Column('standard_name', sa.String(length=255), nullable=True),
        sa.Column('clause_id', sa.String(length=36), nullable=True),
        sa.Column('limit_id', sa.String(length=36), nullable=True),
        sa.Column('source_id', sa.String(length=36), nullable=True),
        sa.Column('source_uri', sa.String(length=1024), nullable=True),
        sa.Column('evidence_type', compliance_evidence_type, nullable=False),
        sa.Column('evidence_summary', sa.Text(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['clause_id'], ['standard_clauses.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['limit_id'], ['regulatory_limits.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['measurement_id'], ['detection_measurements.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['report_id'], ['detection_reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['result_id'], ['compliance_results.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sample_id'], ['detection_samples.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_id'], ['standard_sources.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_compliance_evidence_clause_id'), 'compliance_evidence', ['clause_id'])
    op.create_index(op.f('ix_compliance_evidence_deleted_at'), 'compliance_evidence', ['deleted_at'])
    op.create_index(
        op.f('ix_compliance_evidence_evidence_type'), 'compliance_evidence', ['evidence_type']
    )
    op.create_index(op.f('ix_compliance_evidence_limit_id'), 'compliance_evidence', ['limit_id'])
    op.create_index(
        op.f('ix_compliance_evidence_measurement_id'), 'compliance_evidence', ['measurement_id']
    )
    op.create_index(op.f('ix_compliance_evidence_report_id'), 'compliance_evidence', ['report_id'])
    op.create_index(op.f('ix_compliance_evidence_result_id'), 'compliance_evidence', ['result_id'])
    op.create_index(op.f('ix_compliance_evidence_sample_id'), 'compliance_evidence', ['sample_id'])
    op.create_index(
        op.f('ix_compliance_evidence_standard_code'), 'compliance_evidence', ['standard_code']
    )
    op.create_index(op.f('ix_compliance_evidence_source_id'), 'compliance_evidence', ['source_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_compliance_evidence_source_id'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_standard_code'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_sample_id'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_result_id'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_report_id'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_measurement_id'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_limit_id'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_evidence_type'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_deleted_at'), table_name='compliance_evidence')
    op.drop_index(op.f('ix_compliance_evidence_clause_id'), table_name='compliance_evidence')
    op.drop_table('compliance_evidence')

    op.drop_index(
        op.f('ix_standard_precedence_rules_source_clause_id'),
        table_name='standard_precedence_rules',
    )
    op.drop_index(op.f('ix_standard_precedence_rules_rule_name'), table_name='standard_precedence_rules')
    op.drop_index(
        op.f('ix_standard_precedence_rules_review_status'),
        table_name='standard_precedence_rules',
    )
    op.drop_index(op.f('ix_standard_precedence_rules_region'), table_name='standard_precedence_rules')
    op.drop_index(
        op.f('ix_standard_precedence_rules_priority'), table_name='standard_precedence_rules'
    )
    op.drop_index(
        op.f('ix_standard_precedence_rules_lower_standard_code'),
        table_name='standard_precedence_rules',
    )
    op.drop_index(
        op.f('ix_standard_precedence_rules_industry'), table_name='standard_precedence_rules'
    )
    op.drop_index(
        op.f('ix_standard_precedence_rules_higher_standard_code'),
        table_name='standard_precedence_rules',
    )
    op.drop_index(op.f('ix_standard_precedence_rules_domain'), table_name='standard_precedence_rules')
    op.drop_index(
        op.f('ix_standard_precedence_rules_deleted_at'), table_name='standard_precedence_rules'
    )
    op.drop_table('standard_precedence_rules')

    op.drop_index(
        op.f('ix_standard_applicability_rules_standard_code'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_review_status'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_report_type'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_region'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_process_type'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_priority'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_pollutant_category'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_medium'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_industry'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_indicator_name'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_effective_to'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_deleted_at'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_clause_id'),
        table_name='standard_applicability_rules',
    )
    op.drop_index(
        op.f('ix_standard_applicability_rules_cas_no'),
        table_name='standard_applicability_rules',
    )
    op.drop_table('standard_applicability_rules')

    op.drop_index(op.f('ix_standard_relations_verified_by_id'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_subject_type'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_subject_id'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_source_type'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_relation_type'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_object_type'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_object_id'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_is_verified'), table_name='standard_relations')
    op.drop_index(op.f('ix_standard_relations_deleted_at'), table_name='standard_relations')
    op.drop_table('standard_relations')

    op.drop_index(op.f('ix_standard_clauses_version'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_text_hash'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_status'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_standard_code'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_effective_to'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_document_id'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_deleted_at'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_clause_type'), table_name='standard_clauses')
    op.drop_index(op.f('ix_standard_clauses_clause_code'), table_name='standard_clauses')
    op.drop_table('standard_clauses')

    compliance_evidence_type.drop(op.get_bind(), checkfirst=True)
    standard_rule_review_status.drop(op.get_bind(), checkfirst=True)
    standard_relation_source_type.drop(op.get_bind(), checkfirst=True)
    standard_relation_type.drop(op.get_bind(), checkfirst=True)
    standard_graph_node_type.drop(op.get_bind(), checkfirst=True)
    standard_clause_status.drop(op.get_bind(), checkfirst=True)
    standard_clause_type.drop(op.get_bind(), checkfirst=True)
