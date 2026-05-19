from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.db_models import TaskStatus


class DefaultOrganizationMeta(BaseModel):
    """配置中的默认公司 ID 及库中是否存在该记录（含已软删）。"""

    default_organization_id: str
    exists_in_db: bool
    deleted_at: datetime | None = None
    name: str | None = None


class OrganizationAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class AssessmentTaskAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    filename: str
    content_type: str
    file_path: str
    status: TaskStatus
    progress: int
    result_json: str | None
    error_message: str | None
    parsed_text: str | None
    created_by_id: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
