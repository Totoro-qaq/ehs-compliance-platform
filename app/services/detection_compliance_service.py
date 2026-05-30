from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.core.patterns import is_uuid
from app.dao.detection_dao import (
    ComplianceResultDAO,
    DetectionMeasurementDAO,
    DetectionReportDAO,
    DetectionSampleDAO,
    RegulatoryLimitDAO,
    deserialize_aliases,
    serialize_aliases,
)
from app.dao.organization_dao import OrganizationDAO
from app.models.base import audit_now_naive
from app.models.db_models import (
    AccountRole,
    ComplianceResult,
    ComplianceStatus,
    DetectionMeasurement,
    DetectionReport,
    DetectionSample,
    LimitType,
    RegulatoryLimit,
    ReportStatus,
    ReportType,
    SampleMedium,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.detection_schema import (
    ComplianceRunResponse,
    DetectionReportCreateResponse,
    DetectionReportDetail,
    DetectionReportSummary,
    RegulatoryLimitCreate,
    RegulatoryLimitResponse,
    RegulatoryLimitUpdate,
)
from app.schemas.pagination import Page
from app.services.access_control import (
    ensure_admin,
    ensure_client_org_id_allowed,
    ensure_organization_scope,
    ensure_user_has_organization,
)
from app.services.detection_calculation_service import (
    TWASegment,
    UnitConversionError,
    calc_noise_leq_8h,
    calc_pc_twa_8h,
    calc_stel_15min,
    convert_value,
    normalize_unit,
)
from app.services.detection_import_service import DetectionImportService
from app.services.detection_limit_service import DetectionLimitService
from app.services.detection_service_types import clean_detection_service_type
from app.services.standard_graph_service import StandardGraphService

_ALLOWED_UPLOAD_EXTENSIONS = frozenset({'.csv', '.xlsx', '.xlsm'})
_BORDERLINE_RATIO = Decimal('0.9')
_EXCEEDANCE_QUANT = Decimal('0.0001')


def _report_type_default_medium(report_type: ReportType) -> SampleMedium:
    if report_type == ReportType.OCCUPATIONAL_HEALTH:
        return SampleMedium.WORKPLACE_AIR
    if report_type == ReportType.WASTEWATER:
        return SampleMedium.WASTEWATER
    if report_type == ReportType.EXHAUST_GAS:
        return SampleMedium.EXHAUST_GAS
    if report_type == ReportType.NOISE:
        return SampleMedium.NOISE
    if report_type == ReportType.HIGH_TEMPERATURE:
        return SampleMedium.HIGH_TEMPERATURE
    return SampleMedium.WORKPLACE_AIR


def _parse_report_type(raw: str | ReportType) -> ReportType:
    if isinstance(raw, ReportType):
        return raw
    try:
        return ReportType(raw)
    except ValueError as exc:
        raise EHSException(
            'Invalid detection report_type',
            code='DETECTION_INVALID_REPORT_TYPE',
            status_code=400,
            details={'allowed': [item.value for item in ReportType]},
        ) from exc


def _parse_report_status(raw: str | None) -> ReportStatus | None:
    if raw is None:
        return None
    try:
        return ReportStatus(raw)
    except ValueError as exc:
        raise EHSException(
            'Invalid detection report status',
            code='DETECTION_INVALID_STATUS',
            status_code=400,
            details={'allowed': [item.value for item in ReportStatus]},
        ) from exc


def _parse_medium(raw: str | None) -> SampleMedium | None:
    if raw is None:
        return None
    try:
        return SampleMedium(raw)
    except ValueError as exc:
        raise EHSException(
            'Invalid sample medium',
            code='DETECTION_INVALID_MEDIUM',
            status_code=400,
            details={'allowed': [item.value for item in SampleMedium]},
        ) from exc


def _clean_display_name(value: str | None) -> str | None:
    cleaned = (value or '').strip()
    return cleaned[:255] if cleaned else None


def _report_type_label(report_type: ReportType) -> str:
    return {
        ReportType.OCCUPATIONAL_HEALTH: '职业卫生',
        ReportType.WASTEWATER: '废水',
        ReportType.EXHAUST_GAS: '废气',
        ReportType.NOISE: '噪声',
        ReportType.HIGH_TEMPERATURE: '高温WBGT',
    }.get(report_type, report_type.value)


def _default_report_name(
    organization_name: str | None,
    report_type: ReportType,
    service_type: str | None = None,
) -> str:
    org_name = (organization_name or '默认公司').strip() or '默认公司'
    business_type = service_type or f'{_report_type_label(report_type)}检测'
    return f'{org_name} {business_type}报告 {date.today().isoformat()}'[:255]


def _validate_filename(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise EHSException(
            'Upload filename is required',
            code='DETECTION_INVALID_UPLOAD_FILENAME',
            status_code=400,
        )
    name = Path(filename).name
    if name != filename or '..' in filename or '/' in filename or '\\' in filename:
        raise EHSException(
            'Upload filename is invalid',
            code='DETECTION_INVALID_UPLOAD_FILENAME',
            status_code=400,
        )
    suffix = Path(name).suffix.lower()
    if suffix not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise EHSException(
            'Unsupported detection upload file type',
            code='DETECTION_UNSUPPORTED_FORMAT',
            status_code=400,
            details={'allowed': sorted(_ALLOWED_UPLOAD_EXTENSIONS)},
        )
    return name


def _store_upload(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    stem = Path(filename).stem or 'file'
    safe_stem = re.sub(r'[^\w.-]', '_', stem).strip('._') or 'file'
    safe_stem = safe_stem[:120]
    today = date.today()
    day_dir = (
        Path(settings.upload_dir)
        / 'detection'
        / str(today.year)
        / f'{today.month:02d}'
        / f'{today.day:02d}'
    )
    day_dir.mkdir(parents=True, exist_ok=True)
    target = day_dir / f'{uuid.uuid4().hex}_{safe_stem}{suffix}'
    target.write_bytes(content)
    return str(target)


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _json_decimal(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None


def _first_decimal(*values: Decimal | None) -> Decimal | None:
    for value in values:
        if value is not None:
            return value
    return None


def _source_limit_type(measurement: DetectionMeasurement) -> LimitType:
    return measurement.source_limit_type or LimitType.INSTANT


def _source_limit_from_measurement(
    *,
    measurement: DetectionMeasurement,
    sample: DetectionSample,
    unit: str | None,
) -> RegulatoryLimit:
    limit_type = _source_limit_type(measurement)
    limit_kwargs: dict[str, Decimal | None] = {}
    if limit_type == LimitType.RANGE:
        limit_kwargs['limit_min'] = measurement.source_limit_value
    else:
        limit_kwargs['limit_value'] = measurement.source_limit_value
    return RegulatoryLimit(
        indicator_name=measurement.indicator_name,
        cas_no=measurement.cas_no,
        medium=sample.medium,
        limit_type=limit_type,
        unit=measurement.source_limit_unit or unit or '',
        standard_code='REPORT_SOURCE_LIMIT',
        standard_name='检测报告内限值',
        clause='source table',
        priority=10_000,
        **limit_kwargs,
    )


def _limit_response(limit: RegulatoryLimit) -> RegulatoryLimitResponse:
    return RegulatoryLimitResponse(
        id=limit.id,
        indicator_name=limit.indicator_name,
        cas_no=limit.cas_no,
        aliases=deserialize_aliases(limit.aliases_json),
        medium=limit.medium,
        limit_type=limit.limit_type,
        limit_value=limit.limit_value,
        limit_min=limit.limit_min,
        limit_max=limit.limit_max,
        unit=limit.unit,
        standard_code=limit.standard_code,
        standard_name=limit.standard_name,
        clause=limit.clause,
        basis_text=limit.basis_text,
        effective_from=limit.effective_from,
        effective_to=limit.effective_to,
        applicability=_json_dict(limit.applicability_json),
        priority=limit.priority,
        created_at=limit.created_at,
        updated_at=limit.updated_at,
    )


class DetectionComplianceService:
    @staticmethod
    def create_report_from_upload(
        *,
        db: Session,
        actor: CurrentUser,
        organization_id: str,
        report_type: str | ReportType,
        filename: str | None,
        content: bytes,
        report_name: str | None = None,
        client_name: str | None = None,
        project_name: str | None = None,
        project_code: str | None = None,
        service_type: str | None = None,
    ) -> DetectionReportCreateResponse:
        ensure_client_org_id_allowed(actor, requested_organization_id=organization_id)
        if not is_uuid(organization_id):
            raise EHSException(
                'organization_id must be a valid UUID',
                code='INVALID_ORGANIZATION_ID',
                status_code=400,
            )
        organization = OrganizationDAO(db).get_by_id(organization_id)
        if organization is None:
            raise EHSException('Organization not found', code='ORG_NOT_FOUND', status_code=404)
        if len(content) > settings.max_upload_bytes:
            raise EHSException(
                'Upload file is too large',
                code='FILE_TOO_LARGE',
                status_code=413,
                details={'max_upload_bytes': settings.max_upload_bytes},
            )

        parsed_type = _parse_report_type(report_type)
        cleaned_service_type = clean_detection_service_type(service_type)
        business_name = _clean_display_name(report_name) or _default_report_name(
            organization.name,
            parsed_type,
            cleaned_service_type,
        )
        display_name = _validate_filename(filename)
        file_path = _store_upload(display_name, content)

        report_dao = DetectionReportDAO(db)
        report = report_dao.create_report(
            organization_id=organization_id,
            filename=display_name,
            report_name=business_name,
            client_name=_clean_display_name(client_name),
            project_name=_clean_display_name(project_name),
            project_code=_clean_display_name(project_code)[:64] if _clean_display_name(project_code) else None,
            service_type=cleaned_service_type,
            report_type=parsed_type,
            file_path=file_path,
            created_by_id=actor.account_id,
        )

        try:
            parsed = DetectionImportService.parse(
                content=content,
                filename=display_name,
                report_id=report.id,
                default_medium=_report_type_default_medium(parsed_type),
            )
            if parsed.errors:
                raise EHSException(
                    'Detection upload contains invalid rows',
                    code='DETECTION_IMPORT_ROW_ERRORS',
                    status_code=400,
                    details={
                        'errors': [
                            {
                                'row_index': err.row_index,
                                'column': err.column,
                                'message': err.message,
                            }
                            for err in parsed.errors
                        ]
                    },
                )
            if parsed.samples:
                db.add_all(parsed.samples)
                db.commit()
            report = report_dao.update_status(
                report_id=report.id,
                status=ReportStatus.PARSED,
            ) or report
            return DetectionReportCreateResponse(
                report_id=report.id,
                report_name=report.report_name,
                client_name=report.client_name,
                project_name=report.project_name,
                project_code=report.project_code,
                service_type=report.service_type,
                status=report.status,
                report_type=report.report_type,
                sample_count=len(parsed.samples),
                measurement_count=len(parsed.measurements),
                warnings=parsed.warnings,
            )
        except EHSException as exc:
            db.rollback()
            report_dao.update_status(
                report_id=report.id,
                status=ReportStatus.FAILED,
                error_message=exc.message,
            )
            raise
        except Exception as exc:
            db.rollback()
            report_dao.update_status(
                report_id=report.id,
                status=ReportStatus.FAILED,
                error_message=str(exc),
            )
            raise

    @staticmethod
    def list_reports(
        *,
        db: Session,
        actor: CurrentUser,
        organization_id: str | None,
        report_type: str | None,
        status: str | None,
        client_name: str | None = None,
        project_name: str | None = None,
        project_code: str | None = None,
        service_type: str | None = None,
        page: int,
        page_size: int,
    ) -> Page[DetectionReportSummary]:
        if organization_id and not is_uuid(organization_id):
            raise EHSException(
                'organization_id must be a valid UUID',
                code='INVALID_ORGANIZATION_ID',
                status_code=400,
            )
        if actor.role == AccountRole.ADMIN:
            oid = organization_id
        else:
            uid_org = ensure_user_has_organization(actor)
            if organization_id and organization_id != uid_org:
                raise EHSException(
                    'Forbidden to query reports from another organization',
                    code='IDOR_ORG_FORGE',
                    status_code=403,
                )
            oid = uid_org

        parsed_type = _parse_report_type(report_type) if report_type else None
        parsed_status = _parse_report_status(status)
        items, total = DetectionReportDAO(db).list_for_org(
            organization_id=oid,
            report_type=parsed_type,
            status=parsed_status,
            client_name=(client_name or '').strip() or None,
            project_name=(project_name or '').strip() or None,
            project_code=(project_code or '').strip() or None,
            service_type=(service_type or '').strip() or None,
            page=page,
            page_size=page_size,
        )
        return Page[DetectionReportSummary](
            items=[DetectionReportSummary.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def get_report_detail(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
    ) -> DetectionReportDetail:
        report = DetectionComplianceService._get_scoped_report(
            db=db,
            actor=actor,
            report_id=report_id,
        )
        return DetectionReportDetail.model_validate(report)

    @staticmethod
    def list_results(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
    ) -> list[ComplianceResult]:
        DetectionComplianceService._get_scoped_report(db=db, actor=actor, report_id=report_id)
        return ComplianceResultDAO(db).list_by_report(report_id)

    @staticmethod
    def run_report_compliance(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
    ) -> ComplianceRunResponse:
        report = DetectionComplianceService._get_scoped_report(
            db=db,
            actor=actor,
            report_id=report_id,
        )
        samples = DetectionSampleDAO(db).list_by_report(report.id)
        measurement_dao = DetectionMeasurementDAO(db)
        results: list[ComplianceResult] = []

        for sample in samples:
            for measurement in measurement_dao.list_by_sample(sample.id):
                results.append(
                    DetectionComplianceService._build_result(
                        db=db,
                        report=report,
                        sample=sample,
                        measurement=measurement,
                    )
                )

        saved_results = ComplianceResultDAO(db).replace_for_report(
            report_id=report.id,
            results=results,
        )
        StandardGraphService.replace_evidence_for_results(
            db=db,
            report=report,
            results=saved_results,
        )
        DetectionReportDAO(db).update_status(
            report_id=report.id,
            status=ReportStatus.CALCULATED,
        )
        return DetectionComplianceService._run_response(
            report_id=report.id,
            status=ReportStatus.CALCULATED,
            results=saved_results,
        )

    @staticmethod
    def list_limits(
        *,
        db: Session,
        actor: CurrentUser,
        indicator_name: str | None,
        medium: str | None,
        standard_code: str | None,
        page: int,
        page_size: int,
    ) -> Page[RegulatoryLimitResponse]:
        _ = actor
        items, total = RegulatoryLimitDAO(db).list_filtered(
            indicator_name=indicator_name,
            medium=_parse_medium(medium),
            standard_code=standard_code,
            page=page,
            page_size=page_size,
        )
        return Page[RegulatoryLimitResponse](
            items=[_limit_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def create_limit(
        *,
        db: Session,
        actor: CurrentUser,
        payload: RegulatoryLimitCreate,
    ) -> RegulatoryLimitResponse:
        ensure_admin(actor)
        DetectionComplianceService._validate_limit_payload(payload)
        limit = RegulatoryLimit(
            indicator_name=payload.indicator_name.strip(),
            cas_no=payload.cas_no.strip() if payload.cas_no else None,
            aliases_json=serialize_aliases(payload.aliases),
            medium=payload.medium,
            limit_type=payload.limit_type,
            limit_value=payload.limit_value,
            limit_min=payload.limit_min,
            limit_max=payload.limit_max,
            unit=normalize_unit(payload.unit) or payload.unit,
            standard_code=payload.standard_code.strip(),
            standard_name=payload.standard_name.strip(),
            clause=payload.clause.strip() if payload.clause else None,
            basis_text=payload.basis_text,
            effective_from=payload.effective_from,
            effective_to=payload.effective_to,
            applicability_json=json.dumps(payload.applicability, ensure_ascii=False)
            if payload.applicability
            else None,
            priority=payload.priority,
        )
        return _limit_response(RegulatoryLimitDAO(db).save_and_refresh(limit))

    @staticmethod
    def update_limit(
        *,
        db: Session,
        actor: CurrentUser,
        limit_id: str,
        payload: RegulatoryLimitUpdate,
    ) -> RegulatoryLimitResponse:
        ensure_admin(actor)
        fields = payload.model_dump(exclude_unset=True)
        update_fields: dict[str, Any] = {}
        for key, value in fields.items():
            if key == 'aliases':
                update_fields['aliases_json'] = serialize_aliases(value or [])
            elif key == 'applicability':
                update_fields['applicability_json'] = (
                    json.dumps(value, ensure_ascii=False) if value else None
                )
            elif key == 'unit' and value is not None:
                update_fields[key] = normalize_unit(value) or value
            elif isinstance(value, str):
                update_fields[key] = value.strip()
            else:
                update_fields[key] = value
        if update_fields:
            update_fields['updated_at'] = audit_now_naive()
        limit = RegulatoryLimitDAO(db).get_by_id(limit_id)
        if limit is None:
            raise EHSException('Regulatory limit not found', code='LIMIT_NOT_FOUND', status_code=404)
        for key, value in update_fields.items():
            setattr(limit, key, value)
        DetectionComplianceService._validate_limit_entity(limit)
        db.commit()
        db.refresh(limit)
        return _limit_response(limit)

    @staticmethod
    def delete_limit(*, db: Session, actor: CurrentUser, limit_id: str) -> None:
        ensure_admin(actor)
        if not RegulatoryLimitDAO(db).soft_delete_by_id(limit_id):
            raise EHSException('Regulatory limit not found', code='LIMIT_NOT_FOUND', status_code=404)

    @staticmethod
    def _get_scoped_report(*, db: Session, actor: CurrentUser, report_id: str) -> DetectionReport:
        report = DetectionReportDAO(db).get_by_id(report_id)
        if report is None:
            raise EHSException(
                'Detection report not found',
                code='DETECTION_REPORT_NOT_FOUND',
                status_code=404,
            )
        ensure_organization_scope(actor, report.organization_id)
        return report

    @staticmethod
    def _build_result(
        *,
        db: Session,
        report: DetectionReport,
        sample: DetectionSample,
        measurement: DetectionMeasurement,
    ) -> ComplianceResult:
        limit = DetectionComplianceService._match_limit(
            db=db,
            report=report,
            sample=sample,
            measurement=measurement,
        )
        if limit is None:
            if measurement.source_limit_value is not None:
                source_limit = _source_limit_from_measurement(
                    measurement=measurement,
                    sample=sample,
                    unit=measurement.normalized_unit or normalize_unit(measurement.raw_unit),
                )
                value, unit, status, message = DetectionComplianceService._calculated_value(
                    sample=sample,
                    measurement=measurement,
                    limit=source_limit,
                )
                if status is not None:
                    return DetectionComplianceService._result_entity(
                        report=report,
                        sample=sample,
                        measurement=measurement,
                        limit=None,
                        calculated_value=value,
                        calculated_unit=unit,
                        status=status,
                        message=message or 'Report source limit comparison needs review.',
                        limit_value=measurement.source_limit_value,
                        limit_unit=source_limit.unit,
                        limit_type=source_limit.limit_type,
                        standard_code=source_limit.standard_code,
                        standard_name=source_limit.standard_name,
                        clause=source_limit.clause,
                    )
                status, exceedance, limit_value, message = DetectionComplianceService._evaluate(
                    value=value,
                    limit=source_limit,
                )
                return DetectionComplianceService._result_entity(
                    report=report,
                    sample=sample,
                    measurement=measurement,
                    limit=None,
                    calculated_value=value,
                    calculated_unit=unit,
                    status=status,
                    message=f'{message} Source: detection report table limit.',
                    limit_value=limit_value,
                    exceedance_multiple=exceedance,
                    limit_unit=source_limit.unit,
                    limit_type=source_limit.limit_type,
                    standard_code=source_limit.standard_code,
                    standard_name=source_limit.standard_name,
                    clause=source_limit.clause,
                )
            return DetectionComplianceService._result_entity(
                report=report,
                sample=sample,
                measurement=measurement,
                limit=None,
                calculated_value=_first_decimal(
                    measurement.normalized_value,
                    measurement.raw_value,
                ),
                calculated_unit=measurement.normalized_unit or normalize_unit(measurement.raw_unit),
                status=ComplianceStatus.INSUFFICIENT_DATA,
                message='No applicable regulatory limit was found.',
            )

        value, unit, status, message = DetectionComplianceService._calculated_value(
            sample=sample,
            measurement=measurement,
            limit=limit,
        )
        if status is not None:
            return DetectionComplianceService._result_entity(
                report=report,
                sample=sample,
                measurement=measurement,
                limit=limit,
                calculated_value=value,
                calculated_unit=unit,
                status=status,
                message=message,
            )

        status, exceedance, limit_value, message = DetectionComplianceService._evaluate(
            value=value,
            limit=limit,
        )
        return DetectionComplianceService._result_entity(
            report=report,
            sample=sample,
            measurement=measurement,
            limit=limit,
            calculated_value=value,
            calculated_unit=unit,
            limit_value=limit_value,
            status=status,
            exceedance_multiple=exceedance,
            message=message,
        )

    @staticmethod
    def _match_limit(
        *,
        db: Session,
        report: DetectionReport,
        sample: DetectionSample,
        measurement: DetectionMeasurement,
    ) -> RegulatoryLimit | None:
        preferred = DetectionComplianceService._preferred_limit_type(
            report=report,
            sample=sample,
            measurement=measurement,
        )
        if preferred is not None:
            candidates = DetectionLimitService.find_candidates(
                db=db,
                measurement=measurement,
                medium=sample.medium,
                as_of=report.report_date,
                limit_type=preferred,
            )
            limit = StandardGraphService.select_applicable_limit(
                db=db,
                report=report,
                sample=sample,
                measurement=measurement,
                candidates=candidates,
            )
            if limit is not None:
                return limit
        candidates = DetectionLimitService.find_candidates(
            db=db,
            measurement=measurement,
            medium=sample.medium,
            as_of=report.report_date,
        )
        return StandardGraphService.select_applicable_limit(
            db=db,
            report=report,
            sample=sample,
            measurement=measurement,
            candidates=candidates,
        )

    @staticmethod
    def _preferred_limit_type(
        *,
        report: DetectionReport,
        sample: DetectionSample,
        measurement: DetectionMeasurement,
    ) -> LimitType | None:
        if measurement.source_limit_type is not None:
            if sample.medium == SampleMedium.WORKPLACE_AIR and measurement.source_limit_type in {
                LimitType.PC_TWA,
                LimitType.PC_STEL,
                LimitType.MAC,
            }:
                return measurement.source_limit_type
            if sample.medium in {
                SampleMedium.NOISE,
                SampleMedium.HIGH_TEMPERATURE,
                SampleMedium.PHYSICAL_FACTOR,
            } and measurement.source_limit_type in {LimitType.INSTANT, LimitType.RANGE}:
                return measurement.source_limit_type
        if (
            sample.medium in {SampleMedium.NOISE, SampleMedium.HIGH_TEMPERATURE}
            or report.report_type in {ReportType.NOISE, ReportType.HIGH_TEMPERATURE}
        ):
            return LimitType.INSTANT
        if sample.medium == SampleMedium.PHYSICAL_FACTOR:
            if measurement.indicator_name == '照度':
                return LimitType.RANGE
            return LimitType.INSTANT
        if sample.medium == SampleMedium.WORKPLACE_AIR:
            if sample.duration_minutes is not None and sample.duration_minutes <= Decimal('15'):
                return LimitType.PC_STEL
            return LimitType.PC_TWA
        return None

    @staticmethod
    def _calculated_value(
        *,
        sample: DetectionSample,
        measurement: DetectionMeasurement,
        limit: RegulatoryLimit,
    ) -> tuple[Decimal | None, str | None, ComplianceStatus | None, str | None]:
        value = _first_decimal(
            measurement.normalized_value,
            measurement.raw_value,
            measurement.detect_limit,
        )
        unit = measurement.normalized_unit or normalize_unit(measurement.raw_unit)
        if value is None:
            return None, unit, ComplianceStatus.INSUFFICIENT_DATA, 'Measurement value is missing.'
        if not unit:
            return value, None, ComplianceStatus.NEEDS_REVIEW, 'Measurement unit is missing.'

        try:
            value, unit = DetectionComplianceService._convert_to_limit_unit(
                value=value,
                unit=unit,
                limit=limit,
            )
        except UnitConversionError as exc:
            return value, unit, ComplianceStatus.NEEDS_REVIEW, str(exc)

        if limit.limit_type == LimitType.PC_TWA and sample.duration_minutes is not None:
            value = calc_pc_twa_8h(
                [TWASegment(concentration=value, minutes=sample.duration_minutes)]
            )
        elif limit.limit_type == LimitType.PC_STEL:
            if sample.duration_minutes is not None:
                if sample.duration_minutes < Decimal('15'):
                    return (
                        value,
                        unit,
                        ComplianceStatus.INSUFFICIENT_DATA,
                        'PC-STEL requires at least 15 minutes of sampling duration.',
                    )
                value = calc_stel_15min(
                    [TWASegment(concentration=value, minutes=sample.duration_minutes)]
                )
        elif limit.medium == SampleMedium.NOISE and unit == 'dB(A)':
            exposure_hours = sample.shift_hours
            if exposure_hours is None and sample.duration_minutes is not None:
                exposure_hours = sample.duration_minutes / Decimal('60')
            if exposure_hours is not None:
                value = calc_noise_leq_8h(value, exposure_hours)

        return value, unit, None, None

    @staticmethod
    def _convert_to_limit_unit(
        *,
        value: Decimal,
        unit: str,
        limit: RegulatoryLimit,
    ) -> tuple[Decimal, str]:
        target_unit = normalize_unit(limit.unit) or limit.unit
        current_unit = normalize_unit(unit) or unit
        if current_unit == target_unit:
            return value, target_unit
        applicability = _json_dict(limit.applicability_json)
        molecular_weight = _json_decimal(applicability.get('molecular_weight'))
        converted = convert_value(
            value,
            current_unit,
            target_unit,
            molecular_weight=molecular_weight,
        )
        return converted.value, converted.unit

    @staticmethod
    def _evaluate(
        *,
        value: Decimal | None,
        limit: RegulatoryLimit,
    ) -> tuple[ComplianceStatus, Decimal | None, Decimal | None, str]:
        if value is None:
            return ComplianceStatus.INSUFFICIENT_DATA, None, None, 'Calculated value is missing.'

        if limit.limit_type == LimitType.RANGE:
            return DetectionComplianceService._evaluate_range(value=value, limit=limit)

        if limit.limit_value is None:
            return (
                ComplianceStatus.NEEDS_REVIEW,
                None,
                None,
                'Scalar regulatory limit value is missing.',
            )
        if value > limit.limit_value:
            exceedance = DetectionComplianceService._exceedance(value, limit.limit_value)
            return (
                ComplianceStatus.EXCEEDED,
                exceedance,
                limit.limit_value,
                'Calculated value exceeds regulatory limit.',
            )
        if limit.limit_value > 0 and value >= limit.limit_value * _BORDERLINE_RATIO:
            return (
                ComplianceStatus.BORDERLINE,
                None,
                limit.limit_value,
                'Calculated value is close to regulatory limit.',
            )
        return ComplianceStatus.COMPLIANT, None, limit.limit_value, 'Calculated value is compliant.'

    @staticmethod
    def _evaluate_range(
        *,
        value: Decimal,
        limit: RegulatoryLimit,
    ) -> tuple[ComplianceStatus, Decimal | None, Decimal | None, str]:
        if limit.limit_min is None and limit.limit_max is None:
            return (
                ComplianceStatus.NEEDS_REVIEW,
                None,
                None,
                'Range regulatory limit is missing both lower and upper bounds.',
            )
        if limit.limit_min is not None and value < limit.limit_min:
            return (
                ComplianceStatus.EXCEEDED,
                None,
                limit.limit_min,
                'Calculated value is below regulatory range.',
            )
        if limit.limit_max is not None and value > limit.limit_max:
            return (
                ComplianceStatus.EXCEEDED,
                None,
                limit.limit_max,
                'Calculated value is above regulatory range.',
            )
        return ComplianceStatus.COMPLIANT, None, None, 'Calculated value is within regulatory range.'

    @staticmethod
    def _exceedance(value: Decimal, limit_value: Decimal) -> Decimal | None:
        if limit_value <= 0:
            return None
        return ((value - limit_value) / limit_value).quantize(_EXCEEDANCE_QUANT)

    @staticmethod
    def _result_entity(
        *,
        report: DetectionReport,
        sample: DetectionSample,
        measurement: DetectionMeasurement,
        limit: RegulatoryLimit | None,
        calculated_value: Decimal | None,
        calculated_unit: str | None,
        status: ComplianceStatus,
        message: str,
        limit_value: Decimal | None = None,
        exceedance_multiple: Decimal | None = None,
        limit_unit: str | None = None,
        limit_type: LimitType | None = None,
        standard_code: str | None = None,
        standard_name: str | None = None,
        clause: str | None = None,
    ) -> ComplianceResult:
        if limit is not None and limit_value is None and limit.limit_type != LimitType.RANGE:
            limit_value = limit.limit_value
        return ComplianceResult(
            report_id=report.id,
            sample_id=sample.id,
            measurement_id=measurement.id,
            limit_id=limit.id if limit is not None else None,
            calculated_value=calculated_value,
            calculated_unit=calculated_unit,
            limit_value=limit_value,
            limit_unit=limit.unit if limit is not None else limit_unit,
            limit_type=limit.limit_type if limit is not None else limit_type,
            status=status,
            exceedance_multiple=exceedance_multiple,
            standard_code=limit.standard_code if limit is not None else standard_code,
            standard_name=limit.standard_name if limit is not None else standard_name,
            clause=limit.clause if limit is not None else clause,
            message=message,
        )

    @staticmethod
    def _run_response(
        *,
        report_id: str,
        status: ReportStatus,
        results: list[ComplianceResult],
    ) -> ComplianceRunResponse:
        counts = Counter(item.status for item in results)
        return ComplianceRunResponse(
            report_id=report_id,
            status=status,
            total=len(results),
            compliant=counts[ComplianceStatus.COMPLIANT],
            exceeded=counts[ComplianceStatus.EXCEEDED],
            borderline=counts[ComplianceStatus.BORDERLINE],
            insufficient=counts[ComplianceStatus.INSUFFICIENT_DATA],
            needs_review=counts[ComplianceStatus.NEEDS_REVIEW],
            results=results,
        )

    @staticmethod
    def _validate_limit_payload(payload: RegulatoryLimitCreate) -> None:
        if payload.limit_type == LimitType.RANGE:
            if payload.limit_min is None and payload.limit_max is None:
                raise EHSException(
                    'Range limit requires limit_min or limit_max',
                    code='LIMIT_RANGE_BOUNDS_REQUIRED',
                    status_code=400,
                )
            return
        if payload.limit_value is None:
            raise EHSException(
                'Scalar limit requires limit_value',
                code='LIMIT_VALUE_REQUIRED',
                status_code=400,
            )

    @staticmethod
    def _validate_limit_entity(limit: RegulatoryLimit) -> None:
        if limit.limit_type == LimitType.RANGE:
            if limit.limit_min is None and limit.limit_max is None:
                raise EHSException(
                    'Range limit requires limit_min or limit_max',
                    code='LIMIT_RANGE_BOUNDS_REQUIRED',
                    status_code=400,
                )
        elif limit.limit_value is None:
            raise EHSException(
                'Scalar limit requires limit_value',
                code='LIMIT_VALUE_REQUIRED',
                status_code=400,
            )
