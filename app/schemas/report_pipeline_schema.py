from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from app.models.db_models import (
    ReportSectionCitationCheckStatus,
    ReportSectionReviewStatus,
)


class ReportExportFormat(str, Enum):
    MARKDOWN = 'markdown'
    TXT = 'txt'
    DOCX = 'docx'
    DOC = 'doc'


class ReportSectionUpsertRequest(BaseModel):
    report_id: str = Field(min_length=1, max_length=36)
    section_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    draft_content: str = Field(min_length=1)
    citation_memory_ids: list[str] = Field(default_factory=list, max_length=50)


class ReportSectionReviewRequest(BaseModel):
    review_status: ReportSectionReviewStatus
    review_note: str | None = Field(default=None, max_length=1000)


class ReportSectionTemplateOut(BaseModel):
    section_key: str
    title: str
    description: str
    required: bool
    sort_order: int


class ReportBootstrapRequest(BaseModel):
    section_keys: list[str] | None = Field(default=None, max_length=20)


class ReportReadinessIssueOut(BaseModel):
    code: str
    message: str
    section_key: str | None = None
    title: str | None = None


class ReportReadinessOut(BaseModel):
    report_id: str
    ready: bool
    required_section_keys: list[str]
    issues: list[ReportReadinessIssueOut] = Field(default_factory=list)


class ReportSectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    report_id: str
    section_key: str
    title: str
    draft_content: str
    citation_memory_ids: list[str] = Field(default_factory=list)
    citation_check_status: ReportSectionCitationCheckStatus
    citation_check_message: str | None = None
    review_status: ReportSectionReviewStatus
    review_note: str | None = None
    reviewed_by_id: str | None = None
    reviewed_at: datetime | None = None
    created_by_id: str | None = None
    created_at: datetime
    updated_at: datetime
