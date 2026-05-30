from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import EHSException
from app.dao.detection_dao import DetectionReportDAO
from app.dao.standard_graph_dao import (
    ComplianceEvidenceDAO,
    StandardApplicabilityRuleDAO,
    StandardClauseDAO,
    StandardPrecedenceRuleDAO,
    StandardRelationDAO,
)
from app.dao.standard_library_dao import StandardDocumentDAO
from app.models.base import audit_now_naive
from app.models.db_models import (
    ComplianceEvidence,
    ComplianceEvidenceType,
    ComplianceResult,
    DetectionMeasurement,
    DetectionReport,
    DetectionSample,
    RegulatoryLimit,
    StandardApplicabilityRule,
    StandardClause,
    StandardPrecedenceRule,
    StandardRelation,
    StandardRelationType,
    StandardRuleReviewStatus,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.pagination import Page
from app.schemas.standard_graph_schema import (
    ComplianceEvidenceOut,
    StandardApplicabilityRuleCreate,
    StandardApplicabilityRuleOut,
    StandardClauseCreate,
    StandardClauseOut,
    StandardPrecedenceRuleCreate,
    StandardPrecedenceRuleOut,
    StandardRelationCreate,
    StandardRelationOut,
)
from app.services.access_control import (
    ensure_admin,
    ensure_organization_scope,
    ensure_user_has_organization,
    is_system_admin,
)
from app.services.detection_limit_service import DetectionLimitService


@dataclass(slots=True)
class _LimitRuleRanking:
    limit: RegulatoryLimit
    applicability_rules: list[StandardApplicabilityRule]
    precedence_rules: list[StandardPrecedenceRule]
    original_index: int


class StandardGraphService:
    @staticmethod
    def select_applicable_limit(
        *,
        db: Session,
        report: DetectionReport,
        sample: DetectionSample,
        measurement: DetectionMeasurement,
        candidates: Sequence[RegulatoryLimit],
    ) -> RegulatoryLimit | None:
        if not candidates:
            return None
        rankings = _rank_limits(
            db=db,
            report=report,
            sample=sample,
            measurement=measurement,
            candidates=candidates,
        )
        return rankings[0].limit if rankings else candidates[0]

    @staticmethod
    def create_clause(
        *,
        db: Session,
        actor: CurrentUser,
        payload: StandardClauseCreate,
    ) -> StandardClauseOut:
        ensure_admin(actor)
        if payload.document_id and StandardDocumentDAO(db).get_by_id(payload.document_id) is None:
            raise EHSException(
                'Standard document not found',
                code='STANDARD_DOCUMENT_NOT_FOUND',
                status_code=404,
                details={'document_id': payload.document_id},
            )
        clause = StandardClauseDAO(db).create_clause(fields=_clause_fields(payload))
        db.commit()
        db.refresh(clause)
        return StandardClauseOut.model_validate(clause)

    @staticmethod
    def list_clauses(
        *,
        db: Session,
        actor: CurrentUser,
        page: int,
        page_size: int,
        query: str | None = None,
        standard_code: str | None = None,
        document_id: str | None = None,
        include_unapproved: bool = False,
    ) -> Page[StandardClauseOut]:
        visible_organization_id = None if is_system_admin(actor) else ensure_user_has_organization(actor)
        effective_include_unapproved = include_unapproved and is_system_admin(actor)
        items, total = StandardClauseDAO(db).list_page_filtered(
            page=page,
            page_size=page_size,
            visible_organization_id=visible_organization_id,
            include_unapproved=effective_include_unapproved,
            query=query,
            standard_code=standard_code,
            document_id=document_id,
        )
        return Page(
            items=[StandardClauseOut.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def create_relation(
        *,
        db: Session,
        actor: CurrentUser,
        payload: StandardRelationCreate,
    ) -> StandardRelationOut:
        ensure_admin(actor)
        relation = StandardRelationDAO(db).create_relation(fields=_relation_fields(payload, actor))
        db.commit()
        db.refresh(relation)
        return StandardRelationOut.model_validate(relation)

    @staticmethod
    def list_relations(
        *,
        db: Session,
        actor: CurrentUser,
        page: int,
        page_size: int,
        subject_id: str | None = None,
        object_id: str | None = None,
        relation_type: StandardRelationType | None = None,
    ) -> Page[StandardRelationOut]:
        _ = actor
        filters: list[Any] = []
        if subject_id:
            filters.append(StandardRelation.subject_id == subject_id.strip())
        if object_id:
            filters.append(StandardRelation.object_id == object_id.strip())
        if relation_type is not None:
            filters.append(StandardRelation.relation_type == relation_type)
        items, total = StandardRelationDAO(db).list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[StandardRelation.updated_at.desc()],
            max_page_size=100,
        )
        return Page(
            items=[StandardRelationOut.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def create_applicability_rule(
        *,
        db: Session,
        actor: CurrentUser,
        payload: StandardApplicabilityRuleCreate,
    ) -> StandardApplicabilityRuleOut:
        ensure_admin(actor)
        _ensure_clause_exists(db=db, clause_id=payload.clause_id)
        rule = StandardApplicabilityRuleDAO(db).create_rule(
            fields=_applicability_rule_fields(payload)
        )
        db.commit()
        db.refresh(rule)
        return StandardApplicabilityRuleOut.model_validate(rule)

    @staticmethod
    def list_applicability_rules(
        *,
        db: Session,
        actor: CurrentUser,
        page: int,
        page_size: int,
        standard_code: str | None = None,
        review_status: StandardRuleReviewStatus | None = None,
    ) -> Page[StandardApplicabilityRuleOut]:
        approved_only = not is_system_admin(actor)
        items, total = StandardApplicabilityRuleDAO(db).list_page_filtered(
            page=page,
            page_size=page_size,
            standard_code=standard_code,
            review_status=review_status if is_system_admin(actor) else None,
            approved_only=approved_only,
        )
        return Page(
            items=[StandardApplicabilityRuleOut.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def create_precedence_rule(
        *,
        db: Session,
        actor: CurrentUser,
        payload: StandardPrecedenceRuleCreate,
    ) -> StandardPrecedenceRuleOut:
        ensure_admin(actor)
        _ensure_clause_exists(db=db, clause_id=payload.source_clause_id)
        rule = StandardPrecedenceRuleDAO(db).create_rule(fields=_precedence_rule_fields(payload))
        db.commit()
        db.refresh(rule)
        return StandardPrecedenceRuleOut.model_validate(rule)

    @staticmethod
    def list_precedence_rules(
        *,
        db: Session,
        actor: CurrentUser,
        page: int,
        page_size: int,
        standard_code: str | None = None,
        review_status: StandardRuleReviewStatus | None = None,
    ) -> Page[StandardPrecedenceRuleOut]:
        approved_only = not is_system_admin(actor)
        items, total = StandardPrecedenceRuleDAO(db).list_page_filtered(
            page=page,
            page_size=page_size,
            standard_code=standard_code,
            review_status=review_status if is_system_admin(actor) else None,
            approved_only=approved_only,
        )
        return Page(
            items=[StandardPrecedenceRuleOut.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def list_evidence(
        *,
        db: Session,
        actor: CurrentUser,
        page: int,
        page_size: int,
        report_id: str | None = None,
        result_id: str | None = None,
    ) -> Page[ComplianceEvidenceOut]:
        if report_id:
            report = DetectionReportDAO(db).get_by_id(report_id)
            if report is None:
                raise EHSException(
                    'Detection report not found',
                    code='DETECTION_REPORT_NOT_FOUND',
                    status_code=404,
                )
            ensure_organization_scope(actor, report.organization_id)
        visible_organization_id = None if is_system_admin(actor) else ensure_user_has_organization(actor)
        items, total = ComplianceEvidenceDAO(db).list_page_filtered(
            page=page,
            page_size=page_size,
            visible_organization_id=visible_organization_id,
            report_id=report_id,
            result_id=result_id,
        )
        return Page(
            items=[ComplianceEvidenceOut.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def replace_evidence_for_results(
        *,
        db: Session,
        report: DetectionReport,
        results: list[ComplianceResult],
    ) -> list[ComplianceEvidence]:
        evidence_dao = ComplianceEvidenceDAO(db)
        evidence_dao.clear_for_report(report.id)
        items = [
            evidence
            for result in results
            for evidence in _result_evidence_items(db=db, result=result)
        ]
        if not items:
            db.commit()
            return []
        evidence_dao.add_many(items)
        db.commit()
        for item in items:
            db.refresh(item)
        return items


def _rank_limits(
    *,
    db: Session,
    report: DetectionReport,
    sample: DetectionSample,
    measurement: DetectionMeasurement,
    candidates: Sequence[RegulatoryLimit],
) -> list[_LimitRuleRanking]:
    standard_codes = [limit.standard_code for limit in candidates]
    applicability_rules = StandardApplicabilityRuleDAO(db).list_approved_for_standard_codes(
        standard_codes=standard_codes,
        as_of=report.report_date,
    )
    precedence_rules = StandardPrecedenceRuleDAO(db).list_approved_for_standard_codes(
        standard_codes=standard_codes,
    )
    candidate_codes = {limit.standard_code for limit in candidates}
    rankings = [
        _LimitRuleRanking(
            limit=limit,
            applicability_rules=[
                rule
                for rule in applicability_rules
                if _applicability_rule_matches(
                    rule=rule,
                    report=report,
                    sample=sample,
                    measurement=measurement,
                    limit=limit,
                )
            ],
            precedence_rules=[
                rule
                for rule in precedence_rules
                if _precedence_rule_matches(
                    rule=rule,
                    candidate_codes=candidate_codes,
                    report=report,
                    sample=sample,
                    measurement=measurement,
                    limit=limit,
                )
            ],
            original_index=index,
        )
        for index, limit in enumerate(candidates)
    ]
    if not any(item.applicability_rules or item.precedence_rules for item in rankings):
        return rankings
    return sorted(rankings, key=_limit_rule_sort_key)


def _limit_rule_sort_key(item: _LimitRuleRanking) -> tuple[int, int, int, int, int, int, int]:
    higher_priorities = [
        rule.priority
        for rule in item.precedence_rules
        if rule.higher_standard_code == item.limit.standard_code
    ]
    is_lower_precedence = any(
        rule.lower_standard_code == item.limit.standard_code for rule in item.precedence_rules
    )
    applicability_priorities = [rule.priority for rule in item.applicability_rules]
    return (
        0 if higher_priorities else 1,
        1 if is_lower_precedence else 0,
        min(higher_priorities, default=10_000),
        0 if applicability_priorities else 1,
        min(applicability_priorities, default=10_000),
        item.limit.priority,
        item.original_index,
    )


def _applicability_rule_matches(
    *,
    rule: StandardApplicabilityRule,
    report: DetectionReport,
    sample: DetectionSample,
    measurement: DetectionMeasurement,
    limit: RegulatoryLimit,
) -> bool:
    if rule.standard_code != limit.standard_code:
        return False
    if rule.report_type is not None and rule.report_type != report.report_type:
        return False
    if rule.medium is not None and rule.medium != sample.medium:
        return False
    if rule.indicator_name and not _any_text_matches(
        rule.indicator_name,
        measurement.indicator_name,
        limit.indicator_name,
    ):
        return False
    if rule.cas_no and not _any_text_matches(rule.cas_no, measurement.cas_no, limit.cas_no):
        return False
    if rule.industry or rule.region or rule.pollutant_category or rule.process_type:
        return False
    return _context_json_matches(
        _json_to_dict(rule.applicability_json),
        report=report,
        sample=sample,
        measurement=measurement,
        limit=limit,
    )


def _precedence_rule_matches(
    *,
    rule: StandardPrecedenceRule,
    candidate_codes: set[str],
    report: DetectionReport,
    sample: DetectionSample,
    measurement: DetectionMeasurement,
    limit: RegulatoryLimit,
) -> bool:
    if rule.higher_standard_code not in candidate_codes or rule.lower_standard_code not in candidate_codes:
        return False
    if limit.standard_code not in {rule.higher_standard_code, rule.lower_standard_code}:
        return False
    if rule.region or rule.industry:
        return False
    if rule.domain and not _any_text_matches(rule.domain, report.report_type.value):
        return False
    return _context_json_matches(
        _json_to_dict(rule.condition_json),
        report=report,
        sample=sample,
        measurement=measurement,
        limit=limit,
    )


def _context_json_matches(
    condition: dict[str, Any],
    *,
    report: DetectionReport,
    sample: DetectionSample,
    measurement: DetectionMeasurement,
    limit: RegulatoryLimit,
) -> bool:
    for key, expected in condition.items():
        if _is_empty_condition_value(expected):
            continue
        normalized_key = key.strip().lower()
        actual_values = _context_values(
            normalized_key,
            report=report,
            sample=sample,
            measurement=measurement,
            limit=limit,
        )
        if not actual_values or not _condition_value_matches(expected, actual_values):
            return False
    return True


def _context_values(
    key: str,
    *,
    report: DetectionReport,
    sample: DetectionSample,
    measurement: DetectionMeasurement,
    limit: RegulatoryLimit,
) -> tuple[str, ...]:
    values: tuple[Any, ...]
    if key == 'service_type':
        values = (report.service_type,)
    elif key == 'report_type':
        values = (report.report_type.value,)
    elif key == 'medium':
        values = (sample.medium.value,)
    elif key == 'standard_code':
        values = (limit.standard_code,)
    elif key == 'indicator_name':
        values = (measurement.indicator_name, limit.indicator_name)
    elif key == 'cas_no':
        values = (measurement.cas_no, limit.cas_no)
    elif key == 'limit_type':
        values = (limit.limit_type.value,)
    else:
        return ()
    return tuple(str(value).strip() for value in values if value is not None and str(value).strip())


def _condition_value_matches(expected: Any, actual_values: tuple[str, ...]) -> bool:
    if isinstance(expected, (list, tuple, set)):
        return any(_condition_value_matches(item, actual_values) for item in expected)
    expected_text = str(expected).strip().lower()
    if not expected_text:
        return True
    return any(expected_text == actual.lower() for actual in actual_values)


def _is_empty_condition_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _any_text_matches(expected: str, *actual_values: str | None) -> bool:
    expected_text = expected.strip().lower()
    return any(
        expected_text == actual.strip().lower()
        for actual in actual_values
        if actual is not None and actual.strip()
    )


def _clause_fields(payload: StandardClauseCreate) -> dict[str, Any]:
    return {
        'document_id': _strip_or_none(payload.document_id),
        'standard_code': payload.standard_code.strip(),
        'standard_name': payload.standard_name.strip(),
        'version': _strip_or_none(payload.version),
        'clause_code': payload.clause_code.strip(),
        'clause_title': _strip_or_none(payload.clause_title),
        'clause_type': payload.clause_type,
        'page_start': payload.page_start,
        'page_end': payload.page_end,
        'text_hash': _strip_or_none(payload.text_hash),
        'source_uri': _strip_or_none(payload.source_uri),
        'status': payload.status,
        'effective_from': payload.effective_from,
        'effective_to': payload.effective_to,
    }


def _relation_fields(payload: StandardRelationCreate, actor: CurrentUser) -> dict[str, Any]:
    verified = bool(payload.is_verified)
    return {
        'subject_type': payload.subject_type,
        'subject_id': payload.subject_id.strip(),
        'relation_type': payload.relation_type,
        'object_type': payload.object_type,
        'object_id': payload.object_id.strip(),
        'confidence': payload.confidence,
        'source_type': payload.source_type,
        'is_verified': 1 if verified else 0,
        'verified_by_id': actor.account_id if verified else None,
        'verified_at': audit_now_naive() if verified else None,
        'metadata_json': _json_or_none(payload.metadata),
    }


def _applicability_rule_fields(payload: StandardApplicabilityRuleCreate) -> dict[str, Any]:
    return {
        'standard_code': payload.standard_code.strip(),
        'clause_id': _strip_or_none(payload.clause_id),
        'report_type': payload.report_type,
        'medium': payload.medium,
        'industry': _strip_or_none(payload.industry),
        'region': _strip_or_none(payload.region),
        'pollutant_category': _strip_or_none(payload.pollutant_category),
        'indicator_name': _strip_or_none(payload.indicator_name),
        'cas_no': _strip_or_none(payload.cas_no),
        'process_type': _strip_or_none(payload.process_type),
        'applicability_json': _json_or_none(payload.applicability),
        'priority': payload.priority,
        'effective_from': payload.effective_from,
        'effective_to': payload.effective_to,
        'review_status': payload.review_status,
    }


def _precedence_rule_fields(payload: StandardPrecedenceRuleCreate) -> dict[str, Any]:
    return {
        'rule_name': payload.rule_name.strip(),
        'domain': _strip_or_none(payload.domain),
        'region': _strip_or_none(payload.region),
        'industry': _strip_or_none(payload.industry),
        'higher_standard_code': payload.higher_standard_code.strip(),
        'lower_standard_code': payload.lower_standard_code.strip(),
        'condition_json': _json_or_none(payload.condition),
        'priority': payload.priority,
        'reason': _strip_or_none(payload.reason),
        'source_clause_id': _strip_or_none(payload.source_clause_id),
        'review_status': payload.review_status,
    }


def _result_evidence_items(*, db: Session, result: ComplianceResult) -> list[ComplianceEvidence]:
    clause = _find_clause_for_result(db=db, result=result)
    source_id = clause.document.source_id if clause is not None and clause.document is not None else None
    source_uri = clause.source_uri if clause is not None else None
    common = {
        'report_id': result.report_id,
        'sample_id': result.sample_id,
        'measurement_id': result.measurement_id,
        'result_id': result.id,
        'standard_code': result.standard_code,
        'standard_name': result.standard_name,
        'clause_id': clause.id if clause is not None else None,
        'limit_id': result.limit_id,
        'source_id': source_id,
        'source_uri': source_uri,
    }
    items: list[ComplianceEvidence] = []
    if result.limit_id:
        ranking = _rule_ranking_for_result(db=db, result=result)
        items.append(
            ComplianceEvidence(
                **common,
                evidence_type=ComplianceEvidenceType.LIMIT_MATCH,
                evidence_summary=_limit_match_summary(result),
                metadata_json=_json_or_none(_result_metadata(result)),
            )
        )
        if ranking is not None:
            items.extend(_rule_evidence_items(common=common, ranking=ranking))
    items.append(
        ComplianceEvidence(
            **common,
            evidence_type=ComplianceEvidenceType.CALCULATION,
            evidence_summary=_calculation_summary(result),
            metadata_json=_json_or_none(_result_metadata(result)),
        )
    )
    return items


def _rule_ranking_for_result(
    *,
    db: Session,
    result: ComplianceResult,
) -> _LimitRuleRanking | None:
    if not result.limit_id or result.limit_type is None:
        return None
    report = db.get(DetectionReport, result.report_id)
    sample = db.get(DetectionSample, result.sample_id)
    measurement = db.get(DetectionMeasurement, result.measurement_id)
    if report is None or sample is None or measurement is None:
        return None
    candidates = DetectionLimitService.find_candidates(
        db=db,
        measurement=measurement,
        medium=sample.medium,
        as_of=report.report_date,
        limit_type=result.limit_type,
    )
    rankings = _rank_limits(
        db=db,
        report=report,
        sample=sample,
        measurement=measurement,
        candidates=candidates,
    )
    return next((item for item in rankings if item.limit.id == result.limit_id), None)


def _rule_evidence_items(
    *,
    common: dict[str, Any],
    ranking: _LimitRuleRanking,
) -> list[ComplianceEvidence]:
    items = [
        ComplianceEvidence(
            **common,
            evidence_type=ComplianceEvidenceType.APPLICABILITY,
            evidence_summary=_applicability_summary(rule),
            metadata_json=_json_or_none(_applicability_metadata(rule)),
        )
        for rule in ranking.applicability_rules
    ]
    items.extend(
        ComplianceEvidence(
            **common,
            evidence_type=ComplianceEvidenceType.PRECEDENCE,
            evidence_summary=_precedence_summary(rule),
            metadata_json=_json_or_none(_precedence_metadata(rule)),
        )
        for rule in ranking.precedence_rules
        if rule.higher_standard_code == ranking.limit.standard_code
    )
    return items


def _find_clause_for_result(*, db: Session, result: ComplianceResult) -> StandardClause | None:
    if not result.standard_code:
        return None
    return StandardClauseDAO(db).find_by_standard_clause(
        standard_code=result.standard_code,
        clause_code=result.clause,
    )


def _limit_match_summary(result: ComplianceResult) -> str:
    parts = [
        '命中结构化限值',
        result.standard_code,
        f'条款 {result.clause}' if result.clause else None,
        f'限值类型 {result.limit_type.value}' if result.limit_type else None,
    ]
    return '，'.join(part for part in parts if part)


def _calculation_summary(result: ComplianceResult) -> str:
    return f'判定结果 {result.status.value}：{result.message or "无附加说明"}'


def _applicability_summary(rule: StandardApplicabilityRule) -> str:
    parts = [
        '命中适用规则',
        rule.standard_code,
        f'priority={rule.priority}',
    ]
    return '，'.join(parts)


def _precedence_summary(rule: StandardPrecedenceRule) -> str:
    return (
        f'命中优先级规则：{rule.higher_standard_code} '
        f'优先于 {rule.lower_standard_code}，priority={rule.priority}'
    )


def _result_metadata(result: ComplianceResult) -> dict[str, Any]:
    return {
        'calculated_value': _decimal_str(result.calculated_value),
        'calculated_unit': result.calculated_unit,
        'limit_value': _decimal_str(result.limit_value),
        'limit_unit': result.limit_unit,
        'limit_type': result.limit_type.value if result.limit_type else None,
        'status': result.status.value,
        'exceedance_multiple': _decimal_str(result.exceedance_multiple),
    }


def _applicability_metadata(rule: StandardApplicabilityRule) -> dict[str, Any]:
    return {
        'rule_id': rule.id,
        'standard_code': rule.standard_code,
        'clause_id': rule.clause_id,
        'report_type': rule.report_type.value if rule.report_type else None,
        'medium': rule.medium.value if rule.medium else None,
        'indicator_name': rule.indicator_name,
        'cas_no': rule.cas_no,
        'priority': rule.priority,
        'applicability': _json_to_dict(rule.applicability_json),
    }


def _precedence_metadata(rule: StandardPrecedenceRule) -> dict[str, Any]:
    return {
        'rule_id': rule.id,
        'rule_name': rule.rule_name,
        'higher_standard_code': rule.higher_standard_code,
        'lower_standard_code': rule.lower_standard_code,
        'priority': rule.priority,
        'reason': rule.reason,
        'condition': _json_to_dict(rule.condition_json),
    }


def _ensure_clause_exists(*, db: Session, clause_id: str | None) -> None:
    if clause_id and StandardClauseDAO(db).get_by_id(clause_id) is None:
        raise EHSException(
            'Standard clause not found',
            code='STANDARD_CLAUSE_NOT_FOUND',
            status_code=404,
            details={'clause_id': clause_id},
        )


def _json_or_none(value: dict[str, Any]) -> str | None:
    payload = {key: item for key, item in value.items() if item is not None}
    if not payload:
        return None
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _json_to_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, 'f')


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
