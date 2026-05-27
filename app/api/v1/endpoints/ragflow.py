from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.schemas.auth_context import CurrentUser
from app.services.rag.provider import RagflowService
from app.services.rag.schemas import RagChunkSearchResponse, RagHealthResponse

router = APIRouter(prefix='/ragflow', tags=['RAGFlow'])


@router.get(
    '/health',
    response_model=RagHealthResponse,
    summary='RAGFlow read-only integration healthcheck',
)
def ragflow_health(actor: Annotated[CurrentUser, Depends(get_current_user)]) -> RagHealthResponse:
    return RagflowService.healthcheck()


@router.get(
    '/chunks/search',
    response_model=RagChunkSearchResponse,
    summary='Search authorized RAGFlow guideline chunks',
)
def search_ragflow_chunks(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    q: str = Query(min_length=1, max_length=8000),
    standard_code: str | None = Query(default=None, max_length=64),
    domain: str | None = Query(default=None, max_length=64),
    service_type: str | None = Query(default=None, max_length=64),
    document_id: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=10, ge=1, le=50),
) -> RagChunkSearchResponse:
    return RagflowService.search_chunks(
        query=q,
        standard_code=standard_code,
        domain=domain,
        service_type=service_type,
        document_id=document_id,
        limit=limit,
    )


@router.get(
    '/clauses/search',
    response_model=RagChunkSearchResponse,
    summary='Search one guideline clause from authorized RAGFlow datasets',
)
def search_ragflow_clause(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    standard_code: str = Query(min_length=1, max_length=64),
    clause: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=5, ge=1, le=20),
) -> RagChunkSearchResponse:
    return RagflowService.get_clause(
        standard_code=standard_code,
        clause=clause,
        limit=limit,
    )
