from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.dao.base_repository import BaseRepository
from app.dao.pagination import fetch_scalar_rows_page, normalize_page_params
from app.models.base import audit_now_naive
from app.models.db_models import (
    ComplianceEvidence,
    DetectionReport,
    StandardApplicabilityRule,
    StandardClause,
    StandardClauseStatus,
    StandardDocument,
    StandardPrecedenceRule,
    StandardRelation,
    StandardRuleReviewStatus,
    StandardSourceReviewStatus,
)


class StandardClauseDAO(BaseRepository[StandardClause]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardClause)

    def create_clause(self, *, fields: dict[str, Any]) -> StandardClause:
        entity = StandardClause(**fields)
        self.session.add(entity)
        self.session.flush()
        return entity

    def find_by_standard_clause(
        self,
        *,
        standard_code: str,
        clause_code: str | None,
    ) -> StandardClause | None:
        if not clause_code:
            return None
        stmt = (
            select(StandardClause)
            .where(
                StandardClause.standard_code == standard_code,
                StandardClause.clause_code == clause_code,
                StandardClause.status == StandardClauseStatus.ACTIVE,
            )
            .order_by(StandardClause.updated_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_page_filtered(
        self,
        *,
        page: int,
        page_size: int,
        visible_organization_id: str | None,
        include_unapproved: bool,
        query: str | None = None,
        standard_code: str | None = None,
        document_id: str | None = None,
    ) -> tuple[list[StandardClause], int]:
        filters: list[Any] = []
        if standard_code:
            filters.append(StandardClause.standard_code == standard_code.strip())
        if document_id:
            filters.append(StandardClause.document_id == document_id.strip())
        if query:
            like = f'%{query.strip()}%'
            filters.append(
                or_(
                    StandardClause.standard_code.ilike(like),
                    StandardClause.standard_name.ilike(like),
                    StandardClause.clause_code.ilike(like),
                    StandardClause.clause_title.ilike(like),
                )
            )
        if visible_organization_id is not None:
            filters.append(
                or_(
                    StandardDocument.organization_id.is_(None),
                    StandardDocument.organization_id == visible_organization_id,
                )
            )
        if not include_unapproved:
            filters.extend(
                [
                    StandardClause.document_id.is_not(None),
                    StandardDocument.source_review_status == StandardSourceReviewStatus.APPROVED,
                    StandardDocument.allow_ai_retrieval == 1,
                ]
            )

        params = normalize_page_params(page=page, page_size=page_size, max_page_size=100)
        list_stmt = (
            select(StandardClause)
            .join(StandardDocument, StandardDocument.id == StandardClause.document_id, isouter=True)
            .options(joinedload(StandardClause.document))
            .where(*filters)
            .order_by(
                StandardClause.standard_code.asc(),
                StandardClause.clause_code.asc(),
                StandardClause.updated_at.desc(),
            )
        )
        count_stmt = (
            select(func.count())
            .select_from(StandardClause)
            .join(StandardDocument, StandardDocument.id == StandardClause.document_id, isouter=True)
            .where(*filters)
        )
        rows, total = fetch_scalar_rows_page(
            self.session,
            list_stmt=list_stmt,
            count_stmt=count_stmt,
            params=params,
        )
        return rows, total


class StandardRelationDAO(BaseRepository[StandardRelation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardRelation)

    def create_relation(self, *, fields: dict[str, Any]) -> StandardRelation:
        entity = StandardRelation(**fields)
        self.session.add(entity)
        self.session.flush()
        return entity


class StandardApplicabilityRuleDAO(BaseRepository[StandardApplicabilityRule]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardApplicabilityRule)

    def create_rule(self, *, fields: dict[str, Any]) -> StandardApplicabilityRule:
        entity = StandardApplicabilityRule(**fields)
        self.session.add(entity)
        self.session.flush()
        return entity

    def list_page_filtered(
        self,
        *,
        page: int,
        page_size: int,
        standard_code: str | None = None,
        review_status: StandardRuleReviewStatus | None = None,
        approved_only: bool = True,
    ) -> tuple[list[StandardApplicabilityRule], int]:
        filters: list[Any] = []
        if standard_code:
            filters.append(StandardApplicabilityRule.standard_code == standard_code.strip())
        if review_status is not None:
            filters.append(StandardApplicabilityRule.review_status == review_status)
        elif approved_only:
            filters.append(StandardApplicabilityRule.review_status == StandardRuleReviewStatus.APPROVED)
        return self.list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[
                StandardApplicabilityRule.priority.asc(),
                StandardApplicabilityRule.updated_at.desc(),
            ],
            max_page_size=100,
        )

    def list_approved_for_standard_codes(
        self,
        *,
        standard_codes: Sequence[str],
        as_of: date | None = None,
    ) -> list[StandardApplicabilityRule]:
        codes = sorted({code.strip() for code in standard_codes if code and code.strip()})
        if not codes:
            return []
        filters: list[Any] = [
            StandardApplicabilityRule.standard_code.in_(codes),
            StandardApplicabilityRule.review_status == StandardRuleReviewStatus.APPROVED,
        ]
        if as_of is not None:
            filters.extend(
                [
                    or_(
                        StandardApplicabilityRule.effective_from.is_(None),
                        StandardApplicabilityRule.effective_from <= as_of,
                    ),
                    or_(
                        StandardApplicabilityRule.effective_to.is_(None),
                        StandardApplicabilityRule.effective_to >= as_of,
                    ),
                ]
            )
        stmt = (
            select(StandardApplicabilityRule)
            .where(*filters)
            .order_by(
                StandardApplicabilityRule.priority.asc(),
                StandardApplicabilityRule.updated_at.desc(),
            )
        )
        return list(self.session.scalars(stmt).all())


class StandardPrecedenceRuleDAO(BaseRepository[StandardPrecedenceRule]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardPrecedenceRule)

    def create_rule(self, *, fields: dict[str, Any]) -> StandardPrecedenceRule:
        entity = StandardPrecedenceRule(**fields)
        self.session.add(entity)
        self.session.flush()
        return entity

    def list_page_filtered(
        self,
        *,
        page: int,
        page_size: int,
        standard_code: str | None = None,
        review_status: StandardRuleReviewStatus | None = None,
        approved_only: bool = True,
    ) -> tuple[list[StandardPrecedenceRule], int]:
        filters: list[Any] = []
        if standard_code:
            code = standard_code.strip()
            filters.append(
                or_(
                    StandardPrecedenceRule.higher_standard_code == code,
                    StandardPrecedenceRule.lower_standard_code == code,
                )
            )
        if review_status is not None:
            filters.append(StandardPrecedenceRule.review_status == review_status)
        elif approved_only:
            filters.append(StandardPrecedenceRule.review_status == StandardRuleReviewStatus.APPROVED)
        return self.list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[
                StandardPrecedenceRule.priority.asc(),
                StandardPrecedenceRule.updated_at.desc(),
            ],
            max_page_size=100,
        )

    def list_approved_for_standard_codes(
        self,
        *,
        standard_codes: Sequence[str],
    ) -> list[StandardPrecedenceRule]:
        codes = sorted({code.strip() for code in standard_codes if code and code.strip()})
        if not codes:
            return []
        stmt = (
            select(StandardPrecedenceRule)
            .where(
                StandardPrecedenceRule.review_status == StandardRuleReviewStatus.APPROVED,
                or_(
                    StandardPrecedenceRule.higher_standard_code.in_(codes),
                    StandardPrecedenceRule.lower_standard_code.in_(codes),
                ),
            )
            .order_by(
                StandardPrecedenceRule.priority.asc(),
                StandardPrecedenceRule.updated_at.desc(),
            )
        )
        return list(self.session.scalars(stmt).all())


class ComplianceEvidenceDAO(BaseRepository[ComplianceEvidence]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ComplianceEvidence)

    def clear_for_report(self, report_id: str) -> int:
        stmt = select(ComplianceEvidence).where(ComplianceEvidence.report_id == report_id)
        items = list(self.session.scalars(stmt).all())
        for item in items:
            self.session.delete(item)
        self.session.flush()
        return len(items)

    def add_many(self, items: list[ComplianceEvidence]) -> list[ComplianceEvidence]:
        self.session.add_all(items)
        self.session.flush()
        return items

    def list_page_filtered(
        self,
        *,
        page: int,
        page_size: int,
        visible_organization_id: str | None,
        report_id: str | None = None,
        result_id: str | None = None,
    ) -> tuple[list[ComplianceEvidence], int]:
        filters: list[Any] = []
        if visible_organization_id is not None:
            filters.append(DetectionReport.organization_id == visible_organization_id)
        if report_id:
            filters.append(ComplianceEvidence.report_id == report_id)
        if result_id:
            filters.append(ComplianceEvidence.result_id == result_id)

        params = normalize_page_params(page=page, page_size=page_size, max_page_size=100)
        list_stmt = (
            select(ComplianceEvidence)
            .join(DetectionReport, DetectionReport.id == ComplianceEvidence.report_id)
            .where(*filters)
            .order_by(ComplianceEvidence.created_at.asc(), ComplianceEvidence.id.asc())
        )
        count_stmt = (
            select(func.count())
            .select_from(ComplianceEvidence)
            .join(DetectionReport, DetectionReport.id == ComplianceEvidence.report_id)
            .where(*filters)
        )
        rows, total = fetch_scalar_rows_page(
            self.session,
            list_stmt=list_stmt,
            count_stmt=count_stmt,
            params=params,
        )
        return rows, total

    def touch_updated_at(self, item: ComplianceEvidence) -> None:
        item.updated_at = audit_now_naive()
