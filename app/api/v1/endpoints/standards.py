from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.db import get_db
from app.schemas.auth_context import CurrentUser
from app.schemas.standard_schema import (
    StandardChunkSearchResponse,
    StandardManifestImportRequest,
    StandardManifestImportResponse,
)
from app.services.standard_library_service import StandardLibraryService

router = APIRouter(prefix='/standards', tags=['标准库 RAG'])


@router.post(
    '/manifest/import',
    response_model=StandardManifestImportResponse,
    summary='导入标准库 manifest 元数据',
    description='只接收已处理好的 manifest JSON，不上传、不读取、不解析标准/导则原文文件。',
)
def import_standard_manifest(
    payload: StandardManifestImportRequest,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardLibraryService.import_manifest(db=db, actor=actor, payload=payload)


@router.get(
    '/chunks/search',
    response_model=StandardChunkSearchResponse,
    summary='检索已入库标准条文 chunk',
)
def search_standard_chunks(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description='关键词；当前先走 MySQL 文本检索'),
    standard_code: str | None = Query(default=None, description='标准编号精确过滤'),
    domain: str | None = Query(default=None, description='领域过滤'),
    service_type: str | None = Query(default=None, description='服务类型过滤'),
    include_sensitive: bool = Query(default=False, description='仅管理员可包含敏感 chunk'),
    limit: int = Query(default=10, ge=1, le=50),
):
    return StandardLibraryService.search_chunks(
        db=db,
        actor=actor,
        query=q,
        standard_code=standard_code,
        domain=domain,
        service_type=service_type,
        include_sensitive=include_sensitive,
        limit=limit,
    )
