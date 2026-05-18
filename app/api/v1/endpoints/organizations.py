from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.schemas.auth_context import CurrentUser
from app.schemas.organization_schema import OrganizationCreate, OrganizationOut, OrganizationUpdate
from app.schemas.pagination import Page
from app.services.organization_service import OrganizationService

router = APIRouter(prefix='/organizations', tags=['公司管理'])


@router.post(
    '',
    response_model=OrganizationOut,
    summary='创建公司',
    description='仅管理员可创建新公司。公司名称不要求唯一但建议避免重复。',
)
def create_organization(
    payload: OrganizationCreate,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return OrganizationService.create(db=db, actor=actor, payload=payload)


@router.get('/', response_model=Page[OrganizationOut], include_in_schema=False)
@router.get(
    '',
    response_model=Page[OrganizationOut],
    summary='查询公司列表',
    description='普通用户仅能看到自己所属的公司；管理员可浏览全部公司列表。',
)
def list_organizations(
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1, description='页码'),
    page_size: int = Query(default=20, ge=1, le=200, description='每页条数'),
):
    return OrganizationService.list_page(db=db, actor=actor, page=page, page_size=page_size)


@router.get('/{org_id}/', response_model=OrganizationOut, include_in_schema=False)
@router.get(
    '/{org_id}',
    response_model=OrganizationOut,
    summary='查询公司详情',
    description='普通用户仅能查看本公司信息；管理员可查看任意公司。',
)
def get_organization(
    org_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return OrganizationService.get(db=db, actor=actor, org_id=org_id)


@router.patch(
    '/{org_id}',
    response_model=OrganizationOut,
    summary='更新公司信息',
    description='仅管理员可修改公司信息。支持部分更新（仅传需要修改的字段）。',
)
def update_organization(
    org_id: str,
    payload: OrganizationUpdate,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    return OrganizationService.update(db=db, actor=actor, org_id=org_id, payload=payload)


@router.delete(
    '/{org_id}',
    status_code=204,
    summary='删除公司',
    description='仅管理员可软删除公司。删除后该公司下的用户和任务仍保留，可通过管理接口恢复。',
)
def delete_organization(
    org_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    OrganizationService.soft_delete(db=db, actor=actor, org_id=org_id)
