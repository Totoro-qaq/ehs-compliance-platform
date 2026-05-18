"""无需登录的运维/探测接口（挂靠在 public_api_v1 下）。"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=['运维与探测'])


@router.get('/healthz', summary='API v1 健康检查', description='返回状态 JSON；通常需网关将 /api/v1 前缀探活指到此处。')
def api_v1_healthz():
    """与根路径 /healthz 语义一致，便于统一走 /api/v1 前缀做网关探测。"""
    return {'status': 'ok'}
