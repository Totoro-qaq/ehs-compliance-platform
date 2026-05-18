"""SSE 进度推送：Celery Worker 发布状态变更 → Redis Pub/Sub → SSE 端点推送给前端。"""

from __future__ import annotations

import json

import redis

from app.core.config import settings

_CHANNEL_PREFIX = 'ehs:task_progress:'


def _get_redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def publish_task_progress(task_id: str, status: str, progress: int, error_message: str | None = None) -> None:
    """Worker 侧调用：将状态变更发布到 Redis channel。"""
    payload = json.dumps({
        'task_id': task_id,
        'status': status,
        'progress': progress,
        'error_message': error_message,
    }, ensure_ascii=False)
    client = _get_redis_client()
    try:
        client.publish(f'{_CHANNEL_PREFIX}{task_id}', payload)
    finally:
        client.close()


def subscribe_task_progress(task_id: str):
    """返回 Redis PubSub 对象，调用方负责关闭。"""
    client = _get_redis_client()
    pubsub = client.pubsub()
    pubsub.subscribe(f'{_CHANNEL_PREFIX}{task_id}')
    return pubsub
