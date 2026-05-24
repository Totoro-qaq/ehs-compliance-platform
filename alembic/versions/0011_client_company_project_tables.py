"""retire client company and project tables from MVP scope

Revision ID: 0011_client_company_project_tables
Revises: 0010_client_project_fields
Create Date: 2026-05-23 16:30:00.000000

This revision ID existed briefly while the project table design was still
being evaluated. The current MVP keeps only lightweight client/project context
fields on assessment_tasks and detection_reports, so this compatibility
revision intentionally does not create standalone client tables.
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = '0011_client_company_project_tables'
_unused_down_revision: str | None = '0010_client_project_fields'
down_revision: str | None = _unused_down_revision
_unused_branch_labels: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = _unused_branch_labels
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
