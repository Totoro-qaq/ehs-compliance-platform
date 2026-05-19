#!/usr/bin/env python3
"""
端到端自检脚本：按环节探测 FastAPI、Redis、Celery Worker、Dify Key、登录与创建评价任务。
在仓库根目录执行：
    python scripts/e2e_pipeline.py
    python scripts/e2e_pipeline.py --skip-dify --poll-timeout 30

默认：若执行了 Dify 探针且返回 401 等失败，将直接结束（不再登录/创建任务），避免无意义轮询。
若仍要在 Dify 失败时跑通 API：加 --continue-after-dify-failure

可选环境变量（未设置时尽量使用 .env 内已有项）：
  E2E_BASE_URL            默认 http://127.0.0.1:8000
  E2E_IDENTIFIER          登录标识（用户名/邮箱/手机号）；默认 BOOTSTRAP_ADMIN_USERNAME
  E2E_PASSWORD            登录密码；默认 BOOTSTRAP_ADMIN_PASSWORD
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 保证可 import app.*
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)


@dataclass
class StepResult:
    step: str
    ok: bool
    message: str = ''
    hint: str = ''
    detail: dict[str, Any] = field(default_factory=dict)


def _as_report(steps: list[StepResult]) -> dict[str, Any]:
    return {
        'overall_ok': all(s.ok for s in steps),
        'steps': [asdict(s) for s in steps],
    }


def _http_request(
    base: str,
    method: str,
    path: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[int, dict[str, Any] | str]:
    url = f'{base.rstrip("/")}{path}'
    hdrs = dict(headers or {})
    req = Request(url, data=data, method=method, headers=hdrs)
    try:
        with urlopen(req, timeout=timeout) as resp:  # nosec - E2E 自控 URL
            raw = resp.read().decode('utf-8', errors='replace')
            status = resp.status
    except HTTPError as exc:
        status = exc.code
        raw = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
    except URLError as exc:
        raise ConnectionError(f'无法连接 {url}: {exc.reason!s}') from exc

    try:
        body: dict[str, Any] | str = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        body = raw[:2000]
    return status, body


def _unwrap_envelope(body: dict[str, Any] | str, http_status: int, context: str) -> Any:
    if not isinstance(body, dict):
        raise RuntimeError(f'{context}: HTTP {http_status}，响应非 JSON 信封，片段={str(body)[:300]}')
    if not body.get('success'):
        code = body.get('code', '')
        msg = body.get('message', '')
        raise RuntimeError(f'{context}: HTTP {http_status}，业务失败 code={code} message={msg}')
    return body.get('data')


def _normalize_maybe_envelope(body: dict[str, Any] | str) -> dict[str, Any]:
    """根路径 /healthz 为裸 JSON；多数业务路径为 ApiEnvelope。"""
    if not isinstance(body, dict):
        return {}
    if body.get('success') is True and isinstance(body.get('data'), dict):
        return body['data']
    return body


def _multipart_body(
    fields: dict[str, str],
    file_name: str,
    file_bytes: bytes,
    file_content_type: str,
) -> tuple[bytes, str]:
    boundary = f'----E2EFormBoundary{uuid.uuid4().hex}'
    crlf = b'\r\n'
    parts: list[bytes] = []

    for key, val in fields.items():
        parts.append(f'--{boundary}'.encode() + crlf)
        parts.append(f'Content-Disposition: form-data; name="{key}"'.encode() + crlf + crlf)
        parts.append(val.encode('utf-8') + crlf)

    parts.append(f'--{boundary}'.encode() + crlf)
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"'.encode()
        + crlf
    )
    parts.append(f'Content-Type: {file_content_type}'.encode() + crlf + crlf)
    parts.append(file_bytes + crlf)
    parts.append(f'--{boundary}--'.encode() + crlf)
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def step_load_config() -> StepResult:
    try:
        from app.core.config import settings

        return StepResult(
            step='load_config',
            ok=True,
            message='已加载 .env / 环境变量',
            detail={
                'upload_dir': settings.upload_dir,
                'dify_base_url': settings.dify_base_url,
                'dify_api_key_configured': bool(settings.dify_api_key and settings.dify_api_key.strip()),
                'celery_broker': settings.celery_broker_url.split('@')[-1] if '@' in settings.celery_broker_url else settings.celery_broker_url,
            },
        )
    except Exception as exc:
        return StepResult(
            step='load_config',
            ok=False,
            message=f'读取配置失败: {exc}',
            hint='确认在仓库根目录执行，且已安装依赖；检查 .env 编码为 UTF-8',
            detail={'exc_type': type(exc).__name__},
        )


def step_redis() -> StepResult:
    try:
        import redis  # type: ignore[import-untyped]

        from app.core.config import settings

        client = redis.from_url(settings.celery_broker_url, socket_connect_timeout=5)
        if not client.ping():
            return StepResult(
                step='redis_broker',
                ok=False,
                message='PING 未返回真值',
                hint='检查 Redis 是否启动（如 docker compose up -d）与 CELERY_BROKER_URL',
            )
        return StepResult(
            step='redis_broker',
            ok=True,
            message='Redis broker 连通正常',
            detail={'url_tail': settings.celery_broker_url.split('@')[-1]},
        )
    except Exception as exc:
        return StepResult(
            step='redis_broker',
            ok=False,
            message=f'Redis 不可用: {exc}',
            hint='启动 Redis；核对 .env 中 CELERY_BROKER_URL',
            detail={'exc_type': type(exc).__name__},
        )


def step_celery_worker() -> StepResult:
    try:
        from app.tasks.worker import celery_app

        insp = celery_app.control.inspect(timeout=3.0)
        pong = insp.ping() if insp else None
        if not pong:
            return StepResult(
                step='celery_worker',
                ok=False,
                message='未发现在线 Celery Worker（inspect.ping 无响应）',
                hint='在项目根执行: celery -A app.tasks.worker.celery_app worker -l info（Windows 已默认 solo）',
            )
        return StepResult(
            step='celery_worker',
            ok=True,
            message='至少有一个 Worker 响应 ping',
            detail={'workers': list(pong.keys())},
        )
    except Exception as exc:
        return StepResult(
            step='celery_worker',
            ok=False,
            message=f'检查 Celery Worker 失败: {exc}',
            hint='确认 Redis 正常且与 Worker 使用同一 .env；Windows 勿用 prefork',
            detail={'exc_type': type(exc).__name__},
        )


def step_dify_api_key(timeout_sec: int) -> StepResult:
    try:
        from app.core.config import settings
        from app.services.dify_service import DifyWorkflowError, run_workflow_blocking

        if not settings.dify_api_key or not settings.dify_api_key.strip():
            return StepResult(
                step='dify_api_key',
                ok=False,
                message='未配置 DIFY_API_KEY',
                hint='在 .env 中设置 Dify 应用的 API Key，并与 DIFY_BASE_URL 同属一个环境',
            )
        text_key = settings.dify_workflow_input_text_key
        run_workflow_blocking(
            inputs={text_key: 'E2E 探针文本（可忽略）'},
            user='e2e_pipeline',
            timeout_sec=timeout_sec,
        )
        return StepResult(
            step='dify_api_key',
            ok=True,
            message='Dify /workflows/run 调用成功（鉴权通过）',
            detail={'base_url': settings.dify_base_url},
        )
    except DifyWorkflowError as exc:
        err = str(exc)
        hint = '若含 401 / Access token invalid：在 Dify 控制台重新生成 API Key 并更新 .env，重启 Worker'
        if '401' in err or 'unauthorized' in err.lower():
            hint = 'Dify 返回未授权：请核对 DIFY_API_KEY 与 DIFY_BASE_URL（云与自建勿混用），轮换 Key 后重启 Celery'
        return StepResult(
            step='dify_api_key',
            ok=False,
            message=err[:800],
            hint=hint,
        )
    except Exception as exc:
        return StepResult(
            step='dify_api_key',
            ok=False,
            message=f'Dify 探针异常: {exc}',
            hint='查看完整日志；核对网络与 DIFY_BASE_URL',
            detail={'exc_type': type(exc).__name__},
        )


def step_fastapi_health(base: str) -> StepResult:
    for path in ('/healthz', '/api/v1/healthz'):
        try:
            status, body = _http_request(base, 'GET', path, timeout=15.0)
            if status != 200:
                return StepResult(
                    step='fastapi_health',
                    ok=False,
                    message=f'{path} 返回 HTTP {status}',
                    hint='确认 uvicorn 已启动: python -m uvicorn main:app --reload',
                    detail={'path': path, 'status': status, 'body_preview': str(body)[:400]},
                )
            payload = _normalize_maybe_envelope(body)
            if payload.get('status') != 'ok':
                return StepResult(
                    step='fastapi_health',
                    ok=False,
                    message=f'{path} 解包后 status 非 ok',
                    detail={'path': path, 'payload': payload},
                )
        except ConnectionError as exc:
            return StepResult(
                step='fastapi_health',
                ok=False,
                message=str(exc),
                hint='启动 FastAPI：cd 到项目根后 python -m uvicorn main:app --host 127.0.0.1 --port 8000',
                detail={'tried': path},
            )
    return StepResult(
        step='fastapi_health',
        ok=True,
        message='/healthz 与 /api/v1/healthz 均正常',
        detail={'base_url': base},
    )


def step_login(base: str, identifier: str, password: str) -> tuple[StepResult, str | None]:
    try:
        payload = json.dumps(
            {'identifier': identifier, 'password': password},
            ensure_ascii=False,
        ).encode('utf-8')
        status, body = _http_request(
            base,
            'POST',
            '/api/v1/auth/login',
            data=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30.0,
        )
        data = _unwrap_envelope(body, status, '登录')
        token = data.get('access_token') if isinstance(data, dict) else None
        if not token:
            return (
                StepResult(
                    step='auth_login',
                    ok=False,
                    message='登录响应缺少 data.access_token',
                    hint='检查信封结构；确认账号密码正确',
                    detail={'http_status': status},
                ),
                None,
            )
        return (
            StepResult(
                step='auth_login',
                ok=True,
                message='登录成功',
                detail={'expires_in': data.get('expires_in') if isinstance(data, dict) else None},
            ),
            str(token),
        )
    except RuntimeError as exc:
        return (
            StepResult(
                step='auth_login',
                ok=False,
                message=str(exc),
                hint='核对 E2E_IDENTIFIER / E2E_PASSWORD 或 BOOTSTRAP_ADMIN_*；确认账号已创建',
            ),
            None,
        )
    except ConnectionError as exc:
        return (
            StepResult(
                step='auth_login',
                ok=False,
                message=str(exc),
                hint='FastAPI 未监听或 BASE_URL 错误',
            ),
            None,
        )


def step_create_assessment(
    base: str,
    token: str,
    org_id: str,
    fixture_path: Path,
) -> StepResult:
    try:
        raw = fixture_path.read_bytes()
        fields: dict[str, str] = {}
        if org_id:
            fields['organization_id'] = org_id
        body, ctype = _multipart_body(
            fields,
            fixture_path.name,
            raw,
            'text/plain; charset=utf-8',
        )
        status, resp_body = _http_request(
            base,
            'POST',
            '/api/v1/assessment',
            data=body,
            headers={
                'Content-Type': ctype,
                'Authorization': f'Bearer {token}',
            },
            timeout=120.0,
        )
        if status == 503 and isinstance(resp_body, dict):
            code = resp_body.get('code', '')
            if code == 'TASK_ENQUEUE_FAILED':
                return StepResult(
                    step='create_assessment',
                    ok=False,
                    message=resp_body.get('message', '任务入队失败'),
                    hint='检查 Redis 与 Celery Worker；查看 details.reason',
                    detail=dict(resp_body),
                )
        data = _unwrap_envelope(resp_body, status, '创建评价任务')
        task_id = data.get('task_id') if isinstance(data, dict) else None
        if not task_id:
            return StepResult(
                step='create_assessment',
                ok=False,
                message='创建成功信封中缺少 task_id',
                detail={'data': data},
            )
        return StepResult(
            step='create_assessment',
            ok=True,
            message='已创建评价任务并入队',
            detail={'task_id': task_id, 'status': data.get('status') if isinstance(data, dict) else None},
        )
    except RuntimeError as exc:
        return StepResult(
            step='create_assessment',
            ok=False,
            message=str(exc),
            hint='403/401 多为 JWT 无效或未带 Authorization: Bearer',
        )
    except ConnectionError as exc:
        return StepResult(step='create_assessment', ok=False, message=str(exc))


def step_poll_task(
    base: str,
    token: str,
    task_id: str,
    timeout_sec: int,
    interval: float,
) -> StepResult:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        try:
            status, body = _http_request(
                base,
                'GET',
                f'/api/v1/assessment/{task_id}',
                headers={'Authorization': f'Bearer {token}'},
                timeout=30.0,
            )
            data = _unwrap_envelope(body, status, '查询任务详情')
            last = data if isinstance(data, dict) else {}
            st = str(last.get('status', ''))
            if st in ('SUCCESS', 'FAILED'):
                ok = st == 'SUCCESS'
                return StepResult(
                    step='poll_assessment',
                    ok=ok,
                    message=f'终态 {st}',
                    hint=''
                    if ok
                    else (last.get('error_message') or '见 error_message / Worker 日志'),
                    detail={
                        'status': st,
                        'progress': last.get('progress'),
                        'has_result_json': bool(last.get('result_json')),
                        'error_message': (last.get('error_message') or '')[:500],
                    },
                )
        except Exception as exc:
            return StepResult(
                step='poll_assessment',
                ok=False,
                message=f'轮询异常: {exc}',
                detail={'exc_type': type(exc).__name__},
            )
        time.sleep(interval)
    return StepResult(
        step='poll_assessment',
        ok=False,
        message=f'{timeout_sec}s 内未达到 SUCCESS/FAILED，最后状态: {last.get("status", "UNKNOWN")}',
        hint='若长期 PENDING：启动 Celery Worker；若 FAILED：查 error_message（如 Dify 401）',
        detail=last,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='EHS E2E 流水线自检')
    parser.add_argument(
        '--base-url',
        default=os.environ.get('E2E_BASE_URL', 'http://127.0.0.1:8000'),
        help='API 根地址',
    )
    parser.add_argument('--skip-redis', action='store_true')
    parser.add_argument('--skip-celery-ping', action='store_true')
    parser.add_argument('--skip-dify', action='store_true')
    parser.add_argument(
        '--continue-after-dify-failure',
        action='store_true',
        help='Dify 探针失败时仍继续登录与创建评价（默认会提前退出）',
    )
    parser.add_argument('--dify-timeout', type=int, default=90, help='Dify blocking 调用超时（秒）')
    parser.add_argument('--poll-timeout', type=int, default=180, help='等待任务终态超时（秒）')
    parser.add_argument('--poll-interval', type=float, default=3.0)
    parser.add_argument(
        '--fixture',
        type=Path,
        default=_ROOT / 'fixtures' / 'ehs' / 'sample_document_text.txt',
        help='上传用的样例文件',
    )
    parser.add_argument('--skip-assessment-flow', action='store_true', help='跳过登录与创建任务（仍做 health/redis 等）')
    args = parser.parse_args()

    steps: list[StepResult] = []

    steps.append(step_load_config())
    if not steps[-1].ok:
        print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
        return 1

    from app.core.config import settings

    identifier = os.environ.get('E2E_IDENTIFIER') or settings.bootstrap_admin_username
    password = os.environ.get('E2E_PASSWORD') or settings.bootstrap_admin_password

    if not args.skip_redis:
        steps.append(step_redis())
    if not args.skip_celery_ping:
        steps.append(step_celery_worker())
    if not args.skip_dify:
        steps.append(step_dify_api_key(args.dify_timeout))
        if not steps[-1].ok and not args.continue_after_dify_failure:
            print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
            print(
                '[e2e] Dify 探针未通过，已中止后续步骤。'
                '修正 DIFY_API_KEY / DIFY_BASE_URL 后重试；'
                '或加 --continue-after-dify-failure 仅测 API。',
                file=sys.stderr,
            )
            return 1

    steps.append(step_fastapi_health(args.base_url))

    if args.skip_assessment_flow:
        print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
        return 0 if all(s.ok for s in steps) else 1

    if not identifier or not password:
        steps.append(
            StepResult(
                step='auth_login',
                ok=False,
                message='缺少登录凭证',
                hint='设置 E2E_IDENTIFIER / E2E_PASSWORD，或在 .env 配置 BOOTSTRAP_ADMIN_PASSWORD',
            )
        )
        print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
        return 1

    login_result, token = step_login(args.base_url, identifier, password)
    steps.append(login_result)
    if not login_result.ok or not token:
        print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
        return 1

    if not args.fixture.is_file():
        steps.append(
            StepResult(
                step='create_assessment',
                ok=False,
                message=f'样例文件不存在: {args.fixture}',
                hint='指定 --fixture 或添加 fixtures/ehs/sample_document_text.txt',
            )
        )
        print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
        return 1

    org_id = settings.default_organization_id
    create_res = step_create_assessment(args.base_url, token, org_id, args.fixture)
    steps.append(create_res)
    if not create_res.ok or not create_res.detail.get('task_id'):
        print(json.dumps(_as_report(steps), ensure_ascii=False, indent=2))
        return 1

    task_id = str(create_res.detail['task_id'])
    steps.append(
        step_poll_task(
            args.base_url,
            token,
            task_id,
            args.poll_timeout,
            args.poll_interval,
        )
    )

    report = _as_report(steps)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['overall_ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
