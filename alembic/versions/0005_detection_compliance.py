"""detection compliance module

Revision ID: 0005_detection_compliance
Revises: 0004_assessment_timeline_events
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = '0005_detection_compliance'
down_revision = '0004_assessment_timeline_events'
branch_labels = None
depends_on = None


report_type_enum = mysql.ENUM(
    'OCCUPATIONAL_HEALTH', 'WASTEWATER', 'EXHAUST_GAS', 'NOISE', 'HIGH_TEMPERATURE'
)
report_status_enum = mysql.ENUM(
    'UPLOADED', 'PARSED', 'VALIDATED', 'CALCULATED', 'FAILED'
)
sample_medium_enum = mysql.ENUM(
    'WORKPLACE_AIR', 'WASTEWATER', 'EXHAUST_GAS', 'NOISE', 'HIGH_TEMPERATURE'
)
limit_type_enum = mysql.ENUM(
    'MAC', 'PC_TWA', 'PC_STEL', 'DAILY_AVG', 'INSTANT', 'RANGE'
)
compliance_status_enum = mysql.ENUM(
    'COMPLIANT', 'EXCEEDED', 'BORDERLINE', 'INSUFFICIENT_DATA', 'NEEDS_REVIEW'
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
        'detection_reports',
        *_audit_columns(),
        sa.Column('organization_id', sa.String(length=36), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('report_type', report_type_enum, nullable=False),
        sa.Column('status', report_status_enum, nullable=False),
        sa.Column('report_date', sa.Date(), nullable=True),
        sa.Column('issuer', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_detection_reports_deleted_at', 'detection_reports', ['deleted_at'])
    op.create_index('ix_detection_reports_organization_id', 'detection_reports', ['organization_id'])
    op.create_index('ix_detection_reports_report_type', 'detection_reports', ['report_type'])
    op.create_index('ix_detection_reports_created_by_id', 'detection_reports', ['created_by_id'])

    op.create_table(
        'detection_samples',
        *_audit_columns(),
        sa.Column('report_id', sa.String(length=36), nullable=False),
        sa.Column('sample_point', sa.String(length=255), nullable=False),
        sa.Column('workplace', sa.String(length=255), nullable=True),
        sa.Column('post_name', sa.String(length=255), nullable=True),
        sa.Column('medium', sample_medium_enum, nullable=False),
        sa.Column('sample_time_start', sa.DateTime(), nullable=True),
        sa.Column('sample_time_end', sa.DateTime(), nullable=True),
        sa.Column('duration_minutes', sa.Numeric(10, 2), nullable=True),
        sa.Column('shift_hours', sa.Numeric(6, 2), nullable=True),
        sa.Column('raw_payload_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['report_id'], ['detection_reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_detection_samples_deleted_at', 'detection_samples', ['deleted_at'])
    op.create_index('ix_detection_samples_report_id', 'detection_samples', ['report_id'])
    op.create_index('ix_detection_samples_medium', 'detection_samples', ['medium'])

    op.create_table(
        'detection_measurements',
        *_audit_columns(),
        sa.Column('sample_id', sa.String(length=36), nullable=False),
        sa.Column('indicator_name', sa.String(length=128), nullable=False),
        sa.Column('indicator_alias', sa.String(length=255), nullable=True),
        sa.Column('cas_no', sa.String(length=32), nullable=True),
        sa.Column('raw_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('raw_unit', sa.String(length=32), nullable=True),
        sa.Column('normalized_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('normalized_unit', sa.String(length=32), nullable=True),
        sa.Column('detect_limit', sa.Numeric(18, 6), nullable=True),
        sa.Column('method_code', sa.String(length=64), nullable=True),
        sa.Column('raw_text', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['sample_id'], ['detection_samples.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_detection_measurements_deleted_at', 'detection_measurements', ['deleted_at'])
    op.create_index('ix_detection_measurements_sample_id', 'detection_measurements', ['sample_id'])
    op.create_index('ix_detection_measurements_indicator_name', 'detection_measurements', ['indicator_name'])
    op.create_index('ix_detection_measurements_cas_no', 'detection_measurements', ['cas_no'])

    op.create_table(
        'regulatory_limits',
        *_audit_columns(),
        sa.Column('indicator_name', sa.String(length=128), nullable=False),
        sa.Column('cas_no', sa.String(length=32), nullable=True),
        sa.Column('aliases_json', sa.Text(), nullable=True),
        sa.Column('medium', sample_medium_enum, nullable=False),
        sa.Column('limit_type', limit_type_enum, nullable=False),
        sa.Column('limit_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('limit_min', sa.Numeric(18, 6), nullable=True),
        sa.Column('limit_max', sa.Numeric(18, 6), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('standard_code', sa.String(length=64), nullable=False),
        sa.Column('standard_name', sa.String(length=255), nullable=False),
        sa.Column('clause', sa.String(length=128), nullable=True),
        sa.Column('basis_text', sa.Text(), nullable=True),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('applicability_json', sa.Text(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_regulatory_limits_deleted_at', 'regulatory_limits', ['deleted_at'])
    op.create_index('ix_regulatory_limits_indicator_name', 'regulatory_limits', ['indicator_name'])
    op.create_index('ix_regulatory_limits_cas_no', 'regulatory_limits', ['cas_no'])
    op.create_index('ix_regulatory_limits_medium', 'regulatory_limits', ['medium'])
    op.create_index('ix_regulatory_limits_limit_type', 'regulatory_limits', ['limit_type'])
    op.create_index('ix_regulatory_limits_standard_code', 'regulatory_limits', ['standard_code'])

    op.create_table(
        'compliance_results',
        *_audit_columns(),
        sa.Column('report_id', sa.String(length=36), nullable=False),
        sa.Column('sample_id', sa.String(length=36), nullable=False),
        sa.Column('measurement_id', sa.String(length=36), nullable=False),
        sa.Column('limit_id', sa.String(length=36), nullable=True),
        sa.Column('calculated_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('calculated_unit', sa.String(length=32), nullable=True),
        sa.Column('limit_value', sa.Numeric(18, 6), nullable=True),
        sa.Column('limit_unit', sa.String(length=32), nullable=True),
        sa.Column('limit_type', limit_type_enum, nullable=True),
        sa.Column('status', compliance_status_enum, nullable=False),
        sa.Column('exceedance_multiple', sa.Numeric(12, 4), nullable=True),
        sa.Column('standard_code', sa.String(length=64), nullable=True),
        sa.Column('standard_name', sa.String(length=255), nullable=True),
        sa.Column('clause', sa.String(length=128), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['report_id'], ['detection_reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sample_id'], ['detection_samples.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['measurement_id'], ['detection_measurements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['limit_id'], ['regulatory_limits.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_compliance_results_deleted_at', 'compliance_results', ['deleted_at'])
    op.create_index('ix_compliance_results_report_id', 'compliance_results', ['report_id'])
    op.create_index('ix_compliance_results_sample_id', 'compliance_results', ['sample_id'])
    op.create_index('ix_compliance_results_measurement_id', 'compliance_results', ['measurement_id'])
    op.create_index('ix_compliance_results_limit_id', 'compliance_results', ['limit_id'])
    op.create_index('ix_compliance_results_status', 'compliance_results', ['status'])


def downgrade() -> None:
    op.drop_table('compliance_results')
    op.drop_table('regulatory_limits')
    op.drop_table('detection_measurements')
    op.drop_table('detection_samples')
    op.drop_table('detection_reports')
