"""API v1：公开路由 + 管理员路由 + 默认需登录的业务路由。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.agent import router as agent_router
from app.api.v1.endpoints.assessment import router as assessment_router
from app.api.v1.endpoints.assessment_sse import router as assessment_sse_router
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.detection import router as detection_router
from app.api.v1.endpoints.organizations import router as organizations_router
from app.api.v1.endpoints.ragflow import router as ragflow_router
from app.api.v1.endpoints.report_pipeline import router as report_pipeline_router
from app.api.v1.endpoints.standards import router as standards_router
from app.api.v1.endpoints.system import router as system_router

# 无需登录：身份 / 运维探测 /（未来）第三方回调
public_api_v1 = APIRouter(prefix='/api/v1')
public_api_v1.include_router(auth_router)
public_api_v1.include_router(system_router)
# 未来：from app.api.v1.endpoints.callbacks import router as callbacks_router
# public_api_v1.include_router(callbacks_router)

# 管理员：require_admin 内处理 JWT 或 X-Admin-Key，不能套全局 get_current_user
admin_api_v1 = APIRouter(prefix='/api/v1')
admin_api_v1.include_router(admin_router)

# 默认登录：公司、评价等业务（鉴权由各端点显式 Depends(get_current_user)，避免与路由级依赖重复）
business_api_v1 = APIRouter(prefix='/api/v1')
business_api_v1.include_router(organizations_router)
business_api_v1.include_router(assessment_router)
business_api_v1.include_router(assessment_sse_router)
business_api_v1.include_router(detection_router)
business_api_v1.include_router(agent_router)
business_api_v1.include_router(standards_router)
business_api_v1.include_router(ragflow_router)
business_api_v1.include_router(report_pipeline_router)


def include_api_v1(app) -> None:
    """向应用挂载 v1 全部子路由（顺序无关）。"""
    app.include_router(public_api_v1)
    app.include_router(admin_api_v1)
    app.include_router(business_api_v1)
