from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RagChunkOut(BaseModel):
    provider: str = 'ragflow'
    dataset_id: str | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    standard_code: str | None = None
    standard_name: str | None = None
    clause: str | None = None
    page: int | None = None
    version: str | None = None
    effective_date: str | None = None
    source_uri: str | None = None
    authorized: bool = False
    license_id: str | None = None
    source_review_status: str | None = None
    allow_ai_retrieval: bool = False
    allow_excerpt_export: bool = False
    chunk_text: str = ''
    score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagChunkSearchResponse(BaseModel):
    provider: str = 'ragflow'
    configured: bool
    query: str | None = None
    dataset_ids: list[str] = Field(default_factory=list)
    items: list[RagChunkOut] = Field(default_factory=list)
    blocked_count: int = 0
    limit: int
    error: str | None = None


class RagHealthResponse(BaseModel):
    provider: str = 'ragflow'
    configured: bool
    ok: bool
    base_url: str | None = None
    dataset_ids: list[str] = Field(default_factory=list)
    error: str | None = None
