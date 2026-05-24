"""无需登录的运维 / 探测接口（挂载在 public_api_v1 下）。"""

from __future__ import annotations

import time
from typing import Any

import redis
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core import db as db_module
from app.core.config import settings
from app.core.db import get_db
from app.core.logging_setup import get_logger
from app.models.db_models import AssessmentTask, DetectionReport, Organization

router = APIRouter(tags=['运维与探测'])
_log = get_logger(__name__)


class PlatformStatsOut(BaseModel):
    total_tasks: int = Field(ge=0, description='累计任务数（评价任务 + 检测任务）')
    assessment_tasks: int = Field(ge=0, description='累计评价任务数')
    detection_tasks: int = Field(ge=0, description='累计检测任务数')
    companies_served: int = Field(ge=0, description='已注册公司数量（不含已删除公司）')
    completed_tasks: int = Field(ge=0, description='已完成任务总数（评价 SUCCESS + 检测 CALCULATED）')


@router.get('/healthz', summary='API v1 健康检查', description='返回状态 JSON；通常需网关将 /api/v1 前缀探活指到此处。')
def api_v1_healthz():
    """与根路径 /healthz 语义一致，便于统一走 /api/v1 前缀做网关探测。"""
    return {'status': 'ok'}


@router.get(
    '/platform/stats',
    response_model=PlatformStatsOut,
    summary='公开平台统计',
    description='返回首页可公开展示的轻量统计数据，不包含成功/失败等内部运营明细。',
)
def public_platform_stats(db: Session = Depends(get_db)):
    assessment_total = db.scalar(select(func.count()).select_from(AssessmentTask)) or 0
    detection_total = db.scalar(select(func.count()).select_from(DetectionReport)) or 0

    # 首页展示口径按平台注册公司数统计；纯 count 显式排除软删除公司。
    companies_served = (
        db.scalar(select(func.count()).select_from(Organization).where(Organization.deleted_at.is_(None)))
        or 0
    )

    # 已完成任务总量：评价 SUCCESS + 检测 CALCULATED
    completed_assessment = (
        db.scalar(select(func.count()).where(AssessmentTask.status == 'SUCCESS')) or 0
    )
    completed_detection = (
        db.scalar(
            select(func.count()).where(DetectionReport.status == 'CALCULATED')
        )
        or 0
    )

    return PlatformStatsOut(
        total_tasks=assessment_total + detection_total,
        assessment_tasks=assessment_total,
        detection_tasks=detection_total,
        companies_served=companies_served,
        completed_tasks=completed_assessment + completed_detection,
    )


def _check_database() -> tuple[bool, str | None]:
    try:
        with db_module.SessionLocal() as db:
            db.execute(text('SELECT 1'))
        return True, None
    except Exception as exc:
        _log.warning('Readiness database check failed: %s', exc)
        return False, type(exc).__name__


def _check_redis() -> tuple[bool, str | None]:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        client.ping()
        return True, None
    except Exception as exc:
        _log.warning('Readiness redis check failed: %s', exc)
        return False, type(exc).__name__
    finally:
        client.close()


@router.get('/readyz', summary='API v1 就绪检查', description='检查数据库与 Redis 是否可用；失败时返回 503。')
def api_v1_readyz():
    """部署探针使用：依赖不可用时返回 503，避免接入层继续转发业务流量。"""
    started = time.perf_counter()
    checks: dict[str, dict[str, Any]] = {}

    db_ok, db_error = _check_database()
    checks['database'] = {'ok': db_ok, 'error': db_error}

    redis_ok, redis_error = _check_redis()
    checks['redis'] = {'ok': redis_ok, 'error': redis_error}

    ready = all(item['ok'] for item in checks.values())
    payload = {
        'status': 'ready' if ready else 'degraded',
        'checks': checks,
        'elapsed_ms': int((time.perf_counter() - started) * 1000),
    }
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)
