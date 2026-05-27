"""检测报告合规模块的 DAO。

按 roadmap 的 Fat DAO 约定，把所有复杂查询、聚合、状态更新都封装在这里；
Service 层不直接拼写 SQLAlchemy 语句。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date

from sqlalchemy import and_, case, or_, select
from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import (
    ComplianceResult,
    DetectionMeasurement,
    DetectionReport,
    DetectionSample,
    LimitType,
    RegulatoryLimit,
    ReportStatus,
    SampleMedium,
)


class DetectionReportDAO(BaseRepository[DetectionReport]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DetectionReport)

    def create_report(
        self,
        *,
        organization_id: str,
        filename: str,
        report_type: str,
        report_name: str | None = None,
        client_name: str | None = None,
        project_name: str | None = None,
        project_code: str | None = None,
        service_type: str | None = None,
        file_path: str | None = None,
        report_date: date | None = None,
        issuer: str | None = None,
        created_by_id: str | None = None,
    ) -> DetectionReport:
        report = DetectionReport(
            organization_id=organization_id,
            filename=filename,
            report_name=report_name,
            client_name=client_name,
            project_name=project_name,
            project_code=project_code,
            service_type=service_type,
            report_type=report_type,
            status=ReportStatus.UPLOADED,
            file_path=file_path,
            report_date=report_date,
            issuer=issuer,
            created_by_id=created_by_id,
        )
        return self.save_and_refresh(report)

    def update_status(
        self,
        *,
        report_id: str,
        status: ReportStatus,
        error_message: str | None = None,
    ) -> DetectionReport | None:
        report = self.get_by_id(report_id)
        if report is None:
            return None
        report.status = status
        report.error_message = error_message
        report.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(report)
        return report

    def list_for_org(
        self,
        *,
        organization_id: str | None,
        report_type: str | None,
        status: str | None,
        client_name: str | None,
        project_name: str | None,
        project_code: str | None,
        service_type: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[DetectionReport], int]:
        filters = []
        if organization_id:
            filters.append(DetectionReport.organization_id == organization_id)
        if report_type:
            filters.append(DetectionReport.report_type == report_type)
        if status:
            filters.append(DetectionReport.status == status)
        if client_name:
            filters.append(DetectionReport.client_name.like(f'%{client_name}%'))
        if project_name:
            filters.append(DetectionReport.project_name.like(f'%{project_name}%'))
        if project_code:
            filters.append(DetectionReport.project_code.like(f'%{project_code}%'))
        if service_type:
            filters.append(DetectionReport.service_type == service_type)
        return self.list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[DetectionReport.created_at.desc()],
        )


class DetectionSampleDAO(BaseRepository[DetectionSample]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DetectionSample)

    def add_sample(self, sample: DetectionSample) -> DetectionSample:
        return self.save_and_refresh(sample)

    def list_by_report(self, report_id: str) -> list[DetectionSample]:
        stmt = (
            select(DetectionSample)
            .where(DetectionSample.report_id == report_id)
            .order_by(DetectionSample.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def clear_by_report(self, report_id: str) -> None:
        """删除该报告下的全部样品（级联到 measurement）。重新解析时使用。"""
        for sample in self.list_by_report(report_id):
            self.session.delete(sample)
        self.session.commit()


class DetectionMeasurementDAO(BaseRepository[DetectionMeasurement]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, DetectionMeasurement)

    def add_measurement(self, measurement: DetectionMeasurement) -> DetectionMeasurement:
        return self.save_and_refresh(measurement)

    def list_by_sample(self, sample_id: str) -> list[DetectionMeasurement]:
        stmt = (
            select(DetectionMeasurement)
            .where(DetectionMeasurement.sample_id == sample_id)
            .order_by(DetectionMeasurement.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())

    def list_by_report(self, report_id: str) -> list[DetectionMeasurement]:
        stmt = (
            select(DetectionMeasurement)
            .join(DetectionSample, DetectionSample.id == DetectionMeasurement.sample_id)
            .where(DetectionSample.report_id == report_id)
            .order_by(DetectionSample.created_at.asc(), DetectionMeasurement.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())


class RegulatoryLimitDAO(BaseRepository[RegulatoryLimit]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, RegulatoryLimit)

    def list_filtered(
        self,
        *,
        indicator_name: str | None,
        medium: str | None,
        standard_code: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[RegulatoryLimit], int]:
        filters = []
        if indicator_name:
            like = f'%{indicator_name.strip()}%'
            filters.append(
                or_(
                    RegulatoryLimit.indicator_name.ilike(like),
                    RegulatoryLimit.aliases_json.ilike(like),
                )
            )
        if medium:
            filters.append(RegulatoryLimit.medium == medium)
        if standard_code:
            filters.append(RegulatoryLimit.standard_code == standard_code)
        return self.list_page(
            page=page,
            page_size=page_size,
            filters=filters,
            order_by=[
                RegulatoryLimit.indicator_name.asc(),
                RegulatoryLimit.priority.asc(),
            ],
        )

    def find_candidates(
        self,
        *,
        indicator_name: str,
        cas_no: str | None,
        medium: SampleMedium,
        limit_types: Sequence[LimitType] | None = None,
        as_of: date | None = None,
    ) -> list[RegulatoryLimit]:
        """按因子 + 介质 + 限值类型匹配候选限值，按 priority 升序返回。

        匹配口径：
        1. 介质必须一致（职业卫生空气 ≠ 废水）。
        2. 因子优先按 CAS 号精确匹配，否则按中文名 / aliases_json 模糊匹配。
        3. 生效区间（effective_from / effective_to）若有则必须覆盖 as_of。
        4. 默认按 priority 升序，再按 effective_from 倒序，便于 Service 层取首选。
        """
        name = indicator_name.strip()
        name_clauses = [
            RegulatoryLimit.indicator_name == name,
            RegulatoryLimit.aliases_json.ilike(f'%"{name}"%'),
        ]
        if cas_no:
            name_clauses.insert(0, RegulatoryLimit.cas_no == cas_no.strip())

        filters = [RegulatoryLimit.medium == medium, or_(*name_clauses)]
        if limit_types:
            filters.append(RegulatoryLimit.limit_type.in_(list(limit_types)))
        if as_of is not None:
            filters.append(
                and_(
                    or_(
                        RegulatoryLimit.effective_from.is_(None),
                        RegulatoryLimit.effective_from <= as_of,
                    ),
                    or_(
                        RegulatoryLimit.effective_to.is_(None),
                        RegulatoryLimit.effective_to >= as_of,
                    ),
                )
            )

        stmt = (
            select(RegulatoryLimit)
            .where(*filters)
            .order_by(
                RegulatoryLimit.priority.asc(),
                # MySQL 不支持 NULLS LAST，用 CASE 实现：NULL 排最后
                case((RegulatoryLimit.effective_from.is_(None), 1), else_=0),
                RegulatoryLimit.effective_from.desc(),
            )
        )
        return list(self.session.scalars(stmt).all())

    def upsert_fixture_limit(
        self,
        *,
        standard_code: str,
        indicator_name: str,
        medium: SampleMedium,
        limit_type: LimitType,
        unit: str,
        **fields,
    ) -> RegulatoryLimit:
        """测试夹具用：按 (standard_code, indicator_name, medium, limit_type) 去重写入。"""
        stmt = select(RegulatoryLimit).where(
            RegulatoryLimit.standard_code == standard_code,
            RegulatoryLimit.indicator_name == indicator_name,
            RegulatoryLimit.medium == medium,
            RegulatoryLimit.limit_type == limit_type,
        )
        existing = self.session.scalars(stmt).one_or_none()
        if existing is not None:
            for key, value in {'unit': unit, **fields}.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = audit_now_naive()
            self.session.commit()
            self.session.refresh(existing)
            return existing
        entity = RegulatoryLimit(
            standard_code=standard_code,
            indicator_name=indicator_name,
            medium=medium,
            limit_type=limit_type,
            unit=unit,
            **fields,
        )
        return self.save_and_refresh(entity)


class ComplianceResultDAO(BaseRepository[ComplianceResult]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, ComplianceResult)

    def replace_for_report(
        self,
        *,
        report_id: str,
        results: list[ComplianceResult],
    ) -> list[ComplianceResult]:
        """覆盖式写入：先清掉旧结果，再批量写入。"""
        existing = self.list_by_report(report_id)
        for old in existing:
            self.session.delete(old)
        self.session.flush()
        for item in results:
            self.session.add(item)
        self.session.commit()
        for item in results:
            self.session.refresh(item)
        return results

    def list_by_report(self, report_id: str) -> list[ComplianceResult]:
        stmt = (
            select(ComplianceResult)
            .where(ComplianceResult.report_id == report_id)
            .order_by(ComplianceResult.created_at.asc())
        )
        return list(self.session.scalars(stmt).all())


def serialize_aliases(aliases: list[str]) -> str | None:
    if not aliases:
        return None
    return json.dumps(aliases, ensure_ascii=False)


def deserialize_aliases(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
