from __future__ import annotations

import json
import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import EHSException
from app.core.patterns import is_uuid
from app.dao.detection_dao import DetectionReportDAO
from app.dao.report_pipeline_dao import ReportSectionDAO
from app.models.base import audit_now_naive
from app.models.db_models import (
    AgentMemory,
    AgentMemoryType,
    DetectionReport,
    ReportSection,
    ReportSectionCitationCheckStatus,
    ReportSectionReviewStatus,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.report_pipeline_schema import ReportSectionOut
from app.services.access_control import (
    ensure_org_admin_or_system_admin,
    ensure_organization_scope,
    is_system_admin,
)

_SECTION_KEY_RE = re.compile(r'^[A-Za-z0-9_.-]+$')
_MAX_CITATION_IDS = 50


class ReportPipelineService:
    @staticmethod
    def upsert_section(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
        section_key: str,
        title: str,
        draft_content: str,
        citation_memory_ids: list[str],
    ) -> ReportSectionOut:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        normalized_section_key = _normalize_section_key(section_key)
        normalized_title = _clean_required_text(title, field_name='title', max_length=255)
        normalized_content = _clean_required_text(draft_content, field_name='draft_content')
        normalized_citation_ids = _normalize_citation_ids(citation_memory_ids)
        citation_status, citation_message = _check_citations(
            db=db,
            actor=actor,
            organization_id=report.organization_id,
            citation_memory_ids=normalized_citation_ids,
        )

        section = ReportSectionDAO(db).upsert_section(
            organization_id=report.organization_id,
            report_id=report.id,
            section_key=normalized_section_key,
            title=normalized_title,
            draft_content=normalized_content,
            citation_memory_ids_json=_dump_citation_ids(normalized_citation_ids),
            citation_check_status=citation_status,
            citation_check_message=citation_message,
            created_by_id=actor.account_id,
        )
        db.commit()
        db.refresh(section)
        return _section_out(section)

    @staticmethod
    def list_sections(*, db: Session, actor: CurrentUser, report_id: str) -> list[ReportSectionOut]:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        sections = ReportSectionDAO(db).list_by_report(report.id)
        return [_section_out(section) for section in sections]

    @staticmethod
    def update_review_status(
        *,
        db: Session,
        actor: CurrentUser,
        section_id: str,
        review_status: ReportSectionReviewStatus,
        review_note: str | None,
    ) -> ReportSectionOut:
        section = _get_scoped_section(db=db, actor=actor, section_id=section_id)
        ensure_org_admin_or_system_admin(actor, section.organization_id)
        if review_status == ReportSectionReviewStatus.DRAFT:
            raise EHSException(
                'DRAFT status is managed by section draft updates',
                code='REPORT_SECTION_INVALID_REVIEW_STATUS',
                status_code=400,
            )
        if (
            review_status == ReportSectionReviewStatus.APPROVED
            and section.citation_check_status != ReportSectionCitationCheckStatus.PASSED
        ):
            raise EHSException(
                'Report section citations must pass before approval',
                code='REPORT_SECTION_CITATIONS_NOT_PASSED',
                status_code=400,
            )

        section.review_status = review_status
        section.review_note = _clean_optional_text(review_note, max_length=1000)
        section.reviewed_by_id = actor.account_id
        section.reviewed_at = audit_now_naive()
        section.updated_at = audit_now_naive()
        db.commit()
        db.refresh(section)
        return _section_out(section)


def _get_scoped_report(*, db: Session, actor: CurrentUser, report_id: str) -> DetectionReport:
    if not is_uuid(report_id):
        raise EHSException(
            'report_id must be a valid UUID',
            code='REPORT_PIPELINE_INVALID_REPORT_ID',
            status_code=400,
        )
    report = DetectionReportDAO(db).get_by_id(report_id)
    if report is None:
        raise EHSException(
            'Detection report not found',
            code='DETECTION_REPORT_NOT_FOUND',
            status_code=404,
        )
    ensure_organization_scope(actor, report.organization_id)
    return report


def _get_scoped_section(*, db: Session, actor: CurrentUser, section_id: str) -> ReportSection:
    if not is_uuid(section_id):
        raise EHSException(
            'section_id must be a valid UUID',
            code='REPORT_PIPELINE_INVALID_SECTION_ID',
            status_code=400,
        )
    section = ReportSectionDAO(db).get_by_id(section_id)
    if section is None:
        raise EHSException(
            'Report section not found',
            code='REPORT_SECTION_NOT_FOUND',
            status_code=404,
        )
    ensure_organization_scope(actor, section.organization_id)
    return section


def _normalize_section_key(section_key: str) -> str:
    normalized = _clean_required_text(section_key, field_name='section_key', max_length=64)
    if not _SECTION_KEY_RE.fullmatch(normalized):
        raise EHSException(
            'section_key only allows letters, numbers, dot, underscore and hyphen',
            code='REPORT_SECTION_INVALID_KEY',
            status_code=400,
        )
    return normalized


def _normalize_citation_ids(citation_memory_ids: list[str]) -> list[str]:
    if len(citation_memory_ids) > _MAX_CITATION_IDS:
        raise EHSException(
            'Too many citation memory ids',
            code='REPORT_SECTION_TOO_MANY_CITATIONS',
            status_code=400,
            details={'max': _MAX_CITATION_IDS},
        )
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in citation_memory_ids:
        citation_id = (raw_id or '').strip()
        if not is_uuid(citation_id):
            raise EHSException(
                'citation_memory_ids must be valid UUID strings',
                code='REPORT_SECTION_INVALID_CITATION_ID',
                status_code=400,
            )
        if citation_id not in seen:
            normalized_ids.append(citation_id)
            seen.add(citation_id)
    return normalized_ids


def _check_citations(
    *,
    db: Session,
    actor: CurrentUser,
    organization_id: str,
    citation_memory_ids: list[str],
) -> tuple[ReportSectionCitationCheckStatus, str | None]:
    if not citation_memory_ids:
        return ReportSectionCitationCheckStatus.PENDING, 'No citation memory ids supplied'

    filters = [
        AgentMemory.id.in_(citation_memory_ids),
        AgentMemory.organization_id == organization_id,
        AgentMemory.memory_type == AgentMemoryType.CITATION,
        AgentMemory.deleted_at.is_(None),
        or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > audit_now_naive()),
    ]
    if not is_system_admin(actor):
        filters.append(or_(AgentMemory.account_id.is_(None), AgentMemory.account_id == actor.account_id))

    found_ids = set(db.scalars(select(AgentMemory.id).where(*filters)).all())
    missing_ids = [citation_id for citation_id in citation_memory_ids if citation_id not in found_ids]
    if missing_ids:
        return (
            ReportSectionCitationCheckStatus.FAILED,
            f'Invalid or invisible citation memory ids: {", ".join(missing_ids[:5])}',
        )
    return ReportSectionCitationCheckStatus.PASSED, None


def _clean_required_text(value: str, *, field_name: str, max_length: int | None = None) -> str:
    cleaned = ' '.join(value.strip().split()) if field_name != 'draft_content' else value.strip()
    if not cleaned:
        raise EHSException(
            f'{field_name} is required',
            code='REPORT_SECTION_REQUIRED_FIELD',
            status_code=400,
            details={'field': field_name},
        )
    return cleaned[:max_length] if max_length is not None else cleaned


def _clean_optional_text(value: str | None, *, max_length: int) -> str | None:
    cleaned = (value or '').strip()
    return cleaned[:max_length] if cleaned else None


def _dump_citation_ids(citation_memory_ids: list[str]) -> str | None:
    if not citation_memory_ids:
        return None
    return json.dumps(citation_memory_ids, ensure_ascii=False)


def _load_citation_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def _section_out(section: ReportSection) -> ReportSectionOut:
    return ReportSectionOut(
        id=section.id,
        organization_id=section.organization_id,
        report_id=section.report_id,
        section_key=section.section_key,
        title=section.title,
        draft_content=section.draft_content,
        citation_memory_ids=_load_citation_ids(section.citation_memory_ids_json),
        citation_check_status=section.citation_check_status,
        citation_check_message=section.citation_check_message,
        review_status=section.review_status,
        review_note=section.review_note,
        reviewed_by_id=section.reviewed_by_id,
        reviewed_at=section.reviewed_at,
        created_by_id=section.created_by_id,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )
