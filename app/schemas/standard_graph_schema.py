from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.db_models import (
    ComplianceEvidenceType,
    ReportType,
    SampleMedium,
    StandardClauseStatus,
    StandardClauseType,
    StandardGraphNodeType,
    StandardRelationSourceType,
    StandardRelationType,
    StandardRuleReviewStatus,
)


class StandardClauseCreate(BaseModel):
    document_id: str | None = Field(default=None, max_length=36)
    standard_code: str = Field(min_length=1, max_length=64)
    standard_name: str = Field(min_length=1, max_length=255)
    version: str | None = Field(default=None, max_length=64)
    clause_code: str = Field(min_length=1, max_length=128)
    clause_title: str | None = Field(default=None, max_length=255)
    clause_type: StandardClauseType = StandardClauseType.OTHER
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    text_hash: str | None = Field(default=None, max_length=64)
    source_uri: str | None = Field(default=None, max_length=1024)
    status: StandardClauseStatus = StandardClauseStatus.ACTIVE
    effective_from: date | None = None
    effective_to: date | None = None


class StandardClauseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str | None = None
    standard_code: str
    standard_name: str
    version: str | None = None
    clause_code: str
    clause_title: str | None = None
    clause_type: StandardClauseType
    page_start: int | None = None
    page_end: int | None = None
    text_hash: str | None = None
    source_uri: str | None = None
    status: StandardClauseStatus
    effective_from: date | None = None
    effective_to: date | None = None
    created_at: datetime
    updated_at: datetime


class StandardRelationCreate(BaseModel):
    subject_type: StandardGraphNodeType
    subject_id: str = Field(min_length=1, max_length=128)
    relation_type: StandardRelationType
    object_type: StandardGraphNodeType
    object_id: str = Field(min_length=1, max_length=128)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    source_type: StandardRelationSourceType = StandardRelationSourceType.HUMAN
    is_verified: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class StandardRelationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    subject_type: StandardGraphNodeType
    subject_id: str
    relation_type: StandardRelationType
    object_type: StandardGraphNodeType
    object_id: str
    confidence: Decimal | None = None
    source_type: StandardRelationSourceType
    is_verified: bool
    verified_by_id: str | None = None
    verified_at: datetime | None = None
    metadata_json: str | None = None
    created_at: datetime
    updated_at: datetime


class StandardApplicabilityRuleCreate(BaseModel):
    standard_code: str = Field(min_length=1, max_length=64)
    clause_id: str | None = Field(default=None, max_length=36)
    report_type: ReportType | None = None
    medium: SampleMedium | None = None
    industry: str | None = Field(default=None, max_length=128)
    region: str | None = Field(default=None, max_length=64)
    pollutant_category: str | None = Field(default=None, max_length=128)
    indicator_name: str | None = Field(default=None, max_length=128)
    cas_no: str | None = Field(default=None, max_length=32)
    process_type: str | None = Field(default=None, max_length=128)
    applicability: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10000)
    effective_from: date | None = None
    effective_to: date | None = None
    review_status: StandardRuleReviewStatus = StandardRuleReviewStatus.PENDING


class StandardApplicabilityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    standard_code: str
    clause_id: str | None = None
    report_type: ReportType | None = None
    medium: SampleMedium | None = None
    industry: str | None = None
    region: str | None = None
    pollutant_category: str | None = None
    indicator_name: str | None = None
    cas_no: str | None = None
    process_type: str | None = None
    applicability_json: str | None = None
    priority: int
    effective_from: date | None = None
    effective_to: date | None = None
    review_status: StandardRuleReviewStatus
    created_at: datetime
    updated_at: datetime


class StandardPrecedenceRuleCreate(BaseModel):
    rule_name: str = Field(min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=64)
    region: str | None = Field(default=None, max_length=64)
    industry: str | None = Field(default=None, max_length=128)
    higher_standard_code: str = Field(min_length=1, max_length=64)
    lower_standard_code: str = Field(min_length=1, max_length=64)
    condition: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=10000)
    reason: str | None = None
    source_clause_id: str | None = Field(default=None, max_length=36)
    review_status: StandardRuleReviewStatus = StandardRuleReviewStatus.PENDING


class StandardPrecedenceRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_name: str
    domain: str | None = None
    region: str | None = None
    industry: str | None = None
    higher_standard_code: str
    lower_standard_code: str
    condition_json: str | None = None
    priority: int
    reason: str | None = None
    source_clause_id: str | None = None
    review_status: StandardRuleReviewStatus
    created_at: datetime
    updated_at: datetime


class ComplianceEvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    report_id: str
    sample_id: str | None = None
    measurement_id: str | None = None
    result_id: str | None = None
    standard_code: str | None = None
    standard_name: str | None = None
    clause_id: str | None = None
    limit_id: str | None = None
    source_id: str | None = None
    source_uri: str | None = None
    evidence_type: ComplianceEvidenceType
    evidence_summary: str
    metadata_json: str | None = None
    created_at: datetime
    updated_at: datetime
