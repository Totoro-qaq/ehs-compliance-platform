from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.schemas.auth_context import CurrentUser
from app.schemas.report_pipeline_schema import (
    ReportBootstrapRequest,
    ReportExportFormat,
    ReportReadinessOut,
    ReportSectionOut,
    ReportSectionReviewRequest,
    ReportSectionTemplateOut,
    ReportSectionUpsertRequest,
)
from app.services.report_pipeline_service import ReportPipelineService

router = APIRouter(prefix='/report-pipeline', tags=['报告生成流水线'])


@router.get(
    '/templates',
    response_model=list[ReportSectionTemplateOut],
    summary='List built-in report section templates',
)
def list_report_section_templates(
    _actor: Annotated[CurrentUser, Depends(get_current_user)],
):
    return ReportPipelineService.list_templates()


@router.post(
    '/sections',
    response_model=ReportSectionOut,
    summary='保存报告章节草稿并校验引用',
)
def upsert_report_section(
    payload: ReportSectionUpsertRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return ReportPipelineService.upsert_section(
        db=db,
        actor=actor,
        report_id=payload.report_id,
        section_key=payload.section_key,
        title=payload.title,
        draft_content=payload.draft_content,
        citation_memory_ids=payload.citation_memory_ids,
    )


@router.post(
    '/reports/{report_id}/bootstrap-sections',
    response_model=list[ReportSectionOut],
    summary='Create missing report sections from templates',
)
def bootstrap_report_sections(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    payload: ReportBootstrapRequest | None = None,
):
    return ReportPipelineService.bootstrap_sections(
        db=db,
        actor=actor,
        report_id=report_id,
        section_keys=payload.section_keys if payload is not None else None,
    )


@router.get(
    '/reports/{report_id}/sections',
    response_model=list[ReportSectionOut],
    summary='查询报告章节草稿列表',
)
def list_report_sections(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return ReportPipelineService.list_sections(db=db, actor=actor, report_id=report_id)


@router.get(
    '/reports/{report_id}/readiness',
    response_model=ReportReadinessOut,
    summary='Check whether report sections are ready for export',
)
def get_report_readiness(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return ReportPipelineService.get_readiness(db=db, actor=actor, report_id=report_id)


@router.get(
    '/reports/{report_id}/export',
    response_class=Response,
    summary='Export approved report sections',
)
def export_report(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    export_format: Annotated[ReportExportFormat, Query(alias='format')] = (
        ReportExportFormat.MARKDOWN
    ),
):
    export = ReportPipelineService.build_file_export(
        db=db,
        actor=actor,
        report_id=report_id,
        export_format=export_format,
    )
    encoded_filename = quote(export.filename)
    headers = {
        'Content-Disposition': (
            f'attachment; filename="report-export"; filename*=UTF-8\'\'{encoded_filename}'
        )
    }
    return Response(
        content=export.content,
        media_type=export.media_type,
        headers=headers,
    )


@router.patch(
    '/sections/{section_id}/review',
    response_model=ReportSectionOut,
    summary='更新报告章节人工复核状态',
)
def update_report_section_review(
    section_id: str,
    payload: ReportSectionReviewRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return ReportPipelineService.update_review_status(
        db=db,
        actor=actor,
        section_id=section_id,
        review_status=payload.review_status,
        review_note=payload.review_note,
    )
