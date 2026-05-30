from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.db_models import StandardSourceReviewStatus, StandardSourceType


class StandardSourceCreate(BaseModel):
    source_name: str = Field(min_length=1, max_length=255)
    source_type: StandardSourceType = StandardSourceType.CUSTOMER_PROVIDED
    provider_name: str | None = Field(default=None, max_length=255)
    license_no: str | None = Field(default=None, max_length=128)
    license_scope: str | None = None
    organization_id: str | None = Field(default=None, max_length=36)
    allow_storage: bool = False
    allow_vectorization: bool = False
    allow_ai_retrieval: bool = False
    allow_excerpt_export: bool = False
    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = None


class StandardSourceReviewRequest(BaseModel):
    review_status: StandardSourceReviewStatus
    allow_storage: bool | None = None
    allow_vectorization: bool | None = None
    allow_ai_retrieval: bool | None = None
    allow_excerpt_export: bool | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    notes: str | None = None


class StandardSourceOut(BaseModel):
    id: str
    source_name: str
    source_type: StandardSourceType
    provider_name: str | None = None
    license_no: str | None = None
    license_scope: str | None = None
    organization_id: str | None = None
    allow_storage: bool
    allow_vectorization: bool
    allow_ai_retrieval: bool
    allow_excerpt_export: bool
    effective_from: date | None = None
    effective_to: date | None = None
    review_status: StandardSourceReviewStatus
    reviewed_by_id: str | None = None
    reviewed_at: datetime | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class StandardChunkManifestItem(BaseModel):
    chunk_id: str | None = Field(default=None, max_length=128)
    chunk_index: int = Field(ge=0)
    clause: str | None = Field(default=None, max_length=128)
    text_chunk: str = Field(min_length=1)
    text_hash: str | None = Field(default=None, max_length=64)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    is_sensitive: bool = False
    milvus_collection: str | None = Field(default=None, max_length=128)
    milvus_id: str | None = Field(default=None, max_length=128)
    embedding_model: str | None = Field(default=None, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StandardDocumentManifestItem(BaseModel):
    standard_code: str = Field(min_length=1, max_length=64)
    standard_name: str = Field(min_length=1, max_length=255)
    domain: str = Field(min_length=1, max_length=64)
    service_type: str | None = Field(default=None, max_length=64)
    source_id: str | None = Field(default=None, max_length=36)
    license_id: str | None = Field(default=None, max_length=128)
    storage_backend: str = Field(default='minio', max_length=32)
    bucket: str | None = Field(default=None, max_length=128)
    object_key: str | None = Field(default=None, max_length=1024)
    object_version: str | None = Field(default=None, max_length=128)
    source_path: str | None = Field(default=None, max_length=1024)
    source_filename: str | None = Field(default=None, max_length=255)
    source_format: str | None = Field(default=None, max_length=32)
    file_hash: str = Field(min_length=8, max_length=64)
    file_size_bytes: int | None = Field(default=None, ge=0)
    version: str | None = Field(default=None, max_length=64)
    effective_from: date | None = None
    effective_to: date | None = None
    status: str = Field(default='ACTIVE', max_length=32)
    is_sensitive: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunks: list[StandardChunkManifestItem] = Field(default_factory=list)

    @field_validator('storage_backend', 'standard_code', 'domain', 'status', mode='before')
    @classmethod
    def _strip_upperish(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class StandardManifestImportRequest(BaseModel):
    documents: list[StandardDocumentManifestItem] = Field(min_length=1)
    replace_chunks: bool = True
    allow_sensitive_chunks: bool = False


class StandardDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    standard_code: str
    standard_name: str
    domain: str
    service_type: str | None = None
    organization_id: str | None = None
    source_id: str | None = None
    license_id: str | None = None
    source_review_status: StandardSourceReviewStatus
    authorized: bool
    allow_ai_retrieval: bool
    allow_excerpt_export: bool
    storage_backend: str
    bucket: str | None = None
    object_key: str | None = None
    object_version: str | None = None
    source_filename: str
    source_format: str | None = None
    file_hash: str
    file_size_bytes: int | None = None
    version: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    status: str
    is_sensitive: bool
    created_at: datetime
    updated_at: datetime


class StandardChunkOut(BaseModel):
    id: str
    document_id: str
    chunk_id: str
    chunk_index: int
    standard_code: str
    standard_name: str
    clause: str | None = None
    domain: str
    service_type: str | None = None
    organization_id: str | None = None
    source_id: str | None = None
    license_id: str | None = None
    source_review_status: StandardSourceReviewStatus
    authorized: bool
    allow_ai_retrieval: bool
    allow_excerpt_export: bool
    text_chunk: str
    text_hash: str
    page_start: int | None = None
    page_end: int | None = None
    is_sensitive: bool
    milvus_collection: str | None = None
    milvus_id: str | None = None
    embedding_model: str | None = None
    indexed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StandardManifestDocumentResult(BaseModel):
    document_id: str
    standard_code: str
    file_hash: str
    source_id: str | None = None
    source_review_status: StandardSourceReviewStatus
    allow_ai_retrieval: bool
    created: bool
    chunks_written: int
    chunks_skipped_sensitive: int


class StandardManifestImportResponse(BaseModel):
    documents_total: int
    documents_created: int
    documents_updated: int
    chunks_written: int
    chunks_skipped_sensitive: int
    documents: list[StandardManifestDocumentResult] = Field(default_factory=list)


class StandardChunkSearchResponse(BaseModel):
    query: str | None = None
    include_sensitive: bool = False
    include_unapproved: bool = False
    items: list[StandardChunkOut] = Field(default_factory=list)
    limit: int
