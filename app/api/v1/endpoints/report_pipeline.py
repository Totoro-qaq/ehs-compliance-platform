from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.schemas.auth_context import CurrentUser
from app.schemas.report_pipeline_schema import (
    ReportSectionOut,
    ReportSectionReviewRequest,
    ReportSectionUpsertRequest,
)
from app.services.report_pipeline_service import ReportPipelineService

router = APIRouter(prefix='/report-pipeline', tags=['报告生成流水线'])


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
