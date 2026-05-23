from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import EHSException
from app.models.db_models import (
    AccountRole,
    AssessmentTask,
    ComplianceResult,
    ComplianceStatus,
    DetectionMeasurement,
    DetectionReport,
    DetectionSample,
    RegulatoryLimit,
    ReportStatus,
    ReportType,
    TaskStatus,
)
from app.schemas.auth_context import CurrentUser
from app.services.access_control import ensure_organization_scope, ensure_user_has_organization


@dataclass(frozen=True)
class AgentToolResult:
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


_CONTEXT_CLEANUP_PATTERN = re.compile(
    r'(的|还有|有哪些|哪些|有什么|什么|检测报告|评价任务|报告|任务|失败|异常|报错|待判定|未判定|没判定|'
    r'情况|状态|进度|怎么|如何|吗|呢|请|帮我|看一下|看看|总结|概览|,|，|。|？|\?)'
)


def _safe_limit(value: int, *, default: int = 5, maximum: int = 20) -> int:
    if value <= 0:
        return default
    return min(value, maximum)


def _dt(value: datetime | date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _enum(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, 'value', str(value))


def _short(value: str | None, length: int = 220) -> str | None:
    if not value:
        return value
    cleaned = value.strip()
    return cleaned if len(cleaned) <= length else f'{cleaned[:length]}...'


def _json_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _client_project_fields(item: AssessmentTask | DetectionReport) -> dict[str, str | None]:
    return {
        'client_name': item.client_name,
        'project_name': item.project_name,
        'project_code': item.project_code,
        'service_type': item.service_type,
    }


def _actor_org_filter(actor: CurrentUser, model) -> list[Any]:
    if actor.role == AccountRole.ADMIN:
        return []
    return [model.organization_id == ensure_user_has_organization(actor)]


def _clean_context_term(value: str) -> str | None:
    cleaned = _CONTEXT_CLEANUP_PATTERN.split(value.strip())[0].strip(' ：:，,。.;；（）()[]【】"\'')
    if len(cleaned) < 2:
        return None
    return cleaned[:80]


def _context_terms(user_text: str | None) -> list[str]:
    text = ' '.join((user_text or '').strip().split())
    if not text:
        return []

    terms: list[str] = []
    quoted = re.findall(r'[“"「『](.+?)[”"」』]', text)
    terms.extend(item for item in quoted if item.strip())

    patterns = [
        r'(?:委托单位|委托客户|客户|公司)[:：\s]*([\w\-\u4e00-\u9fff（）()·]+)',
        r'(?:项目名称|项目)[:：\s]*([\w\-\u4e00-\u9fff（）()·]+)',
        r'(?:项目编号|编号|报告编号)[:：\s]*([A-Za-z0-9_\-]+)',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text):
            terms.append(match)

    cleaned_terms: list[str] = []
    seen: set[str] = set()
    for raw in terms:
        cleaned = _clean_context_term(raw)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            cleaned_terms.append(cleaned)
    return cleaned_terms[:5]


def _context_filter(model, context_query: str | None):
    terms = _context_terms(context_query)
    if not terms:
        return None
    columns = [
        model.client_name,
        model.project_name,
        model.project_code,
        model.service_type,
        model.filename,
    ]
    if hasattr(model, 'task_name'):
        columns.append(model.task_name)
    if hasattr(model, 'report_name'):
        columns.append(model.report_name)
    return or_(*(column.ilike(f'%{term}%') for term in terms for column in columns))


def _parse_task_status(value: str | None) -> TaskStatus | None:
    if not value:
        return None
    try:
        return TaskStatus(value)
    except ValueError as exc:
        raise EHSException(
            '评价任务状态无效',
            code='AGENT_INVALID_TASK_STATUS',
            status_code=400,
            details={'allowed': [item.value for item in TaskStatus]},
        ) from exc


def _parse_report_status(value: str | None) -> ReportStatus | None:
    if not value:
        return None
    try:
        return ReportStatus(value)
    except ValueError as exc:
        raise EHSException(
            '检测报告状态无效',
            code='AGENT_INVALID_REPORT_STATUS',
            status_code=400,
            details={'allowed': [item.value for item in ReportStatus]},
        ) from exc


def _parse_report_type(value: str | None) -> ReportType | None:
    if not value:
        return None
    try:
        return ReportType(value)
    except ValueError as exc:
        raise EHSException(
            '检测报告类型无效',
            code='AGENT_INVALID_REPORT_TYPE',
            status_code=400,
            details={'allowed': [item.value for item in ReportType]},
        ) from exc


class AgentTools:
    @staticmethod
    def selected_tools(user_text: str) -> list[tuple[str, dict[str, Any]]]:
        text = user_text.lower()
        tools: list[tuple[str, dict[str, Any]]] = []
        context_query = user_text if _context_terms(user_text) else None
        context_args = {'context_query': context_query} if context_query else {}

        if context_query:
            tools.append(('get_client_project_context', {'query': context_query, 'limit': 8}))

        if any(key in user_text for key in ('工作台', '概览', '待处理', '待办', '总结', '今天')):
            tools.append(('get_workbench_summary', {}))

        if any(key in user_text for key in ('失败', '异常', '报错')):
            tools.append(('list_assessment_tasks', {'status': TaskStatus.FAILED.value, 'limit': 8, **context_args}))
            tools.append(('list_detection_reports', {'status': ReportStatus.FAILED.value, 'limit': 8, **context_args}))

        if any(key in user_text for key in ('评价', '任务', '材料')) or 'assessment' in text:
            tools.append(('list_assessment_tasks', {'limit': 8, **context_args}))

        if any(key in user_text for key in ('检测', '报告', '判定', '超标')) or 'detection' in text:
            status = None
            if any(key in user_text for key in ('未判定', '待判定', '没判定')):
                status = 'PENDING_CALCULATION'
            tools.append(('list_detection_reports', {'status': status, 'limit': 8, **context_args}))

        if any(key in user_text for key in ('限值', '法规', '标准', '条款', 'cas', 'CAS')):
            tools.append(('search_regulatory_limits', {'query': user_text, 'limit': 8}))

        if not tools:
            tools.append(('get_workbench_summary', {}))

        unique: dict[str, dict[str, Any]] = {}
        for name, args in tools:
            key = f'{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True)}'
            unique[key] = args | {'_name': name}
        return [(item.pop('_name'), item) for item in unique.values()]

    @staticmethod
    def run_tool(
        *,
        db: Session,
        actor: CurrentUser,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> AgentToolResult:
        if tool_name == 'get_workbench_summary':
            result = AgentTools.get_workbench_summary(db=db, actor=actor)
        elif tool_name == 'get_client_project_context':
            result = AgentTools.get_client_project_context(
                db=db,
                actor=actor,
                query=str(arguments.get('query') or ''),
                limit=int(arguments.get('limit') or 5),
            )
        elif tool_name == 'list_assessment_tasks':
            result = AgentTools.list_assessment_tasks(
                db=db,
                actor=actor,
                status=arguments.get('status'),
                context_query=arguments.get('context_query'),
                limit=int(arguments.get('limit') or 5),
            )
        elif tool_name == 'get_assessment_task':
            result = AgentTools.get_assessment_task(
                db=db,
                actor=actor,
                task_id=str(arguments.get('task_id') or ''),
            )
        elif tool_name == 'list_detection_reports':
            result = AgentTools.list_detection_reports(
                db=db,
                actor=actor,
                status=arguments.get('status'),
                report_type=arguments.get('report_type'),
                context_query=arguments.get('context_query'),
                limit=int(arguments.get('limit') or 5),
            )
        elif tool_name == 'get_detection_report':
            result = AgentTools.get_detection_report(
                db=db,
                actor=actor,
                report_id=str(arguments.get('report_id') or ''),
            )
        elif tool_name == 'search_regulatory_limits':
            result = AgentTools.search_regulatory_limits(
                db=db,
                query=str(arguments.get('query') or ''),
                limit=int(arguments.get('limit') or 5),
            )
        else:
            raise EHSException(
                'Agent 工具不存在',
                code='AGENT_TOOL_NOT_FOUND',
                status_code=400,
                details={'tool_name': tool_name},
            )
        return AgentToolResult(tool_name=tool_name, arguments=arguments, result=result)

    @staticmethod
    def get_workbench_summary(*, db: Session, actor: CurrentUser) -> dict[str, Any]:
        task_filters = _actor_org_filter(actor, AssessmentTask)
        report_filters = _actor_org_filter(actor, DetectionReport)

        def count_tasks(*filters: Any) -> int:
            return (
                db.scalar(select(func.count()).select_from(AssessmentTask).where(*task_filters, *filters))
                or 0
            )

        def count_reports(*filters: Any) -> int:
            return (
                db.scalar(select(func.count()).select_from(DetectionReport).where(*report_filters, *filters))
                or 0
            )

        active_statuses = [
            TaskStatus.PENDING,
            TaskStatus.PARSING,
            TaskStatus.AI_ANALYZING,
            TaskStatus.VALIDATING,
            TaskStatus.PERSISTING,
        ]
        pending_report_statuses = [ReportStatus.UPLOADED, ReportStatus.PARSED, ReportStatus.VALIDATED]

        return {
            'scope': {
                'role': actor.role.value,
                'organization_id': None if actor.role == AccountRole.ADMIN else actor.organization_id,
            },
            'assessment': {
                'total': count_tasks(),
                'success': count_tasks(AssessmentTask.status == TaskStatus.SUCCESS),
                'failed': count_tasks(AssessmentTask.status == TaskStatus.FAILED),
                'active': count_tasks(AssessmentTask.status.in_(active_statuses)),
            },
            'detection': {
                'total': count_reports(),
                'calculated': count_reports(DetectionReport.status == ReportStatus.CALCULATED),
                'failed': count_reports(DetectionReport.status == ReportStatus.FAILED),
                'pending': count_reports(DetectionReport.status.in_(pending_report_statuses)),
            },
            'recent_assessments': AgentTools.list_assessment_tasks(db=db, actor=actor, limit=5)[
                'items'
            ],
            'recent_reports': AgentTools.list_detection_reports(db=db, actor=actor, limit=5)['items'],
        }

    @staticmethod
    def list_assessment_tasks(
        *,
        db: Session,
        actor: CurrentUser,
        status: str | None = None,
        context_query: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        parsed_status = _parse_task_status(status)
        filters = _actor_org_filter(actor, AssessmentTask)
        if parsed_status is not None:
            filters.append(AssessmentTask.status == parsed_status)
        context_clause = _context_filter(AssessmentTask, context_query)
        if context_clause is not None:
            filters.append(context_clause)
        max_items = _safe_limit(limit)
        stmt = (
            select(AssessmentTask)
            .where(*filters)
            .order_by(AssessmentTask.updated_at.desc(), AssessmentTask.created_at.desc())
            .limit(max_items)
        )
        items = [
            {
                'task_id': item.id,
                'organization_id': item.organization_id,
                'task_name': item.task_name,
                **_client_project_fields(item),
                'filename': item.filename,
                'status': item.status.value,
                'progress': item.progress,
                'error_message': _short(item.error_message),
                'created_at': _dt(item.created_at),
                'updated_at': _dt(item.updated_at),
            }
            for item in db.scalars(stmt).all()
        ]
        return {
            'status': parsed_status.value if parsed_status else None,
            'context_terms': _context_terms(context_query),
            'items': items,
            'limit': max_items,
        }

    @staticmethod
    def get_assessment_task(*, db: Session, actor: CurrentUser, task_id: str) -> dict[str, Any]:
        task = db.get(AssessmentTask, task_id)
        if task is None:
            raise EHSException('评价任务不存在', code='TASK_NOT_FOUND', status_code=404)
        ensure_organization_scope(actor, task.organization_id)

        result = _json_dict(task.result_json)
        risks = result.get('risks') if isinstance(result.get('risks'), list) else []
        return {
            'task_id': task.id,
            'task_name': task.task_name,
            **_client_project_fields(task),
            'filename': task.filename,
            'status': task.status.value,
            'progress': task.progress,
            'summary': result.get('summary'),
            'risk_count': len(risks),
            'risks_preview': risks[:5],
            'error_message': _short(task.error_message),
            'created_at': _dt(task.created_at),
            'updated_at': _dt(task.updated_at),
        }

    @staticmethod
    def list_detection_reports(
        *,
        db: Session,
        actor: CurrentUser,
        status: str | None = None,
        report_type: str | None = None,
        context_query: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        pending_calculation = status == 'PENDING_CALCULATION'
        parsed_status = None if pending_calculation else _parse_report_status(status)
        parsed_type = _parse_report_type(report_type)
        filters = _actor_org_filter(actor, DetectionReport)
        if pending_calculation:
            filters.append(
                DetectionReport.status.in_(
                    [ReportStatus.UPLOADED, ReportStatus.PARSED, ReportStatus.VALIDATED]
                )
            )
        elif parsed_status is not None:
            filters.append(DetectionReport.status == parsed_status)
        if parsed_type is not None:
            filters.append(DetectionReport.report_type == parsed_type)
        context_clause = _context_filter(DetectionReport, context_query)
        if context_clause is not None:
            filters.append(context_clause)
        max_items = _safe_limit(limit)
        stmt = (
            select(DetectionReport)
            .where(*filters)
            .order_by(DetectionReport.updated_at.desc(), DetectionReport.created_at.desc())
            .limit(max_items)
        )
        items = [
            {
                'report_id': item.id,
                'organization_id': item.organization_id,
                'report_name': item.report_name,
                **_client_project_fields(item),
                'filename': item.filename,
                'report_type': item.report_type.value,
                'status': item.status.value,
                'issuer': item.issuer,
                'report_date': _dt(item.report_date),
                'error_message': _short(item.error_message),
                'created_at': _dt(item.created_at),
                'updated_at': _dt(item.updated_at),
            }
            for item in db.scalars(stmt).all()
        ]
        return {
            'status': 'PENDING_CALCULATION'
            if pending_calculation
            else parsed_status.value
            if parsed_status
            else None,
            'report_type': parsed_type.value if parsed_type else None,
            'context_terms': _context_terms(context_query),
            'items': items,
            'limit': max_items,
        }

    @staticmethod
    def get_client_project_context(
        *,
        db: Session,
        actor: CurrentUser,
        query: str,
        limit: int = 5,
    ) -> dict[str, Any]:
        terms = _context_terms(query)
        max_items = _safe_limit(limit)
        if not terms:
            return {
                'query': query.strip(),
                'terms': [],
                'assessment_counts': {},
                'detection_counts': {},
                'recent_assessments': [],
                'recent_reports': [],
                'limit': max_items,
            }

        task_filters = _actor_org_filter(actor, AssessmentTask)
        report_filters = _actor_org_filter(actor, DetectionReport)
        task_context = _context_filter(AssessmentTask, query)
        report_context = _context_filter(DetectionReport, query)
        if task_context is not None:
            task_filters.append(task_context)
        if report_context is not None:
            report_filters.append(report_context)

        task_status_rows = db.execute(
            select(AssessmentTask.status, func.count()).where(*task_filters).group_by(AssessmentTask.status)
        ).all()
        report_status_rows = db.execute(
            select(DetectionReport.status, func.count()).where(*report_filters).group_by(DetectionReport.status)
        ).all()

        return {
            'query': query.strip(),
            'terms': terms,
            'assessment_counts': {status.value: count for status, count in task_status_rows},
            'detection_counts': {status.value: count for status, count in report_status_rows},
            'recent_assessments': AgentTools.list_assessment_tasks(
                db=db,
                actor=actor,
                context_query=query,
                limit=max_items,
            )['items'],
            'recent_reports': AgentTools.list_detection_reports(
                db=db,
                actor=actor,
                context_query=query,
                limit=max_items,
            )['items'],
            'limit': max_items,
        }

    @staticmethod
    def get_detection_report(*, db: Session, actor: CurrentUser, report_id: str) -> dict[str, Any]:
        report = db.get(DetectionReport, report_id)
        if report is None:
            raise EHSException('检测报告不存在', code='DETECTION_REPORT_NOT_FOUND', status_code=404)
        ensure_organization_scope(actor, report.organization_id)

        sample_count = (
            db.scalar(select(func.count()).select_from(DetectionSample).where(DetectionSample.report_id == report.id))
            or 0
        )
        measurement_count = (
            db.scalar(
                select(func.count())
                .select_from(DetectionMeasurement)
                .join(DetectionSample, DetectionSample.id == DetectionMeasurement.sample_id)
                .where(DetectionSample.report_id == report.id)
            )
            or 0
        )
        status_rows = db.execute(
            select(ComplianceResult.status, func.count())
            .where(ComplianceResult.report_id == report.id)
            .group_by(ComplianceResult.status)
        ).all()
        status_counts = {status.value: count for status, count in status_rows}

        return {
            'report_id': report.id,
            'report_name': report.report_name,
            **_client_project_fields(report),
            'filename': report.filename,
            'report_type': report.report_type.value,
            'status': report.status.value,
            'sample_count': sample_count,
            'measurement_count': measurement_count,
            'compliance_counts': {
                'total': sum(status_counts.values()),
                'compliant': status_counts.get(ComplianceStatus.COMPLIANT.value, 0),
                'exceeded': status_counts.get(ComplianceStatus.EXCEEDED.value, 0),
                'borderline': status_counts.get(ComplianceStatus.BORDERLINE.value, 0),
                'insufficient': status_counts.get(ComplianceStatus.INSUFFICIENT_DATA.value, 0),
                'needs_review': status_counts.get(ComplianceStatus.NEEDS_REVIEW.value, 0),
            },
            'error_message': _short(report.error_message),
            'created_at': _dt(report.created_at),
            'updated_at': _dt(report.updated_at),
        }

    @staticmethod
    def search_regulatory_limits(*, db: Session, query: str, limit: int = 5) -> dict[str, Any]:
        keyword = query.strip()
        max_items = _safe_limit(limit)
        filters: list[Any] = []
        if keyword:
            like = f'%{keyword}%'
            filters.append(
                or_(
                    RegulatoryLimit.indicator_name.ilike(like),
                    RegulatoryLimit.cas_no.ilike(like),
                    RegulatoryLimit.aliases_json.ilike(like),
                    RegulatoryLimit.standard_code.ilike(like),
                    RegulatoryLimit.standard_name.ilike(like),
                    RegulatoryLimit.clause.ilike(like),
                )
            )
        stmt = (
            select(RegulatoryLimit)
            .where(*filters)
            .order_by(RegulatoryLimit.priority.asc(), RegulatoryLimit.indicator_name.asc())
            .limit(max_items)
        )
        items = [
            {
                'limit_id': item.id,
                'indicator_name': item.indicator_name,
                'cas_no': item.cas_no,
                'medium': _enum(item.medium),
                'limit_type': _enum(item.limit_type),
                'limit_value': _decimal(item.limit_value),
                'limit_min': _decimal(item.limit_min),
                'limit_max': _decimal(item.limit_max),
                'unit': item.unit,
                'standard_code': item.standard_code,
                'standard_name': item.standard_name,
                'clause': item.clause,
                'basis_text': _short(item.basis_text),
            }
            for item in db.scalars(stmt).all()
        ]
        return {'query': keyword, 'items': items, 'limit': max_items}
