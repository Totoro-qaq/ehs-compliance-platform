from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.schemas.auth_context import CurrentUser
from app.schemas.ehs_schema import AssessmentCreateResponse, AssessmentStatusResponse
from app.schemas.pagination import Page
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix='/assessment', tags=['评价任务'])


@router.post(
    '',
    response_model=AssessmentCreateResponse,
    summary='上传材料并创建评价任务',
    description=(
        '上传 PDF/TXT/Word/CSV 格式的评价材料，系统异步调用 AI 工作流进行 EHS 合规分析。\n\n'
        '- 文件大小上限 50 MB，支持扩展名：.pdf .txt .doc .docx .csv\n'
        '- 成功后返回 `task_id`，可通过 SSE 或轮询接口跟踪进度\n'
        '- 普通用户仅能指定本人所属公司；管理员可指定任意公司'
    ),
)
async def create_assessment(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    file: UploadFile = File(..., description='评价相关材料（如 PDF）'),
    organization_id: str | None = Form(
        default=None, description='公司 ID；不传则使用系统默认公司（管理员可指定其他公司）'
    ),
    db: Session = Depends(get_db),
):
    content = await file.read()
    oid = organization_id or settings.default_organization_id
    return await AssessmentService.create_assessment_task(
        db=db,
        actor=actor,
        organization_id=oid,
        filename=file.filename,
        content_type=file.content_type or 'application/octet-stream',
        file_bytes=content,
    )


@router.get(
    '/',
    response_model=Page[AssessmentStatusResponse],
    include_in_schema=False,
)
@router.get(
    '',
    response_model=Page[AssessmentStatusResponse],
    summary='分页查询评价任务列表',
    description=(
        '按公司维度分页查询评价任务。\n\n'
        '- 普通用户仅能查询本公司任务\n'
        '- 管理员可通过 `organization_id` 参数筛选任意公司'
    ),
)
def list_assessments(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    organization_id: str | None = Query(default=None, description='筛选公司 ID'),
    status: str | None = Query(default=None, description='筛选任务状态，如 PENDING / SUCCESS / FAILED'),
    q: str | None = Query(default=None, description='按文件名模糊搜索，或按任务 ID 精确搜索'),
    page: int = Query(default=1, ge=1, description='页码，从 1 开始'),
    page_size: int = Query(default=20, ge=1, le=200, description='每页条数'),
):
    return AssessmentService.list_assessment_tasks(
        db=db,
        actor=actor,
        organization_id=organization_id,
        status=status,
        q=q,
        page=page,
        page_size=page_size,
    )


@router.get('/{task_id}/', response_model=AssessmentStatusResponse, include_in_schema=False)
@router.get(
    '/{task_id}',
    response_model=AssessmentStatusResponse,
    summary='查询评价任务详情',
    description='返回任务当前状态、进度百分比及结构化分析结果（任务完成后 `result` 字段非空）。',
)
def get_assessment(
    task_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return AssessmentService.get_assessment_task(db=db, actor=actor, task_id=task_id)


@router.post(
    '/{task_id}/requeue',
    response_model=AssessmentCreateResponse,
    summary='重新分析失败任务',
    description='仅失败状态的评价任务可以重新投递。普通用户只能重新投递自己创建的任务，管理员不受此限制。',
)
def requeue_assessment(
    task_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return AssessmentService.requeue_failed_task(db=db, actor=actor, task_id=task_id)


@router.delete(
    '/{task_id}',
    status_code=204,
    summary='删除评价任务',
    description='软删除评价任务（可由管理员恢复）。普通用户仅能删除自己创建的任务，管理员不受限。关联文件将在保留期后自动清理。',
)
def delete_assessment(
    task_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    AssessmentService.soft_delete_task(db=db, actor=actor, task_id=task_id)
