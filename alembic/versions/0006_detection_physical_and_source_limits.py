"""detection physical factors and source limits

Revision ID: 0006_detection_physical_and_source_limits
Revises: 0005_detection_compliance
"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

revision = '0006_detection_physical_and_source_limits'
down_revision = '0005_detection_compliance'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.execute(
            "ALTER TABLE detection_samples MODIFY medium "
            "ENUM('WORKPLACE_AIR','WASTEWATER','EXHAUST_GAS','NOISE','HIGH_TEMPERATURE','PHYSICAL_FACTOR') "
            "NOT NULL"
        )
        op.execute(
            "ALTER TABLE regulatory_limits MODIFY medium "
            "ENUM('WORKPLACE_AIR','WASTEWATER','EXHAUST_GAS','NOISE','HIGH_TEMPERATURE','PHYSICAL_FACTOR') "
            "NOT NULL"
        )
    op.add_column(
        'detection_measurements',
        sa.Column('source_limit_value', sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        'detection_measurements',
        sa.Column('source_limit_unit', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'detection_measurements',
        sa.Column(
            'source_limit_type',
            mysql.ENUM('MAC', 'PC_TWA', 'PC_STEL', 'DAILY_AVG', 'INSTANT', 'RANGE'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('detection_measurements', 'source_limit_type')
    op.drop_column('detection_measurements', 'source_limit_unit')
    op.drop_column('detection_measurements', 'source_limit_value')
    bind = op.get_bind()
    if bind.dialect.name == 'mysql':
        op.execute(
            "ALTER TABLE detection_samples MODIFY medium "
            "ENUM('WORKPLACE_AIR','WASTEWATER','EXHAUST_GAS','NOISE','HIGH_TEMPERATURE') "
            "NOT NULL"
        )
        op.execute(
            "ALTER TABLE regulatory_limits MODIFY medium "
            "ENUM('WORKPLACE_AIR','WASTEWATER','EXHAUST_GAS','NOISE','HIGH_TEMPERATURE') "
            "NOT NULL"
        )
