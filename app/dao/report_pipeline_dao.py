from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import (
    ReportSection,
    ReportSectionCitationCheckStatus,
    ReportSectionReviewStatus,
)


class ReportSectionDAO(BaseRepository[ReportSection]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ReportSection)

    def find_by_report_section(self, *, report_id: str, section_key: str) -> ReportSection | None:
        stmt = select(ReportSection).where(
            ReportSection.report_id == report_id,
            ReportSection.section_key == section_key,
            ReportSection.deleted_at.is_(None),
        )
        return self.session.scalars(stmt).one_or_none()

    def list_by_report(self, report_id: str) -> list[ReportSection]:
        stmt = (
            select(ReportSection)
            .where(ReportSection.report_id == report_id, ReportSection.deleted_at.is_(None))
            .order_by(ReportSection.section_key.asc(), ReportSection.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def upsert_section(
        self,
        *,
        organization_id: str,
        report_id: str,
        section_key: str,
        title: str,
        draft_content: str,
        citation_memory_ids_json: str | None,
        evidence_ids_json: str | None,
        citation_check_status: ReportSectionCitationCheckStatus,
        citation_check_message: str | None,
        evidence_check_status: ReportSectionCitationCheckStatus,
        evidence_check_message: str | None,
        created_by_id: str | None,
    ) -> ReportSection:
        existing = self.find_by_report_section(report_id=report_id, section_key=section_key)
        if existing is not None:
            existing.title = title
            existing.draft_content = draft_content
            existing.citation_memory_ids_json = citation_memory_ids_json
            existing.evidence_ids_json = evidence_ids_json
            existing.citation_check_status = citation_check_status
            existing.citation_check_message = citation_check_message
            existing.evidence_check_status = evidence_check_status
            existing.evidence_check_message = evidence_check_message
            existing.review_status = ReportSectionReviewStatus.DRAFT
            existing.review_note = None
            existing.reviewed_by_id = None
            existing.reviewed_at = None
            existing.updated_at = audit_now_naive()
            self.session.flush()
            return existing

        section = ReportSection(
            organization_id=organization_id,
            report_id=report_id,
            section_key=section_key,
            title=title,
            draft_content=draft_content,
            citation_memory_ids_json=citation_memory_ids_json,
            evidence_ids_json=evidence_ids_json,
            citation_check_status=citation_check_status,
            citation_check_message=citation_check_message,
            evidence_check_status=evidence_check_status,
            evidence_check_message=evidence_check_message,
            created_by_id=created_by_id,
        )
        self.session.add(section)
        self.session.flush()
        return section
