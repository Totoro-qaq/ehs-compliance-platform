from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.schemas.auth_context import CurrentUser
from app.schemas.detection_schema import (
    ComplianceResultResponse,
    ComplianceRunResponse,
    DetectionDocumentImportRequest,
    DetectionDocumentPreviewResponse,
    DetectionReportCreateResponse,
    DetectionReportDetail,
    DetectionReportSummary,
    RegulatoryLimitCreate,
    RegulatoryLimitResponse,
    RegulatoryLimitUpdate,
)
from app.schemas.pagination import Page
from app.services.detection_compliance_service import DetectionComplianceService
from app.services.detection_document_parse_service import DetectionDocumentParseService

router = APIRouter(prefix='/detection', tags=['检测报告合规'])


@router.post(
    '/reports',
    response_model=DetectionReportCreateResponse,
    summary='上传检测报告结构化数据',
)
async def create_detection_report(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(..., description='CSV / XLSX / XLSM 检测数据文件'),
    report_type: str = Form(default='OCCUPATIONAL_HEALTH', description='检测报告类型'),
    report_name: str | None = Form(default=None, description='检测报告名称；不传则按公司、类型和日期自动生成'),
    organization_id: str | None = Form(default=None, description='公司 ID；普通用户不传则使用本人所属公司'),
    db: Session = Depends(get_db),
):
    content = await file.read()
    return DetectionComplianceService.create_report_from_upload(
        db=db,
        actor=actor,
        organization_id=organization_id or actor.organization_id or settings.default_organization_id,
        report_type=report_type,
        filename=file.filename,
        report_name=report_name,
        content=content,
    )


@router.post(
    '/documents/preview',
    response_model=DetectionDocumentPreviewResponse,
    summary='预览解析 PDF/DOCX 检测报告',
)
async def preview_detection_document(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(..., description='PDF / DOCX / DOC / TXT 检测报告文件'),
    report_type: str = Form(default='OCCUPATIONAL_HEALTH', description='检测报告类型'),
):
    _ = actor
    content = await file.read()
    return DetectionDocumentParseService.preview(
        filename=file.filename,
        content=content,
        report_type=report_type,
    )


@router.post(
    '/documents/import',
    response_model=DetectionReportCreateResponse,
    summary='确认导入 PDF/DOCX 解析预览结果',
)
def import_detection_document_preview(
    payload: DetectionDocumentImportRequest,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return DetectionDocumentParseService.import_preview(db=db, actor=actor, payload=payload)


@router.get('/', response_model=Page[DetectionReportSummary], include_in_schema=False)
@router.get(
    '/reports',
    response_model=Page[DetectionReportSummary],
    summary='查询检测报告列表',
)
def list_detection_reports(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    organization_id: str | None = Query(default=None, description='按公司 ID 筛选'),
    report_type: str | None = Query(default=None, description='按报告类型筛选'),
    status: str | None = Query(default=None, description='按报告状态筛选'),
    page: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=20, ge=1, le=200, description='每页条数'),
):
    return DetectionComplianceService.list_reports(
        db=db,
        actor=actor,
        organization_id=organization_id,
        report_type=report_type,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get('/reports/{report_id}/', response_model=DetectionReportDetail, include_in_schema=False)
@router.get(
    '/reports/{report_id}',
    response_model=DetectionReportDetail,
    summary='查询检测报告详情',
)
def get_detection_report(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return DetectionComplianceService.get_report_detail(db=db, actor=actor, report_id=report_id)


@router.post(
    '/reports/{report_id}/calculate',
    response_model=ComplianceRunResponse,
    summary='运行合规判定',
)
def calculate_detection_report(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return DetectionComplianceService.run_report_compliance(
        db=db,
        actor=actor,
        report_id=report_id,
    )


@router.get('/reports/{report_id}/results/', response_model=list[ComplianceResultResponse], include_in_schema=False)
@router.get(
    '/reports/{report_id}/results',
    response_model=list[ComplianceResultResponse],
    summary='查询合规判定结果',
)
def list_detection_results(
    report_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return DetectionComplianceService.list_results(db=db, actor=actor, report_id=report_id)


@router.get('/limits/', response_model=Page[RegulatoryLimitResponse], include_in_schema=False)
@router.get(
    '/limits',
    response_model=Page[RegulatoryLimitResponse],
    summary='查询法规限值库',
)
def list_regulatory_limits(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    indicator_name: str | None = Query(default=None, description='按因子名/别名模糊查询'),
    medium: str | None = Query(default=None, description='按介质筛选'),
    standard_code: str | None = Query(default=None, description='按标准编号筛选'),
    page: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=20, ge=1, le=200, description='每页条数'),
):
    return DetectionComplianceService.list_limits(
        db=db,
        actor=actor,
        indicator_name=indicator_name,
        medium=medium,
        standard_code=standard_code,
        page=page,
        page_size=page_size,
    )


@router.post(
    '/limits',
    response_model=RegulatoryLimitResponse,
    summary='新增法规限值',
)
def create_regulatory_limit(
    payload: RegulatoryLimitCreate,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return DetectionComplianceService.create_limit(db=db, actor=actor, payload=payload)


@router.put(
    '/limits/{limit_id}',
    response_model=RegulatoryLimitResponse,
    summary='更新法规限值',
)
def update_regulatory_limit(
    limit_id: str,
    payload: RegulatoryLimitUpdate,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return DetectionComplianceService.update_limit(
        db=db,
        actor=actor,
        limit_id=limit_id,
        payload=payload,
    )


@router.delete(
    '/limits/{limit_id}',
    status_code=204,
    summary='删除法规限值',
)
def delete_regulatory_limit(
    limit_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    DetectionComplianceService.delete_limit(db=db, actor=actor, limit_id=limit_id)
