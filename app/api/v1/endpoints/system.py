"""无需登录的运维 / 探测接口（挂载在 public_api_v1 下）。"""

from __future__ import annotations

import time
from typing import Any

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core import db as db_module
from app.core.config import settings
from app.core.logging_setup import get_logger

router = APIRouter(tags=['运维与探测'])
_log = get_logger(__name__)


@router.get('/healthz', summary='API v1 健康检查', description='返回状态 JSON；通常需网关将 /api/v1 前缀探活指到此处。')
def api_v1_healthz():
    """与根路径 /healthz 语义一致，便于统一走 /api/v1 前缀做网关探测。"""
    return {'status': 'ok'}


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
