"""检测报告合规模块的 Pydantic schema。

字段口径与 ORM `db_models.DetectionReport` 等保持一致；
所有数值字段使用 Decimal，与库表 Numeric(18,6) 对齐，避免浮点误差。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.db_models import (
    ComplianceStatus,
    LimitType,
    ReportStatus,
    ReportType,
    SampleMedium,
)

# ---------------------------------------------------------------------------
# 检测报告 / 样品 / 测量
# ---------------------------------------------------------------------------


class DetectionMeasurementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    indicator_name: str
    indicator_alias: str | None = None
    cas_no: str | None = None
    raw_value: Decimal | None = None
    raw_unit: str | None = None
    normalized_value: Decimal | None = None
    normalized_unit: str | None = None
    detect_limit: Decimal | None = None
    method_code: str | None = None
    raw_text: str | None = None


class DetectionSampleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sample_point: str
    workplace: str | None = None
    post_name: str | None = None
    medium: SampleMedium
    sample_time_start: datetime | None = None
    sample_time_end: datetime | None = None
    duration_minutes: Decimal | None = None
    shift_hours: Decimal | None = None
    measurements: list[DetectionMeasurementResponse] = Field(default_factory=list)


class DetectionReportCreateResponse(BaseModel):
    """上传 Excel/CSV 后的简要返回。"""

    report_id: str
    status: ReportStatus
    report_type: ReportType
    sample_count: int = Field(description='已落库的检测点数量')
    measurement_count: int = Field(description='已落库的检测因子数量')
    warnings: list[str] = Field(default_factory=list, description='非阻塞性导入提示')


class DetectionReportSummary(BaseModel):
    """报告列表 / 详情头部信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    filename: str
    report_type: ReportType
    status: ReportStatus
    report_date: date | None = None
    issuer: str | None = None
    error_message: str | None = None
    created_by_id: str | None = None
    created_at: datetime
    updated_at: datetime


class DetectionReportDetail(DetectionReportSummary):
    """报告详情：附带样品 / 测量结构。"""

    samples: list[DetectionSampleResponse] = Field(default_factory=list)


class DetectionParsedRowPreview(BaseModel):
    row_index: int
    sample_point: str
    workplace: str | None = None
    post_name: str | None = None
    medium: SampleMedium | None = None
    indicator_name: str
    cas_no: str | None = None
    raw_value: Decimal | None = None
    raw_unit: str | None = None
    duration_minutes: Decimal | None = None
    shift_hours: Decimal | None = None
    raw_text: str
    confidence: Decimal
    warnings: list[str] = Field(default_factory=list)


class DetectionDocumentPreviewResponse(BaseModel):
    filename: str
    report_type: ReportType
    text_char_count: int
    text_excerpt: str
    rows: list[DetectionParsedRowPreview] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 法规限值库
# ---------------------------------------------------------------------------


class RegulatoryLimitBase(BaseModel):
    indicator_name: str = Field(min_length=1, max_length=128)
    cas_no: str | None = Field(default=None, max_length=32)
    aliases: list[str] = Field(default_factory=list, description='常见别名 / 英文名 / 商品名')
    medium: SampleMedium
    limit_type: LimitType
    limit_value: Decimal | None = None
    limit_min: Decimal | None = None
    limit_max: Decimal | None = None
    unit: str = Field(min_length=1, max_length=32)
    standard_code: str = Field(min_length=1, max_length=64)
    standard_name: str = Field(min_length=1, max_length=255)
    clause: str | None = Field(default=None, max_length=128)
    basis_text: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    applicability: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10000)


class RegulatoryLimitCreate(RegulatoryLimitBase):
    pass


class RegulatoryLimitUpdate(BaseModel):
    """限值库部分更新；所有字段可选。"""

    indicator_name: str | None = Field(default=None, min_length=1, max_length=128)
    cas_no: str | None = None
    aliases: list[str] | None = None
    medium: SampleMedium | None = None
    limit_type: LimitType | None = None
    limit_value: Decimal | None = None
    limit_min: Decimal | None = None
    limit_max: Decimal | None = None
    unit: str | None = None
    standard_code: str | None = None
    standard_name: str | None = None
    clause: str | None = None
    basis_text: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    applicability: dict[str, Any] | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)


class RegulatoryLimitResponse(RegulatoryLimitBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 合规判定结果
# ---------------------------------------------------------------------------


class ComplianceResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    sample_id: str
    measurement_id: str
    limit_id: str | None = None
    calculated_value: Decimal | None = None
    calculated_unit: str | None = None
    limit_value: Decimal | None = None
    limit_unit: str | None = None
    limit_type: LimitType | None = None
    status: ComplianceStatus
    exceedance_multiple: Decimal | None = None
    standard_code: str | None = None
    standard_name: str | None = None
    clause: str | None = None
    message: str | None = None


class ComplianceRunResponse(BaseModel):
    """一次合规计算任务的汇总结果。"""

    report_id: str
    status: ReportStatus
    total: int
    compliant: int
    exceeded: int
    borderline: int
    insufficient: int
    needs_review: int
    results: list[ComplianceResultResponse] = Field(default_factory=list)
