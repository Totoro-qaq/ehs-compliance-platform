from __future__ import annotations

import json
import time
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.core.logging_setup import get_logger
from app.dao.agent_dao import AgentMessageDAO, AgentRunDAO, AgentSessionDAO, AgentToolCallDAO
from app.models.db_models import (
    AgentMessageRole,
    AgentRunStatus,
    ComplianceStatus,
    ReportStatus,
    TaskStatus,
)
from app.schemas.agent_schema import AgentChatResponse
from app.schemas.auth_context import CurrentUser
from app.schemas.pagination import Page
from app.services.agent_tools import AgentToolResult, AgentTools

_logger = get_logger(__name__)

_SYSTEM_PROMPT = """你是 EHS 合规管理平台的企业内助手。
你只能基于后端工具提供的数据回答，不允许编造任务、报告、标准或法规条款。
当前阶段你只能做只读分析，不能声称已经创建、删除、修改或重跑任何业务数据。
如果数据不足，请说明需要用户进入对应页面复核。
回答使用中文，结构清晰，优先给出可执行的下一步建议。"""

_FAST_SUMMARY_TOOLS = {
    'get_workbench_summary',
    'get_client_project_context',
    'list_assessment_tasks',
    'list_detection_reports',
    'summarize_detection_compliance',
    'search_regulatory_limits',
}

_STATUS_OR_LOOKUP_INTENT_KEYWORDS = (
    '总结',
    '概览',
    '工作台',
    '待办',
    '待处理',
    '失败',
    '异常',
    '报错',
    '没判定',
    '未判定',
    '待判定',
    '哪些',
    '什么',
    '多少',
    '几个',
    '列表',
    '清单',
    '最近',
    '当前',
    '今天',
    '进度',
    '状态',
    '下一步',
    '限值',
    '法规',
    '标准',
    '条款',
    'cas',
)

_OPEN_ENDED_MODEL_KEYWORDS = (
    '解释',
    '为什么',
    '原因',
    '分析原因',
    '整改思路',
    '整改方案',
    '方案',
    '生成',
    '撰写',
    '起草',
    '帮我写',
    '写一份',
)

_LIGHTWEIGHT_PROMPTS = {
    '你好',
    '您好',
    '你好啊',
    '您好啊',
    '嗨',
    '哈喽',
    'hello',
    'hi',
    '在吗',
    '在不在',
}

_STATUS_LABELS = {
    TaskStatus.PENDING.value: '待处理',
    TaskStatus.PARSING.value: '解析中',
    TaskStatus.AI_ANALYZING.value: 'AI 分析中',
    TaskStatus.VALIDATING.value: '校验中',
    TaskStatus.PERSISTING.value: '保存中',
    TaskStatus.SUCCESS.value: '成功',
    TaskStatus.FAILED.value: '失败',
    ReportStatus.UPLOADED.value: '已上传',
    ReportStatus.PARSED.value: '已解析',
    ReportStatus.VALIDATED.value: '已校验',
    ReportStatus.CALCULATED.value: '已判定',
    ReportStatus.FAILED.value: '失败',
    ComplianceStatus.COMPLIANT.value: '合规',
    ComplianceStatus.EXCEEDED.value: '超标',
    ComplianceStatus.BORDERLINE.value: '临界',
    ComplianceStatus.INSUFFICIENT_DATA.value: '数据不足',
    ComplianceStatus.NEEDS_REVIEW.value: '需复核',
    'PENDING_CALCULATION': '待判定',
}


def _title_from_content(content: str) -> str:
    cleaned = ' '.join(content.strip().split())
    if not cleaned:
        return '新的 Agent 会话'
    return cleaned[:40]


def _json_text(value: Any, *, limit: int = 16000) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return f'{text[:limit]}...(已截断)'


def _first_tool(tool_results: list[AgentToolResult], name: str) -> dict[str, Any] | None:
    for item in tool_results:
        if item.tool_name == name:
            return item.result
    return None


def _should_use_fast_summary(content: str, tool_results: list[AgentToolResult]) -> bool:
    tool_names = {item.tool_name for item in tool_results}
    if not tool_names or not tool_names.issubset(_FAST_SUMMARY_TOOLS):
        return False

    normalized = content.lower()
    has_status_or_lookup_intent = any(
        keyword in normalized for keyword in _STATUS_OR_LOOKUP_INTENT_KEYWORDS
    )
    has_open_ended_intent = any(keyword in normalized for keyword in _OPEN_ENDED_MODEL_KEYWORDS)

    if has_status_or_lookup_intent:
        return True

    # AgentTools defaults unknown short prompts to workbench summary. Keep those instant unless
    # the user clearly asks for generative reasoning.
    return 'get_workbench_summary' in tool_names and not has_open_ended_intent


def _compact_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _static_reply_for_lightweight_prompt(content: str) -> str | None:
    compact = _compact_text(content)
    normalized = compact.lower().replace(' ', '')
    if not normalized:
        return None

    punctuation = set('?.？！!。.…~～、，,;；:：')
    is_punctuation_only = all(char in punctuation for char in normalized)
    if normalized not in _LIGHTWEIGHT_PROMPTS and not is_punctuation_only:
        return None

    return (
        '你好，我可以按当前账号权限读取工作台、评价任务、检测报告和限值库摘要。'
        '你可以直接问：总结当前工作台、最近失败的任务是什么、检测报告还有哪些没判定。'
    )


def _status_label(status: str | None) -> str:
    return _STATUS_LABELS.get(status or '', status or '-')


def _record_context(item: dict[str, Any] | None) -> str:
    if not item:
        return ''
    parts = []
    if item.get('client_name'):
        parts.append(f'客户：{_compact_text(item.get("client_name"))}')
    if item.get('project_name'):
        parts.append(f'项目：{_compact_text(item.get("project_name"))}')
    if item.get('project_code'):
        parts.append(f'编号：{_compact_text(item.get("project_code"))}')
    if item.get('service_type'):
        parts.append(f'服务：{_compact_text(item.get("service_type"))}')
    return '；'.join(parts)


def _format_record(
    title: str | None,
    status: str | None,
    error: str | None = None,
    context: str | None = None,
) -> str:
    context_suffix = f'，{context}' if context else ''
    suffix = f'，错误：{error}' if error else ''
    return f'{title or "-"}（{_status_label(status)}{context_suffix}{suffix}）'


def _format_value_unit(value: Any, unit: Any = None) -> str:
    if value is None or value == '':
        return '-'
    return f'{value}{unit or ""}'


def _sanitize_failure_error(error: str | None) -> str:
    text = _compact_text(error)
    if not text:
        return '处理失败，需查看任务详情'

    lowered = text.lower()
    if (
        '无法从工作流输出解析 ehs 结构' in lowered
        or 'dify_workflow_result_key' in lowered
        or 'result_json' in lowered
        or '需要包含 risks' in lowered
        or 'keys:' in lowered
    ):
        return 'AI 工作流返回格式不符合系统要求，需要检查工作流输出配置'

    if (
        'dify 请求失败 http 400' in lowered
        or 'invalid_param' in lowered
        or 'document_text' in lowered
        or 'input form must be less than' in lowered
    ):
        return 'AI 工作流参数校验失败，需要检查输入长度或工作流表单配置'

    if 'timeout' in lowered or 'readtimeout' in lowered or 'timed out' in lowered:
        return 'AI 工作流响应超时，需要稍后重试或检查服务状态'

    if 'connection' in lowered or 'connecterror' in lowered or 'http' in lowered:
        return '外部工作流调用失败，需要检查服务连接和工作流状态'

    return '处理失败，需查看任务详情'


def _failed_record_title(item: dict[str, Any], kind: str) -> str:
    if kind == '评价':
        return _compact_text(item.get('task_name') or item.get('filename')) or '-'
    return _compact_text(item.get('report_name') or item.get('filename')) or '-'


def _dedupe_failed_records(*, kind: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in items:
        title = _failed_record_title(item, kind)
        status = _compact_text(item.get('status')) or '-'
        error = _sanitize_failure_error(item.get('error_message'))
        context = _record_context(item)
        key = (kind, title.lower(), status, error, context)
        if key not in seen:
            seen[key] = {
                'kind': kind,
                'title': title,
                'status': status,
                'error': error,
                'context': context,
                'count': 0,
            }
            records.append(seen[key])
        seen[key]['count'] += 1
    return records


class AgentService:
    @staticmethod
    def create_session(*, db: Session, actor: CurrentUser, title: str | None = None):
        session_title = _title_from_content(title or '新的 Agent 会话')
        return AgentSessionDAO(db).create_session(
            account_id=actor.account_id,
            organization_id=actor.organization_id,
            title=session_title,
        )

    @staticmethod
    def list_sessions(*, db: Session, actor: CurrentUser, page: int, page_size: int):
        items, total = AgentSessionDAO(db).list_owned(
            account_id=actor.account_id,
            page=page,
            page_size=page_size,
        )
        return Page(items=items, total=total, page=page, page_size=page_size)

    @staticmethod
    def list_messages(*, db: Session, actor: CurrentUser, session_id: str):
        session = AgentSessionDAO(db).get_owned(session_id=session_id, account_id=actor.account_id)
        if session is None:
            raise EHSException('Agent 会话不存在', code='AGENT_SESSION_NOT_FOUND', status_code=404)
        return AgentMessageDAO(db).list_for_session(session.id, limit=100)

    @staticmethod
    async def chat(
        *,
        db: Session,
        actor: CurrentUser,
        content: str,
        session_id: str | None = None,
    ) -> AgentChatResponse:
        chat_started = time.perf_counter()
        session_dao = AgentSessionDAO(db)
        message_dao = AgentMessageDAO(db)
        run_dao = AgentRunDAO(db)
        tool_call_dao = AgentToolCallDAO(db)

        if session_id:
            session = session_dao.get_owned(session_id=session_id, account_id=actor.account_id)
            if session is None:
                raise EHSException(
                    'Agent 会话不存在',
                    code='AGENT_SESSION_NOT_FOUND',
                    status_code=404,
                )
        else:
            session = session_dao.create_session(
                account_id=actor.account_id,
                organization_id=actor.organization_id,
                title=_title_from_content(content),
            )

        user_message = message_dao.add_message(
            session_id=session.id,
            role=AgentMessageRole.USER,
            content=content.strip(),
        )
        session = session_dao.touch(session, title=session.title or _title_from_content(content))

        provider = settings.agent_llm_provider.strip().lower() or 'ollama'
        model_name = settings.ollama_chat_model
        run = run_dao.create_run(
            session_id=session.id,
            account_id=actor.account_id,
            organization_id=actor.organization_id,
            user_message_id=user_message.id,
            provider=provider,
            model_name=model_name,
        )

        degraded = False
        llm_error: str | None = None
        static_answer = _static_reply_for_lightweight_prompt(content)
        if static_answer:
            run.provider = 'rules'
            run.model_name = 'static-reply'
            answer = static_answer
            tool_results: list[AgentToolResult] = []
            tool_names: list[str] = []
            fast_summary = False
            _logger.info(
                'agent.chat route=static_reply run_id=%s session_id=%s content_len=%s',
                run.id,
                session.id,
                len(content),
            )
        else:
            tool_results = AgentService._execute_tools(
                db=db,
                actor=actor,
                run_id=run.id,
                session_id=session.id,
                content=content,
                tool_call_dao=tool_call_dao,
            )

            fast_summary = _should_use_fast_summary(content, tool_results)
            tool_names = [item.tool_name for item in tool_results]
            if fast_summary:
                _logger.info(
                    'agent.chat route=fast_summary run_id=%s session_id=%s tools=%s content_len=%s',
                    run.id,
                    session.id,
                    tool_names,
                    len(content),
                )
                run.provider = 'rules'
                run.model_name = 'fast-summary'
                answer = AgentService._fallback_answer(
                    content=content,
                    tool_results=tool_results,
                    error_message=None,
                )
            else:
                try:
                    _logger.info(
                        'agent.chat route=model run_id=%s session_id=%s provider=%s model=%s tools=%s timeout=%ss content_len=%s',
                        run.id,
                        session.id,
                        run.provider,
                        run.model_name,
                        tool_names,
                        settings.agent_request_timeout_seconds,
                        len(content),
                    )
                    answer = await AgentService._call_model(
                        db=db,
                        session_id=session.id,
                        content=content,
                        tool_results=tool_results,
                    )
                except Exception as exc:
                    degraded = True
                    llm_error = f'{type(exc).__name__}: {exc}'
                    run.provider = 'fallback'
                    run.model_name = 'rules'
                    answer = AgentService._fallback_answer(
                        content=content,
                        tool_results=tool_results,
                        error_message=llm_error,
                    )

        assistant_message = message_dao.add_message(
            session_id=session.id,
            role=AgentMessageRole.ASSISTANT,
            content=answer,
            metadata={
                'degraded': degraded,
                'provider': run.provider,
                'model_name': run.model_name,
                'fast_summary': fast_summary,
                'static_reply': static_answer is not None,
                'tool_names': tool_names,
                'llm_error': llm_error,
            },
        )
        run = run_dao.finish_run(
            run,
            status=AgentRunStatus.SUCCEEDED,
            assistant_message_id=assistant_message.id,
            error_message=llm_error,
        )
        session = session_dao.touch(session)
        tool_calls = tool_call_dao.list_for_run(run.id)
        elapsed_ms = int((time.perf_counter() - chat_started) * 1000)
        _logger.info(
            'agent.chat completed run_id=%s session_id=%s provider=%s model=%s fast_summary=%s degraded=%s elapsed_ms=%s tools=%s',
            run.id,
            session.id,
            run.provider,
            run.model_name,
            fast_summary,
            degraded,
            elapsed_ms,
            tool_names,
        )

        return AgentChatResponse(
            session=session,
            user_message=user_message,
            assistant_message=assistant_message,
            run=run,
            tool_calls=tool_calls,
            degraded=degraded,
        )

    @staticmethod
    def _execute_tools(
        *,
        db: Session,
        actor: CurrentUser,
        run_id: str,
        session_id: str,
        content: str,
        tool_call_dao: AgentToolCallDAO,
    ) -> list[AgentToolResult]:
        results: list[AgentToolResult] = []
        for tool_name, arguments in AgentTools.selected_tools(content):
            started = time.perf_counter()
            try:
                tool_result = AgentTools.run_tool(
                    db=db,
                    actor=actor,
                    tool_name=tool_name,
                    arguments=arguments,
                )
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                tool_call_dao.add_call(
                    run_id=run_id,
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=tool_result.result,
                    success=True,
                    elapsed_ms=elapsed_ms,
                )
                results.append(tool_result)
            except Exception as exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                tool_call_dao.add_call(
                    run_id=run_id,
                    session_id=session_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    result=None,
                    success=False,
                    elapsed_ms=elapsed_ms,
                    error_message=str(exc),
                )
                raise
        return results

    @staticmethod
    async def _call_model(
        *,
        db: Session,
        session_id: str,
        content: str,
        tool_results: list[AgentToolResult],
    ) -> str:
        if settings.agent_llm_provider.strip().lower() != 'ollama':
            raise EHSException(
                '当前 Agent LLM provider 暂未接入',
                code='AGENT_PROVIDER_NOT_SUPPORTED',
                status_code=503,
            )

        history = AgentMessageDAO(db).list_for_session(session_id, limit=12)
        messages: list[dict[str, str]] = [{'role': 'system', 'content': _SYSTEM_PROMPT}]
        for item in history[-10:]:
            if item.role == AgentMessageRole.USER:
                messages.append({'role': 'user', 'content': item.content[:3000]})
            elif item.role == AgentMessageRole.ASSISTANT:
                messages.append({'role': 'assistant', 'content': item.content[:3000]})

        tool_payload = {
            'user_question': content,
            'tool_results': [
                {
                    'tool_name': item.tool_name,
                    'arguments': item.arguments,
                    'result': item.result,
                }
                for item in tool_results
            ],
        }
        messages.append(
            {
                'role': 'user',
                'content': '后端只读工具返回的数据如下，请只基于这些数据回答：\n'
                + _json_text(tool_payload),
            }
        )

        base_url = settings.ollama_base_url.rstrip('/')
        payload = {
            'model': settings.ollama_chat_model,
            'messages': messages,
            'stream': False,
            'options': {
                'num_predict': 320,
                'temperature': 0.2,
            },
        }
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=settings.agent_request_timeout_seconds) as client:
            response = await client.post(f'{base_url}/api/chat', json=payload)
            response.raise_for_status()
            data = response.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _logger.info(
            'agent.ollama completed model=%s elapsed_ms=%s prompt_messages=%s',
            settings.ollama_chat_model,
            elapsed_ms,
            len(messages),
        )
        content_text = data.get('message', {}).get('content') or data.get('response')
        if not content_text:
            raise RuntimeError('Ollama 返回为空')
        return str(content_text).strip()

    @staticmethod
    def _fallback_answer(
        *,
        content: str,
        tool_results: list[AgentToolResult],
        error_message: str | None,
    ) -> str:
        lines: list[str] = []
        if error_message:
            lines.append('本次模型未响应，先使用后端规则摘要给你一个可操作结论。')

        summary = _first_tool(tool_results, 'get_workbench_summary')
        if summary:
            assessment = summary.get('assessment') or {}
            detection = summary.get('detection') or {}
            assessment_pending = int(assessment.get('active') or 0)
            detection_pending = int(detection.get('pending') or 0)
            failed_total = int(assessment.get('failed') or 0) + int(detection.get('failed') or 0)
            todo_total = assessment_pending + detection_pending + failed_total

            lines.extend(
                [
                    '当前账号可见范围内的工作台摘要：',
                    f'- 评价任务 {assessment.get("total", 0)} 个，成功 {assessment.get("success", 0)} 个，处理中 {assessment_pending} 个，失败 {assessment.get("failed", 0)} 个。',
                    f'- 检测报告 {detection.get("total", 0)} 个，已判定 {detection.get("calculated", 0)} 个，待判定 {detection_pending} 个，失败 {detection.get("failed", 0)} 个。',
                    f'- 当前需要关注的事项约 {todo_total} 个，其中失败异常 {failed_total} 个。',
                ]
            )

        context_summary = _first_tool(tool_results, 'get_client_project_context')
        if context_summary:
            terms = context_summary.get('terms') or []
            assessment_counts = context_summary.get('assessment_counts') or {}
            detection_counts = context_summary.get('detection_counts') or {}
            recent_assessments = context_summary.get('recent_assessments') or []
            recent_reports = context_summary.get('recent_reports') or []
            if terms or recent_assessments or recent_reports:
                lines.append(f'客户/项目上下文：{", ".join(terms) if terms else "已按问题筛选"}')
                lines.append(
                    '- 评价任务：'
                    f'共 {sum(int(value or 0) for value in assessment_counts.values())} 个，'
                    f'失败 {assessment_counts.get(TaskStatus.FAILED.value, 0)} 个，'
                    f'处理中 {sum(int(assessment_counts.get(status.value, 0) or 0) for status in (TaskStatus.PENDING, TaskStatus.PARSING, TaskStatus.AI_ANALYZING, TaskStatus.VALIDATING, TaskStatus.PERSISTING))} 个。'
                )
                lines.append(
                    '- 检测报告：'
                    f'共 {sum(int(value or 0) for value in detection_counts.values())} 个，'
                    f'待判定 {sum(int(detection_counts.get(status.value, 0) or 0) for status in (ReportStatus.UPLOADED, ReportStatus.PARSED, ReportStatus.VALIDATED))} 个，'
                    f'失败 {detection_counts.get(ReportStatus.FAILED.value, 0)} 个。'
                )
                if recent_assessments:
                    lines.append('相关评价任务：')
                    for item in recent_assessments[:3]:
                        lines.append(
                            f'- {_format_record(item.get("task_name") or item.get("filename"), item.get("status"), context=_record_context(item))}'
                        )
                if recent_reports:
                    lines.append('相关检测报告：')
                    for item in recent_reports[:3]:
                        lines.append(
                            f'- {_format_record(item.get("report_name") or item.get("filename"), item.get("status"), context=_record_context(item))}'
                        )

        failed_tasks = [
            item
            for result in tool_results
            if result.tool_name == 'list_assessment_tasks'
            and result.arguments.get('status') == TaskStatus.FAILED.value
            for item in result.result.get('items', [])
        ]
        failed_reports = [
            item
            for result in tool_results
            if result.tool_name == 'list_detection_reports'
            and result.arguments.get('status') == ReportStatus.FAILED.value
            for item in result.result.get('items', [])
        ]
        if failed_tasks or failed_reports:
            failed_records = [
                *_dedupe_failed_records(kind='评价', items=failed_tasks),
                *_dedupe_failed_records(kind='检测', items=failed_reports),
            ]
            lines.append('优先处理失败项：')
            for record in failed_records[:3]:
                same_kind_suffix = f'，同类 {record["count"]} 条' if record['count'] > 1 else ''
                lines.append(
                    f'- {record["kind"]}：'
                    f'{_format_record(record["title"], record["status"], record["error"], record["context"])}'
                    f'{same_kind_suffix}'
                )
            hidden_count = sum(record['count'] for record in failed_records[3:])
            if hidden_count:
                lines.append(f'- 另有 {hidden_count} 条失败项未展示，可进入对应模块按失败状态筛选。')

        compliance_summary = _first_tool(tool_results, 'summarize_detection_compliance')
        if compliance_summary:
            counts = compliance_summary.get('counts') or {}
            findings = compliance_summary.get('findings') or []
            total = int(counts.get('total') or 0)
            if total or findings:
                lines.append('检测判定结果：')
                lines.append(
                    f'- 覆盖已判定报告 {compliance_summary.get("report_count", 0)} 份，'
                    f'结果 {total} 条；超标 {counts.get("exceeded", 0)} 条，'
                    f'需复核 {counts.get("needs_review", 0)} 条，'
                    f'临界 {counts.get("borderline", 0)} 条，'
                    f'合规 {counts.get("compliant", 0)} 条。'
                )
                if findings:
                    lines.append('重点判定项：')
                    for item in findings[:5]:
                        place = ' / '.join(
                            part
                            for part in [
                                _compact_text(item.get('workplace')),
                                _compact_text(item.get('post_name')),
                                _compact_text(item.get('sample_point')),
                            ]
                            if part
                        )
                        basis = ' '.join(
                            part
                            for part in [
                                _compact_text(item.get('standard_code')),
                                _compact_text(item.get('clause')),
                            ]
                            if part
                        )
                        multiple = (
                            f'，超限倍数 {item.get("exceedance_multiple")}'
                            if item.get('exceedance_multiple')
                            else ''
                        )
                        lines.append(
                            f'- {item.get("indicator_name") or "-"}（{_status_label(item.get("status"))}）：'
                            f'{_format_value_unit(item.get("calculated_value"), item.get("calculated_unit"))}，'
                            f'限值 {_format_value_unit(item.get("limit_value"), item.get("limit_unit"))}'
                            f'{multiple}；{item.get("report_name") or item.get("filename") or "-"}'
                            f'{f"；{place}" if place else ""}'
                            f'{f"；依据 {basis}" if basis else ""}'
                            f'{f"；{_record_context(item)}" if _record_context(item) else ""}'
                        )

        detection_list = _first_tool(tool_results, 'list_detection_reports')
        if detection_list and not failed_reports:
            items = detection_list.get('items') or []
            if items:
                lines.append('最近检测报告：')
                for item in items[:5]:
                    formatted = _format_record(
                        item.get('report_name') or item.get('filename'),
                        item.get('status'),
                        context=_record_context(item),
                    )
                    lines.append(f'- {formatted}')

        assessment_list = _first_tool(tool_results, 'list_assessment_tasks')
        if assessment_list and not failed_tasks:
            items = assessment_list.get('items') or []
            if items:
                lines.append('最近评价任务：')
                for item in items[:5]:
                    formatted = _format_record(
                        item.get('task_name') or item.get('filename'),
                        item.get('status'),
                        context=_record_context(item),
                    )
                    lines.append(f'- {formatted}')

        limits = _first_tool(tool_results, 'search_regulatory_limits')
        if limits:
            items = limits.get('items') or []
            if items:
                lines.append('限值库命中：')
                for item in items[:5]:
                    limit_text = item.get('limit_value') or '/'.join(
                        value for value in [item.get('limit_min'), item.get('limit_max')] if value
                    )
                    lines.append(
                        f'- {item.get("indicator_name")} {item.get("limit_type")} {limit_text or "-"} {item.get("unit") or ""}，{item.get("standard_code")}'
                    )
            else:
                lines.append('限值库没有命中明确结果，建议进入检测合规页的限值库标签精确查询。')

        if not lines:
            lines.append('我已经收到你的问题，但当前没有查到足够的业务数据。建议先进入评价任务或检测合规页面确认数据是否已上传。')

        if '整改' in content or '建议' in content:
            lines.append('建议动作：先处理失败任务，再处理待判定检测报告；涉及法规结论时需要人工复核依据条款。')
        else:
            lines.append('下一步建议：进入工作台对应模块查看详情，失败项优先复核错误信息，待判定报告优先运行限值判定。')

        return '\n'.join(lines)
