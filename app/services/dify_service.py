"""调用 Dify Workflow API（阻塞模式），将输出解析为 EHS 结构化结果。"""

from __future__ import annotations

import json
import random
import re
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.core.request_context import TRACEPARENT_HEADER, get_traceparent
from app.schemas.ehs_schema import EHSAssessmentResult

_log = get_logger(__name__)

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class DifyWorkflowError(Exception):
    """Dify 调用失败或返回无法解析。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.attempts = attempts


def _base_url() -> str:
    return settings.dify_base_url.rstrip('/')


def _retry_delay_seconds(attempt: int) -> float:
    base = settings.dify_retry_initial_delay_seconds * (2 ** max(attempt - 1, 0))
    capped = min(base, settings.dify_retry_max_delay_seconds)
    jitter = random.uniform(0, settings.dify_retry_jitter_seconds)
    return min(capped + jitter, settings.dify_retry_max_delay_seconds)


def _build_headers() -> dict[str, str]:
    headers = {
        'Authorization': f'Bearer {settings.dify_api_key}',
        'Content-Type': 'application/json',
        'User-Agent': settings.http_user_agent,
    }
    traceparent = get_traceparent()
    if traceparent:
        headers[TRACEPARENT_HEADER] = traceparent
    return headers


def run_workflow_blocking(
    *,
    inputs: dict[str, Any],
    user: str,
    timeout_sec: int = 600,
) -> dict[str, Any]:
    """
    POST /workflows/run ，response_mode=blocking。
    返回体顶层含 task_id、workflow_run_id、data（含 outputs）。
    """
    if not settings.dify_api_key:
        raise DifyWorkflowError('未配置 DIFY_API_KEY')
    url = f'{_base_url()}/workflows/run'
    payload = {
        'inputs': inputs,
        'response_mode': 'blocking',
        'user': user,
    }
    headers = _build_headers()
    max_attempts = settings.dify_retry_max_attempts
    started = time.perf_counter()

    for attempt in range(1, max_attempts + 1):
        attempt_started = time.perf_counter()
        try:
            with httpx.Client(timeout=timeout_sec) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                break
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            retryable = status_code in _RETRYABLE_STATUS_CODES
            elapsed_ms = int((time.perf_counter() - attempt_started) * 1000)
            err_body = exc.response.text
            _log.warning(
                'Dify workflow HTTP error status=%s attempt=%s max_attempts=%s retryable=%s '
                'elapsed_ms=%s body=%s',
                status_code,
                attempt,
                max_attempts,
                retryable,
                elapsed_ms,
                err_body[:2000],
            )
            if not retryable or attempt >= max_attempts:
                raise DifyWorkflowError(
                    f'Dify 请求失败 HTTP {status_code}: {err_body[:500]}',
                    retryable=retryable,
                    status_code=status_code,
                    attempts=attempt,
                ) from exc
        except httpx.TimeoutException as exc:
            retryable = settings.dify_retry_on_timeout
            elapsed_ms = int((time.perf_counter() - attempt_started) * 1000)
            _log.warning(
                'Dify workflow timeout timeout_sec=%s attempt=%s max_attempts=%s retryable=%s '
                'elapsed_ms=%s',
                timeout_sec,
                attempt,
                max_attempts,
                retryable,
                elapsed_ms,
            )
            if not retryable or attempt >= max_attempts:
                raise DifyWorkflowError(
                    f'Dify 请求超时: {timeout_sec}s',
                    retryable=retryable,
                    attempts=attempt,
                ) from exc
        except httpx.RequestError as exc:
            elapsed_ms = int((time.perf_counter() - attempt_started) * 1000)
            _log.warning(
                'Dify workflow network error attempt=%s max_attempts=%s retryable=true '
                'elapsed_ms=%s error=%s',
                attempt,
                max_attempts,
                elapsed_ms,
                exc,
            )
            if attempt >= max_attempts:
                raise DifyWorkflowError(
                    f'Dify 网络错误: {exc}',
                    retryable=True,
                    attempts=attempt,
                ) from exc

        delay = _retry_delay_seconds(attempt)
        _log.info(
            'Dify workflow retry scheduled attempt=%s next_attempt=%s max_attempts=%s delay_sec=%.2f',
            attempt,
            attempt + 1,
            max_attempts,
            delay,
        )
        time.sleep(delay)
    else:
        raise DifyWorkflowError('Dify 请求失败：重试次数已耗尽', retryable=True, attempts=max_attempts)

    try:
        payload = resp.json()
    except json.JSONDecodeError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _log.warning('Dify workflow returned non-json elapsed_ms=%s body=%s', elapsed_ms, resp.text[:500])
        raise DifyWorkflowError(f'Dify 返回非 JSON: {resp.text[:500]}') from exc

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    data = payload.get('data') if isinstance(payload, dict) else {}
    _log.info(
        'Dify workflow completed elapsed_ms=%s attempts=%s task_id=%s workflow_run_id=%s status=%s',
        elapsed_ms,
        attempt,
        payload.get('task_id') if isinstance(payload, dict) else None,
        payload.get('workflow_run_id') if isinstance(payload, dict) else None,
        data.get('status') if isinstance(data, dict) else None,
    )
    return payload


def _strip_code_fence(text: str) -> str:
    s = text.strip()
    if not s.startswith('```'):
        return s
    lines = s.split('\n')
    if lines and lines[0].lstrip().startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    return '\n'.join(lines).strip()


def _extract_balanced_json_object(s: str) -> str | None:
    """从任意文本中截取第一个花括号匹配的 JSON 对象子串。"""
    i = s.find('{')
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(s)):
        c = s[j]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return s[i : j + 1]
    return None


def _json_loads_tolerant(blob: str) -> Any | None:
    """多策略 JSON 反序列化（LLM 输出常见问题：围栏、前后杂质、仅截取 `{...}`）。"""
    s = blob.strip().lstrip('\ufeff')
    if not s:
        return None
    s = _strip_code_fence(s)
    candidates: list[str] = [s]
    ext = _extract_balanced_json_object(s)
    if ext and ext not in candidates:
        candidates.append(ext)
    # 弱匹配：含 risks 与 summary 的大括号块
    m = re.search(r'\{[\s\S]*?"risks"[\s\S]*?"summary"[\s\S]*\}', s)
    if m:
        seg = m.group(0)
        if seg not in candidates:
            candidates.append(seg)

    for c in candidates:
        if not c.strip():
            continue
        try:
            return json.loads(c)
        except json.JSONDecodeError:
            continue
    return None


def _unwrap_nested_ehs(data: dict[str, Any]) -> dict[str, Any] | None:
    if 'risks' in data and 'summary' in data:
        return data
    for v in data.values():
        if isinstance(v, dict) and 'risks' in v and 'summary' in v:
            return v
        if isinstance(v, str):
            inner = _parse_jsonish_to_dict(v)
            if inner:
                return inner
    return None


def _parse_jsonish_to_dict(raw: Any) -> dict[str, Any] | None:
    """将 Dify 输出变量（字符串 / dict）尽量还原为内含 risks、summary 的 dict。"""
    data: Any = None
    if isinstance(raw, dict):
        data = raw
    elif isinstance(raw, str):
        parsed = _json_loads_tolerant(raw)
        if parsed is None:
            return None
        data = parsed
        # 双（多）重字符串化："{\"risks\": ...}" 解一层后仍是 JSON 串
        for _ in range(4):
            if isinstance(data, str):
                nxt = _json_loads_tolerant(data)
                if nxt is None:
                    break
                data = nxt
            else:
                break
    elif isinstance(raw, list) and len(raw) == 1:
        return _parse_jsonish_to_dict(raw[0])
    else:
        return None

    if not isinstance(data, dict):
        return None

    got = _unwrap_nested_ehs(data)
    return got


def _coerce_ehs_dict(outputs: dict[str, Any]) -> dict[str, Any]:
    """从 data.outputs 得到可喂给 EHSAssessmentResult 的 dict。"""
    if not outputs:
        raise DifyWorkflowError('工作流 outputs 为空')

    if 'risks' in outputs and 'summary' in outputs:
        return outputs

    key = settings.dify_workflow_result_key
    candidates: list[Any] = []
    if key in outputs:
        candidates.append(outputs[key])
    for alt in ('result', 'result_json', 'output', 'structured_json', 'ehs_result', 'answer'):
        if alt in outputs and outputs[alt] not in candidates:
            candidates.append(outputs[alt])

    for raw in candidates:
        parsed = _parse_jsonish_to_dict(raw)
        if parsed:
            return parsed

    for v in outputs.values():
        parsed = _parse_jsonish_to_dict(v)
        if parsed:
            return parsed

    preview = ''
    if key in outputs:
        p = outputs[key]
        preview = (str(p)[:300] + '…') if p is not None and len(str(p)) > 300 else str(p)

    raise DifyWorkflowError(
        '无法从工作流输出解析 EHS 结构（需要包含 risks、summary；'
        f'或配置 DIFY_WORKFLOW_RESULT_KEY 指向含 JSON 的输出变量）。当前 keys: {list(outputs.keys())}'
        + (f'；{key} 内容预览: {preview!r}' if preview else '')
    )


def fetch_assessment_result(
    *,
    document_text: str,
    filename: str,
    task_id: str,
) -> EHSAssessmentResult:
    """
    调用 Dify 工作流并得到 EHSAssessmentResult。

    默认向工作流传入 inputs:
      - document_text / query（与 Dify 画布中「开始」变量名一致即可，见下）
      - filename

    若你的应用开始节点变量名不是 document_text，请在 .env 设置
    DIFY_WORKFLOW_INPUT_TEXT_KEY（例如 query）。
    """
    text_key = settings.dify_workflow_input_text_key
    inputs: dict[str, Any] = {
        text_key: document_text,
        'filename': filename,
    }
    user = f'ehs-task-{task_id}'
    _log.info('调用 Dify workflow user=%s inputs_keys=%s', user, list(inputs.keys()))
    resp = run_workflow_blocking(inputs=inputs, user=user)
    data = resp.get('data') or {}
    if data.get('status') not in (None, 'succeeded'):
        err = data.get('error') or data
        raise DifyWorkflowError(f'工作流未成功: {err}')
    outputs = data.get('outputs') or {}

    # 检查知识库检索是否命中（Dify 会在 metadata 中返回检索信息）
    retrieval_info = data.get('metadata', {}).get('retriever_resources')
    if not retrieval_info:
        _log.warning(
            '知识库检索未命中任何文档 task_id=%s filename=%s，LLM 将在无参考资料下生成结果',
            task_id, filename,
        )

    payload = _coerce_ehs_dict(outputs)
    try:
        return EHSAssessmentResult.model_validate(payload)
    except Exception as exc:
        raise DifyWorkflowError(f'EHS 结果校验失败: {exc}；payload 摘要: {str(payload)[:400]}') from exc
