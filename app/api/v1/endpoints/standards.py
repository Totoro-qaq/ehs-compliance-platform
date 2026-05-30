from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.core.db import get_db
from app.models.db_models import (
    StandardRelationType,
    StandardRuleReviewStatus,
    StandardSourceReviewStatus,
    StandardSourceType,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.pagination import Page
from app.schemas.standard_graph_schema import (
    ComplianceEvidenceOut,
    StandardApplicabilityRuleCreate,
    StandardApplicabilityRuleOut,
    StandardClauseCreate,
    StandardClauseOut,
    StandardPrecedenceRuleCreate,
    StandardPrecedenceRuleOut,
    StandardRelationCreate,
    StandardRelationOut,
)
from app.schemas.standard_schema import (
    StandardChunkSearchResponse,
    StandardManifestImportRequest,
    StandardManifestImportResponse,
    StandardSourceCreate,
    StandardSourceOut,
    StandardSourceReviewRequest,
)
from app.services.standard_graph_service import StandardGraphService
from app.services.standard_library_service import StandardLibraryService

router = APIRouter(prefix='/standards', tags=['标准库 RAG'])


@router.get(
    '/sources',
    response_model=list[StandardSourceOut],
    summary='List standard source authorization records',
)
def list_standard_sources(
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
    review_status: StandardSourceReviewStatus | None = Query(default=None),
    source_type: StandardSourceType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    return StandardLibraryService.list_sources(
        db=db,
        actor=actor,
        review_status=review_status,
        source_type=source_type,
        limit=limit,
    )


@router.post(
    '/sources',
    response_model=StandardSourceOut,
    summary='Create standard source authorization record',
)
def create_standard_source(
    payload: StandardSourceCreate,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardLibraryService.create_source(db=db, actor=actor, payload=payload)


@router.patch(
    '/sources/{source_id}/review',
    response_model=StandardSourceOut,
    summary='Review standard source authorization record',
)
def review_standard_source(
    source_id: str,
    payload: StandardSourceReviewRequest,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardLibraryService.review_source(
        db=db,
        actor=actor,
        source_id=source_id,
        payload=payload,
    )


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
    include_unapproved: bool = Query(default=False, description='仅管理员可查看未授权 chunk'),
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
        include_unapproved=include_unapproved,
        limit=limit,
    )


@router.post(
    '/clauses',
    response_model=StandardClauseOut,
    summary='创建结构化标准条款',
)
def create_standard_clause(
    payload: StandardClauseCreate,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardGraphService.create_clause(db=db, actor=actor, payload=payload)


@router.get(
    '/clauses',
    response_model=Page[StandardClauseOut],
    summary='查询结构化标准条款',
)
def list_standard_clauses(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, max_length=255),
    standard_code: str | None = Query(default=None, max_length=64),
    document_id: str | None = Query(default=None, max_length=36),
    include_unapproved: bool = Query(default=False),
):
    return StandardGraphService.list_clauses(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        query=q,
        standard_code=standard_code,
        document_id=document_id,
        include_unapproved=include_unapproved,
    )


@router.post(
    '/relations',
    response_model=StandardRelationOut,
    summary='创建标准图谱关系',
)
def create_standard_relation(
    payload: StandardRelationCreate,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardGraphService.create_relation(db=db, actor=actor, payload=payload)


@router.get(
    '/relations',
    response_model=Page[StandardRelationOut],
    summary='查询标准图谱关系',
)
def list_standard_relations(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    subject_id: str | None = Query(default=None, max_length=128),
    object_id: str | None = Query(default=None, max_length=128),
    relation_type: StandardRelationType | None = Query(default=None),
):
    return StandardGraphService.list_relations(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        subject_id=subject_id,
        object_id=object_id,
        relation_type=relation_type,
    )


@router.post(
    '/applicability-rules',
    response_model=StandardApplicabilityRuleOut,
    summary='创建标准适用规则',
)
def create_standard_applicability_rule(
    payload: StandardApplicabilityRuleCreate,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardGraphService.create_applicability_rule(db=db, actor=actor, payload=payload)


@router.get(
    '/applicability-rules',
    response_model=Page[StandardApplicabilityRuleOut],
    summary='查询标准适用规则',
)
def list_standard_applicability_rules(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    standard_code: str | None = Query(default=None, max_length=64),
    review_status: StandardRuleReviewStatus | None = Query(default=None),
):
    return StandardGraphService.list_applicability_rules(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        standard_code=standard_code,
        review_status=review_status,
    )


@router.post(
    '/precedence-rules',
    response_model=StandardPrecedenceRuleOut,
    summary='创建标准优先级规则',
)
def create_standard_precedence_rule(
    payload: StandardPrecedenceRuleCreate,
    actor: Annotated[CurrentUser, Depends(require_admin)],
    db: Session = Depends(get_db),
):
    return StandardGraphService.create_precedence_rule(db=db, actor=actor, payload=payload)


@router.get(
    '/precedence-rules',
    response_model=Page[StandardPrecedenceRuleOut],
    summary='查询标准优先级规则',
)
def list_standard_precedence_rules(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    standard_code: str | None = Query(default=None, max_length=64),
    review_status: StandardRuleReviewStatus | None = Query(default=None),
):
    return StandardGraphService.list_precedence_rules(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        standard_code=standard_code,
        review_status=review_status,
    )


@router.get(
    '/evidence',
    response_model=Page[ComplianceEvidenceOut],
    summary='查询合规判定证据链',
)
def list_compliance_evidence(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    report_id: str | None = Query(default=None, max_length=36),
    result_id: str | None = Query(default=None, max_length=36),
):
    return StandardGraphService.list_evidence(
        db=db,
        actor=actor,
        page=page,
        page_size=page_size,
        report_id=report_id,
        result_id=result_id,
    )
