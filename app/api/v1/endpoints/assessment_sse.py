"""SSE 端点：实时推送评价任务进度。"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.core.sse_broker import subscribe_task_progress
from app.models.db_models import AssessmentTask, TaskStatus
from app.schemas.auth_context import CurrentUser
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix='/assessment', tags=['评价任务'])


async def _sse_generator(request: Request, task_id: str, db: Session):
    """
    SSE 事件流生成器：
    1. 先推送当前状态（防止订阅前已完成的情况）
    2. 监听 Redis Pub/Sub 推送实时进度
    3. 终态（SUCCESS/FAILED）推送后自动关闭流
    """
    # 推送当前快照（兼容任务已完成但客户端刚连接的场景）
    task = db.get(AssessmentTask, task_id)
    if task is None:
        yield _format_sse({'event': 'error', 'data': {'message': '任务不存在'}})
        return

    current = {
        'task_id': task_id,
        'status': task.status.value if hasattr(task.status, 'value') else task.status,
        'progress': task.progress,
        'error_message': task.error_message,
    }
    yield _format_sse({'event': 'progress', 'data': current})

    # 如果已经是终态，直接结束
    if current['status'] in (TaskStatus.SUCCESS.value, TaskStatus.FAILED.value):
        yield _format_sse({'event': 'complete', 'data': current})
        return

    # 订阅 Redis Pub/Sub
    pubsub = subscribe_task_progress(task_id)
    heartbeat_interval = settings.sse_heartbeat_interval
    last_heartbeat = time.monotonic()
    try:
        while True:
            if await request.is_disconnected():
                break

            # 非阻塞获取消息（在线程池中执行阻塞调用）
            msg = await asyncio.to_thread(pubsub.get_message, ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg['type'] == 'message':
                payload = json.loads(msg['data'])
                yield _format_sse({'event': 'progress', 'data': payload})

                # 终态：推送 complete 事件后关闭
                if payload.get('status') in (TaskStatus.SUCCESS.value, TaskStatus.FAILED.value):
                    yield _format_sse({'event': 'complete', 'data': payload})
                    break
            else:
                await asyncio.sleep(0.2)
            if time.monotonic() - last_heartbeat >= heartbeat_interval:
                yield _format_sse({'event': 'heartbeat', 'data': {}})
                last_heartbeat = time.monotonic()
    finally:
        pubsub.unsubscribe()
        pubsub.close()


def _format_sse(msg: dict) -> str:
    """格式化为 SSE 文本帧。"""
    event = msg.get('event', 'message')
    data = json.dumps(msg.get('data', {}), ensure_ascii=False)
    return f'event: {event}\ndata: {data}\n\n'


@router.get(
    '/{task_id}/progress',
    summary='实时进度推送（SSE）',
    description=(
        '通过 Server-Sent Events 实时接收任务进度变更，替代轮询。\n\n'
        '**事件类型：**\n'
        '- `progress` — 状态/进度变更（含 `task_id`, `status`, `progress`, `error_message`）\n'
        '- `complete` — 任务到达终态（SUCCESS 或 FAILED），流自动关闭\n'
        '- `heartbeat` — 空心跳，保持连接活跃\n\n'
        '**使用方式：**\n'
        '```javascript\n'
        'const es = new EventSource(url, { headers: { Authorization: "Bearer <token>" } });\n'
        'es.addEventListener("progress", e => console.log(JSON.parse(e.data)));\n'
        'es.addEventListener("complete", e => { es.close(); });\n'
        '```'
    ),
    responses={200: {'content': {'text/event-stream': {}}}},
)
async def stream_task_progress(
    request: Request,
    task_id: str,
    actor: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    # 权限校验：确保用户有权查看该任务
    AssessmentService.get_assessment_task(db=db, actor=actor, task_id=task_id)

    return StreamingResponse(
        _sse_generator(request, task_id, db),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )
