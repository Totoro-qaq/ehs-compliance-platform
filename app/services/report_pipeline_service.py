from __future__ import annotations

import html
import io
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import EHSException
from app.core.patterns import is_uuid
from app.dao.detection_dao import DetectionReportDAO
from app.dao.report_pipeline_dao import ReportSectionDAO
from app.models.base import audit_now_naive
from app.models.db_models import (
    AgentMemory,
    AgentMemoryType,
    ComplianceEvidence,
    DetectionReport,
    ReportSection,
    ReportSectionCitationCheckStatus,
    ReportSectionReviewStatus,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.report_pipeline_schema import (
    ReportExportFormat,
    ReportReadinessIssueOut,
    ReportReadinessOut,
    ReportSectionOut,
    ReportSectionTemplateOut,
)
from app.services.access_control import (
    ensure_org_admin_or_system_admin,
    ensure_organization_scope,
    is_org_admin,
    is_system_admin,
)
from app.services.agent_model_provider import get_configured_agent_model_provider

_SECTION_KEY_RE = re.compile(r'^[A-Za-z0-9_.-]+$')
_MAX_CITATION_IDS = 50
_MAX_EVIDENCE_IDS = 50
_MAX_GENERATION_EVIDENCE_ITEMS = 50


@dataclass(frozen=True)
class _ReportSectionTemplate:
    section_key: str
    title: str
    description: str
    draft_content: str
    required: bool
    sort_order: int


@dataclass(frozen=True)
class ReportFileExport:
    filename: str
    content: str | bytes
    media_type: str


@dataclass(frozen=True)
class _CitationCheckResult:
    status: ReportSectionCitationCheckStatus
    message: str | None = None
    export_forbidden: bool = False


_REPORT_SECTION_TEMPLATES: tuple[_ReportSectionTemplate, ...] = (
    _ReportSectionTemplate(
        section_key='summary',
        title='报告摘要',
        description='项目、样品和主要风险的概览，不替代人工结论。',
        draft_content='本章节为结构化草稿，请结合检测数据、引用依据和人工复核意见补充。',
        required=True,
        sort_order=10,
    ),
    _ReportSectionTemplate(
        section_key='basis',
        title='依据说明',
        description='记录已核验的评价依据和引用来源，不内置真实法规或标准原文。',
        draft_content='本章节仅保留依据说明占位，正式内容必须来自已校验引用并经人工复核。',
        required=True,
        sort_order=20,
    ),
    _ReportSectionTemplate(
        section_key='findings',
        title='检测结果分析',
        description='汇总检测结果、异常项和需要关注的风险点。',
        draft_content='本章节为检测结果分析草稿，请按报告数据补充事实描述和风险判断。',
        required=True,
        sort_order=30,
    ),
    _ReportSectionTemplate(
        section_key='conclusion',
        title='评价结论',
        description='形成可复核的结论草稿，批准前不得作为正式结论。',
        draft_content='本章节为评价结论草稿，引用和人工复核通过前不得用于正式导出。',
        required=True,
        sort_order=40,
    ),
    _ReportSectionTemplate(
        section_key='actions',
        title='整改建议',
        description='记录建议措施、责任跟进和复查要求。',
        draft_content='本章节为整改建议草稿，请结合实际风险、现场情况和复核意见补充。',
        required=True,
        sort_order=50,
    ),
)
_TEMPLATE_BY_KEY = {template.section_key: template for template in _REPORT_SECTION_TEMPLATES}


class ReportPipelineService:
    @staticmethod
    def list_templates() -> list[ReportSectionTemplateOut]:
        return [_template_out(template) for template in _REPORT_SECTION_TEMPLATES]

    @staticmethod
    def bootstrap_sections(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
        section_keys: list[str] | None = None,
    ) -> list[ReportSectionOut]:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        selected_templates = _select_templates(section_keys)
        dao = ReportSectionDAO(db)
        existing_sections = dao.list_by_report(report.id)
        existing_keys = {section.section_key for section in existing_sections}
        created = False

        for template in selected_templates:
            if template.section_key in existing_keys:
                continue
            dao.upsert_section(
                organization_id=report.organization_id,
                report_id=report.id,
                section_key=template.section_key,
                title=template.title,
                draft_content=template.draft_content,
                citation_memory_ids_json=None,
                evidence_ids_json=None,
                citation_check_status=ReportSectionCitationCheckStatus.PENDING,
                citation_check_message='No citation memory ids supplied',
                evidence_check_status=ReportSectionCitationCheckStatus.PENDING,
                evidence_check_message='No evidence ids supplied',
                created_by_id=actor.account_id,
            )
            created = True

        if created:
            db.commit()

        sections = dao.list_by_report(report.id)
        return [_section_out(section) for section in _sort_sections(sections)]

    @staticmethod
    def upsert_section(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
        section_key: str,
        title: str,
        draft_content: str,
        citation_memory_ids: list[str],
        evidence_ids: list[str],
    ) -> ReportSectionOut:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        normalized_section_key = _normalize_section_key(section_key)
        normalized_title = _clean_required_text(title, field_name='title', max_length=255)
        normalized_content = _clean_required_text(draft_content, field_name='draft_content')
        normalized_citation_ids = _normalize_citation_ids(citation_memory_ids)
        normalized_evidence_ids = _normalize_evidence_ids(evidence_ids)
        citation_check = _check_citations(
            db=db,
            actor=actor,
            organization_id=report.organization_id,
            citation_memory_ids=normalized_citation_ids,
        )
        evidence_check = _check_evidence(
            db=db,
            organization_id=report.organization_id,
            report_id=report.id,
            evidence_ids=normalized_evidence_ids,
        )

        section = ReportSectionDAO(db).upsert_section(
            organization_id=report.organization_id,
            report_id=report.id,
            section_key=normalized_section_key,
            title=normalized_title,
            draft_content=normalized_content,
            citation_memory_ids_json=_dump_citation_ids(normalized_citation_ids),
            evidence_ids_json=_dump_evidence_ids(normalized_evidence_ids),
            citation_check_status=citation_check.status,
            citation_check_message=citation_check.message,
            evidence_check_status=evidence_check.status,
            evidence_check_message=evidence_check.message,
            created_by_id=actor.account_id,
        )
        db.commit()
        db.refresh(section)
        return _section_out(section)

    @staticmethod
    async def generate_section_draft(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
        section_key: str,
        instruction: str | None,
        citation_memory_ids: list[str],
        evidence_limit: int,
    ) -> ReportSectionOut:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        template = _template_for_section_key(section_key)
        evidence_items = _list_report_evidence_for_generation(
            db=db,
            organization_id=report.organization_id,
            report_id=report.id,
            limit=evidence_limit,
        )
        if not evidence_items:
            raise EHSException(
                'Report section draft generation requires report evidence first',
                code='REPORT_SECTION_EVIDENCE_REQUIRED_FOR_GENERATION',
                status_code=400,
            )

        draft_content = await _generate_section_draft_content(
            report=report,
            template=template,
            evidence_items=evidence_items,
            instruction=_clean_optional_text(instruction, max_length=1000),
        )
        evidence_ids = [item.id for item in evidence_items]
        return ReportPipelineService.upsert_section(
            db=db,
            actor=actor,
            report_id=report.id,
            section_key=template.section_key,
            title=template.title,
            draft_content=draft_content,
            citation_memory_ids=citation_memory_ids,
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def list_sections(*, db: Session, actor: CurrentUser, report_id: str) -> list[ReportSectionOut]:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        sections = ReportSectionDAO(db).list_by_report(report.id)
        return [_section_out(section) for section in _sort_sections(sections)]

    @staticmethod
    def update_review_status(
        *,
        db: Session,
        actor: CurrentUser,
        section_id: str,
        review_status: ReportSectionReviewStatus,
        review_note: str | None,
    ) -> ReportSectionOut:
        section = _get_scoped_section(db=db, actor=actor, section_id=section_id)
        ensure_org_admin_or_system_admin(actor, section.organization_id)
        if review_status == ReportSectionReviewStatus.DRAFT:
            raise EHSException(
                'DRAFT status is managed by section draft updates',
                code='REPORT_SECTION_INVALID_REVIEW_STATUS',
                status_code=400,
            )
        if (
            review_status == ReportSectionReviewStatus.APPROVED
            and section.citation_check_status != ReportSectionCitationCheckStatus.PASSED
        ):
            raise EHSException(
                'Report section citations must pass before approval',
                code='REPORT_SECTION_CITATIONS_NOT_PASSED',
                status_code=400,
            )
        evidence_ids = _load_evidence_ids(section.evidence_ids_json)
        evidence_check = _check_evidence(
            db=db,
            organization_id=section.organization_id,
            report_id=section.report_id,
            evidence_ids=evidence_ids,
        )
        if (
            review_status == ReportSectionReviewStatus.APPROVED
            and evidence_ids
            and (
                section.evidence_check_status != ReportSectionCitationCheckStatus.PASSED
                or evidence_check.status != ReportSectionCitationCheckStatus.PASSED
            )
        ):
            raise EHSException(
                evidence_check.message or 'Report section evidence must pass before approval',
                code='REPORT_SECTION_EVIDENCE_NOT_PASSED',
                status_code=400,
            )

        section.review_status = review_status
        section.review_note = _clean_optional_text(review_note, max_length=1000)
        section.reviewed_by_id = actor.account_id
        section.reviewed_at = audit_now_naive()
        section.updated_at = audit_now_naive()
        db.commit()
        db.refresh(section)
        return _section_out(section)

    @staticmethod
    def get_readiness(*, db: Session, actor: CurrentUser, report_id: str) -> ReportReadinessOut:
        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        sections = ReportSectionDAO(db).list_by_report(report.id)
        sections_by_key = {section.section_key: section for section in sections}
        required_keys = [
            template.section_key for template in _REPORT_SECTION_TEMPLATES if template.required
        ]
        issues: list[ReportReadinessIssueOut] = []

        for template in _REPORT_SECTION_TEMPLATES:
            if template.required and template.section_key not in sections_by_key:
                issues.append(
                    ReportReadinessIssueOut(
                        code='REPORT_SECTION_MISSING',
                        section_key=template.section_key,
                        title=template.title,
                        message='Required report section is missing',
                    )
                )

        for section in _sort_sections(sections):
            citation_ids = _load_citation_ids(section.citation_memory_ids_json)
            citation_check = _check_citations(
                db=db,
                actor=actor,
                organization_id=report.organization_id,
                citation_memory_ids=citation_ids,
            )
            if (
                section.citation_check_status != ReportSectionCitationCheckStatus.PASSED
                or citation_check.status != ReportSectionCitationCheckStatus.PASSED
            ):
                issues.append(
                    ReportReadinessIssueOut(
                        code='REPORT_SECTION_CITATION_EXPORT_FORBIDDEN'
                        if citation_check.export_forbidden
                        else 'REPORT_SECTION_CITATIONS_NOT_PASSED',
                        section_key=section.section_key,
                        title=section.title,
                        message=citation_check.message
                        or 'Report section citations must pass before export',
                    )
                )
            evidence_ids = _load_evidence_ids(section.evidence_ids_json)
            if evidence_ids:
                evidence_check = _check_evidence(
                    db=db,
                    organization_id=report.organization_id,
                    report_id=report.id,
                    evidence_ids=evidence_ids,
                )
                if (
                    section.evidence_check_status != ReportSectionCitationCheckStatus.PASSED
                    or evidence_check.status != ReportSectionCitationCheckStatus.PASSED
                ):
                    issues.append(
                        ReportReadinessIssueOut(
                            code='REPORT_SECTION_EVIDENCE_NOT_PASSED',
                            section_key=section.section_key,
                            title=section.title,
                            message=evidence_check.message
                            or 'Report section evidence must pass before export',
                        )
                    )
            if section.review_status != ReportSectionReviewStatus.APPROVED:
                issues.append(
                    ReportReadinessIssueOut(
                        code='REPORT_SECTION_REVIEW_NOT_APPROVED',
                        section_key=section.section_key,
                        title=section.title,
                        message='Report section must be approved before export',
                    )
                )

        return ReportReadinessOut(
            report_id=report.id,
            ready=not issues,
            required_section_keys=required_keys,
            issues=issues,
        )

    @staticmethod
    def build_file_export(
        *,
        db: Session,
        actor: CurrentUser,
        report_id: str,
        export_format: ReportExportFormat,
    ) -> ReportFileExport:
        readiness = ReportPipelineService.get_readiness(db=db, actor=actor, report_id=report_id)
        if not readiness.ready:
            raise EHSException(
                'Report is not ready for export',
                code='REPORT_EXPORT_NOT_READY',
                status_code=400,
                details={'issues': [issue.model_dump() for issue in readiness.issues]},
            )

        report = _get_scoped_report(db=db, actor=actor, report_id=report_id)
        sections = ReportSectionDAO(db).list_by_report(report.id)
        sorted_sections = _sort_sections(sections)
        generated_at = audit_now_naive()
        filename_stem = _safe_filename_stem(report.report_name or report.filename or report.id)
        if export_format == ReportExportFormat.MARKDOWN:
            return ReportFileExport(
                filename=f'{filename_stem}.md',
                content=_render_markdown_export(
                    report=report,
                    sections=sorted_sections,
                    generated_at=generated_at,
                ),
                media_type='text/markdown; charset=utf-8',
            )
        if export_format == ReportExportFormat.TXT:
            return ReportFileExport(
                filename=f'{filename_stem}.txt',
                content=_render_plain_text_export(
                    report=report,
                    sections=sorted_sections,
                    generated_at=generated_at,
                ),
                media_type='text/plain; charset=utf-8',
            )
        if export_format == ReportExportFormat.DOCX:
            return ReportFileExport(
                filename=f'{filename_stem}.docx',
                content=_render_docx_export(
                    report=report,
                    sections=sorted_sections,
                    generated_at=generated_at,
                ),
                media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            )
        if export_format == ReportExportFormat.DOC:
            return ReportFileExport(
                filename=f'{filename_stem}.doc',
                content=_render_doc_export(
                    report=report,
                    sections=sorted_sections,
                    generated_at=generated_at,
                ),
                media_type='application/msword; charset=utf-8',
            )
        raise EHSException(
            'Unsupported report export format',
            code='REPORT_EXPORT_FORMAT_UNSUPPORTED',
            status_code=400,
            details={'format': export_format},
        )


def _template_out(template: _ReportSectionTemplate) -> ReportSectionTemplateOut:
    return ReportSectionTemplateOut(
        section_key=template.section_key,
        title=template.title,
        description=template.description,
        required=template.required,
        sort_order=template.sort_order,
    )


def _select_templates(section_keys: list[str] | None) -> list[_ReportSectionTemplate]:
    if not section_keys:
        return list(_REPORT_SECTION_TEMPLATES)

    selected: list[_ReportSectionTemplate] = []
    seen: set[str] = set()
    for raw_key in section_keys:
        section_key = _normalize_section_key(raw_key)
        template = _TEMPLATE_BY_KEY.get(section_key)
        if template is None:
            raise EHSException(
                'Unknown report section template key',
                code='REPORT_SECTION_TEMPLATE_NOT_FOUND',
                status_code=400,
                details={'section_key': section_key},
            )
        if section_key not in seen:
            selected.append(template)
            seen.add(section_key)
    return selected


def _template_for_section_key(section_key: str) -> _ReportSectionTemplate:
    normalized = _normalize_section_key(section_key)
    template = _TEMPLATE_BY_KEY.get(normalized)
    if template is None:
        raise EHSException(
            'Unknown report section template key',
            code='REPORT_SECTION_TEMPLATE_NOT_FOUND',
            status_code=400,
            details={'section_key': normalized},
        )
    return template


def _list_report_evidence_for_generation(
    *,
    db: Session,
    organization_id: str,
    report_id: str,
    limit: int,
) -> list[ComplianceEvidence]:
    max_items = min(max(limit, 1), _MAX_GENERATION_EVIDENCE_ITEMS)
    stmt = (
        select(ComplianceEvidence)
        .join(DetectionReport, ComplianceEvidence.report_id == DetectionReport.id)
        .where(
            ComplianceEvidence.report_id == report_id,
            ComplianceEvidence.deleted_at.is_(None),
            DetectionReport.organization_id == organization_id,
            DetectionReport.deleted_at.is_(None),
        )
        .order_by(ComplianceEvidence.created_at.asc(), ComplianceEvidence.id.asc())
        .limit(max_items)
    )
    return list(db.scalars(stmt).all())


async def _generate_section_draft_content(
    *,
    report: DetectionReport,
    template: _ReportSectionTemplate,
    evidence_items: list[ComplianceEvidence],
    instruction: str | None,
) -> str:
    messages = [
        {
            'role': 'system',
            'content': (
                '你是 EHS 报告草稿助手。只能基于用户提供的报告元信息和证据链生成章节草稿；'
                '不得编造法规、限值、检测数据或正式结论。输出必须明确这是待人工复核草稿。'
            ),
        },
        {
            'role': 'user',
            'content': _build_section_generation_prompt(
                report=report,
                template=template,
                evidence_items=evidence_items,
                instruction=instruction,
            ),
        },
    ]
    try:
        raw_content = await get_configured_agent_model_provider().generate(messages=messages)
    except EHSException:
        raise
    except Exception as exc:
        raise EHSException(
            'Report section draft generation failed',
            code='REPORT_SECTION_DRAFT_GENERATION_FAILED',
            status_code=503,
            details={'error': str(exc)[:500]},
        ) from exc
    return _clean_generated_draft_content(raw_content)


def _build_section_generation_prompt(
    *,
    report: DetectionReport,
    template: _ReportSectionTemplate,
    evidence_items: list[ComplianceEvidence],
    instruction: str | None,
) -> str:
    payload = {
        'report': {
            'report_id': report.id,
            'report_name': report.report_name,
            'filename': report.filename,
            'client_name': report.client_name,
            'project_name': report.project_name,
            'project_code': report.project_code,
            'service_type': report.service_type,
            'report_type': report.report_type.value,
            'status': report.status.value,
        },
        'section': {
            'section_key': template.section_key,
            'title': template.title,
            'description': template.description,
        },
        'evidence': [_evidence_prompt_item(item) for item in evidence_items],
        'instruction': instruction,
        'requirements': [
            '只生成当前章节草稿，不生成整份报告。',
            '必须引用 evidence_id，方便人工复核证据链。',
            '不得把草稿写成已批准、已签发或最终结论。',
            '如证据不足，直接写明待补充事实和复核点。',
        ],
    }
    return '请基于以下 JSON 生成中文报告章节草稿：\n' + json.dumps(
        payload,
        ensure_ascii=False,
        default=str,
    )


def _evidence_prompt_item(item: ComplianceEvidence) -> dict[str, str | None]:
    return {
        'evidence_id': item.id,
        'evidence_type': item.evidence_type.value,
        'result_id': item.result_id,
        'standard_code': item.standard_code,
        'standard_name': item.standard_name,
        'source_uri': item.source_uri,
        'summary': item.evidence_summary,
    }


def _clean_generated_draft_content(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```[\w-]*\s*', '', cleaned)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
    if len(cleaned) > 8000:
        cleaned = cleaned[:8000].rstrip()
    return _clean_required_text(cleaned, field_name='draft_content')


def _sort_sections(sections: list[ReportSection]) -> list[ReportSection]:
    return sorted(
        sections,
        key=lambda section: (
            _TEMPLATE_BY_KEY.get(section.section_key).sort_order
            if section.section_key in _TEMPLATE_BY_KEY
            else 10_000,
            section.section_key,
            section.created_at.isoformat(),
        ),
    )


def _safe_filename_stem(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', value.strip())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(' ._')
    return cleaned[:80] or 'report-export'


def _render_markdown_export(
    *,
    report: DetectionReport,
    sections: list[ReportSection],
    generated_at: datetime,
) -> str:
    lines = [
        f'# {report.report_name or report.filename or "检测报告"}',
        '',
        '> 本文件由已审批章节生成。正式签发前仍需按机构流程复核、盖章和归档。',
        '',
        '## 报告信息',
        '',
        f'- 报告 ID：{report.id}',
        f'- 来源文件：{report.filename or "-"}',
        f'- 委托单位：{report.client_name or "-"}',
        f'- 项目名称：{report.project_name or "-"}',
        f'- 项目编号：{report.project_code or "-"}',
        f'- 报告类别：{report.service_type or "-"}',
        f'- 生成时间：{generated_at.isoformat(timespec="seconds")}',
        '',
    ]
    for section in sections:
        lines.extend(
            [
                f'## {section.title}',
                '',
                section.draft_content.strip(),
                '',
            ]
        )
        citation_ids = _load_citation_ids(section.citation_memory_ids_json)
        if citation_ids:
            lines.append('引用记忆：')
            lines.extend(f'- `{citation_id}`' for citation_id in citation_ids)
            lines.append('')
        evidence_ids = _load_evidence_ids(section.evidence_ids_json)
        if evidence_ids:
            lines.append('证据链：')
            lines.extend(f'- `{evidence_id}`' for evidence_id in evidence_ids)
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def _render_plain_text_export(
    *,
    report: DetectionReport,
    sections: list[ReportSection],
    generated_at: datetime,
) -> str:
    lines = [
        report.report_name or report.filename or '检测报告',
        '=' * 24,
        '',
        '本文件由已审批章节生成。正式签发前仍需按机构流程复核、盖章和归档。',
        '',
        '报告信息',
        '-' * 24,
        f'报告 ID：{report.id}',
        f'来源文件：{report.filename or "-"}',
        f'委托单位：{report.client_name or "-"}',
        f'项目名称：{report.project_name or "-"}',
        f'项目编号：{report.project_code or "-"}',
        f'报告类别：{report.service_type or "-"}',
        f'生成时间：{generated_at.isoformat(timespec="seconds")}',
        '',
    ]
    for section in sections:
        lines.extend(
            [
                section.title,
                '-' * 24,
                section.draft_content.strip(),
                '',
            ]
        )
        citation_ids = _load_citation_ids(section.citation_memory_ids_json)
        if citation_ids:
            lines.append('引用记忆：')
            lines.extend(f'- {citation_id}' for citation_id in citation_ids)
            lines.append('')
        evidence_ids = _load_evidence_ids(section.evidence_ids_json)
        if evidence_ids:
            lines.append('证据链：')
            lines.extend(f'- {evidence_id}' for evidence_id in evidence_ids)
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def _render_doc_export(
    *,
    report: DetectionReport,
    sections: list[ReportSection],
    generated_at: datetime,
) -> bytes:
    title = html.escape(report.report_name or report.filename or '检测报告')
    body_parts = [
        '<!doctype html>',
        '<html><head><meta charset="utf-8">',
        '<style>body{font-family:"Microsoft YaHei",Arial,sans-serif;line-height:1.6;}'
        'h1{font-size:22px;}h2{font-size:17px;margin-top:22px;}'
        'table{border-collapse:collapse;width:100%;}td{border:1px solid #d0d7de;padding:6px;}'
        '.notice{color:#555;}</style>',
        f'<title>{title}</title></head><body>',
        f'<h1>{title}</h1>',
        '<p class="notice">本文件由已审批章节生成。正式签发前仍需按机构流程复核、盖章和归档。</p>',
        '<h2>报告信息</h2>',
        '<table>',
    ]
    for label, value in _report_info_rows(report=report, generated_at=generated_at):
        body_parts.append(f'<tr><td>{html.escape(label)}</td><td>{html.escape(value)}</td></tr>')
    body_parts.append('</table>')
    for section in sections:
        body_parts.extend(
            [
                f'<h2>{html.escape(section.title)}</h2>',
                f'<p>{html.escape(section.draft_content.strip()).replace(chr(10), "<br>")}</p>',
            ]
        )
        citation_ids = _load_citation_ids(section.citation_memory_ids_json)
        if citation_ids:
            body_parts.append('<p>引用记忆：</p><ul>')
            body_parts.extend(f'<li>{html.escape(citation_id)}</li>' for citation_id in citation_ids)
            body_parts.append('</ul>')
        evidence_ids = _load_evidence_ids(section.evidence_ids_json)
        if evidence_ids:
            body_parts.append('<p>证据链：</p><ul>')
            body_parts.extend(f'<li>{html.escape(evidence_id)}</li>' for evidence_id in evidence_ids)
            body_parts.append('</ul>')
    body_parts.append('</body></html>')
    return '\n'.join(body_parts).encode('utf-8')


def _render_docx_export(
    *,
    report: DetectionReport,
    sections: list[ReportSection],
    generated_at: datetime,
) -> bytes:
    paragraphs: list[str] = [
        _docx_paragraph(report.report_name or report.filename or '检测报告', bold=True, size=32),
        _docx_paragraph('本文件由已审批章节生成。正式签发前仍需按机构流程复核、盖章和归档。'),
        _docx_paragraph('报告信息', bold=True, size=26),
    ]
    for label, value in _report_info_rows(report=report, generated_at=generated_at):
        paragraphs.append(_docx_paragraph(f'{label}：{value}'))
    for section in sections:
        paragraphs.append(_docx_paragraph(section.title, bold=True, size=26))
        paragraphs.extend(_docx_paragraph(line) for line in section.draft_content.strip().splitlines())
        citation_ids = _load_citation_ids(section.citation_memory_ids_json)
        if citation_ids:
            paragraphs.append(_docx_paragraph('引用记忆：'))
            paragraphs.extend(_docx_paragraph(f'- {citation_id}') for citation_id in citation_ids)
        evidence_ids = _load_evidence_ids(section.evidence_ids_json)
        if evidence_ids:
            paragraphs.append(_docx_paragraph('证据链：'))
            paragraphs.extend(_docx_paragraph(f'- {evidence_id}') for evidence_id in evidence_ids)

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>'
        f'{"".join(paragraphs)}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        '</w:body></w:document>'
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            '[Content_Types].xml',
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '</Types>',
        )
        archive.writestr(
            '_rels/.rels',
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr('word/document.xml', document_xml)
    return output.getvalue()


def _docx_paragraph(text: str, *, bold: bool = False, size: int | None = None) -> str:
    cleaned = html.escape(text.strip(), quote=False)
    if not cleaned:
        return '<w:p/>'
    run_props = []
    if bold:
        run_props.append('<w:b/>')
    if size is not None:
        run_props.append(f'<w:sz w:val="{size}"/>')
    props = f'<w:rPr>{"".join(run_props)}</w:rPr>' if run_props else ''
    return f'<w:p><w:r>{props}<w:t xml:space="preserve">{cleaned}</w:t></w:r></w:p>'


def _report_info_rows(*, report: DetectionReport, generated_at: datetime) -> list[tuple[str, str]]:
    return [
        ('报告 ID', report.id),
        ('来源文件', report.filename or '-'),
        ('委托单位', report.client_name or '-'),
        ('项目名称', report.project_name or '-'),
        ('项目编号', report.project_code or '-'),
        ('报告类别', report.service_type or '-'),
        ('生成时间', generated_at.isoformat(timespec='seconds')),
    ]


def _get_scoped_report(*, db: Session, actor: CurrentUser, report_id: str) -> DetectionReport:
    if not is_uuid(report_id):
        raise EHSException(
            'report_id must be a valid UUID',
            code='REPORT_PIPELINE_INVALID_REPORT_ID',
            status_code=400,
        )
    report = DetectionReportDAO(db).get_by_id(report_id)
    if report is None:
        raise EHSException(
            'Detection report not found',
            code='DETECTION_REPORT_NOT_FOUND',
            status_code=404,
        )
    ensure_organization_scope(actor, report.organization_id)
    return report


def _get_scoped_section(*, db: Session, actor: CurrentUser, section_id: str) -> ReportSection:
    if not is_uuid(section_id):
        raise EHSException(
            'section_id must be a valid UUID',
            code='REPORT_PIPELINE_INVALID_SECTION_ID',
            status_code=400,
        )
    section = ReportSectionDAO(db).get_by_id(section_id)
    if section is None:
        raise EHSException(
            'Report section not found',
            code='REPORT_SECTION_NOT_FOUND',
            status_code=404,
        )
    ensure_organization_scope(actor, section.organization_id)
    return section


def _normalize_section_key(section_key: str) -> str:
    normalized = _clean_required_text(section_key, field_name='section_key', max_length=64)
    if not _SECTION_KEY_RE.fullmatch(normalized):
        raise EHSException(
            'section_key only allows letters, numbers, dot, underscore and hyphen',
            code='REPORT_SECTION_INVALID_KEY',
            status_code=400,
        )
    return normalized


def _normalize_citation_ids(citation_memory_ids: list[str]) -> list[str]:
    if len(citation_memory_ids) > _MAX_CITATION_IDS:
        raise EHSException(
            'Too many citation memory ids',
            code='REPORT_SECTION_TOO_MANY_CITATIONS',
            status_code=400,
            details={'max': _MAX_CITATION_IDS},
        )
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in citation_memory_ids:
        citation_id = (raw_id or '').strip()
        if not is_uuid(citation_id):
            raise EHSException(
                'citation_memory_ids must be valid UUID strings',
                code='REPORT_SECTION_INVALID_CITATION_ID',
                status_code=400,
            )
        if citation_id not in seen:
            normalized_ids.append(citation_id)
            seen.add(citation_id)
    return normalized_ids


def _normalize_evidence_ids(evidence_ids: list[str]) -> list[str]:
    if len(evidence_ids) > _MAX_EVIDENCE_IDS:
        raise EHSException(
            'Too many evidence ids',
            code='REPORT_SECTION_TOO_MANY_EVIDENCE_IDS',
            status_code=400,
            details={'max': _MAX_EVIDENCE_IDS},
        )
    normalized_ids: list[str] = []
    seen: set[str] = set()
    for raw_id in evidence_ids:
        evidence_id = (raw_id or '').strip()
        if not is_uuid(evidence_id):
            raise EHSException(
                'evidence_ids must be valid UUID strings',
                code='REPORT_SECTION_INVALID_EVIDENCE_ID',
                status_code=400,
            )
        if evidence_id not in seen:
            normalized_ids.append(evidence_id)
            seen.add(evidence_id)
    return normalized_ids


def _check_citations(
    *,
    db: Session,
    actor: CurrentUser,
    organization_id: str,
    citation_memory_ids: list[str],
) -> _CitationCheckResult:
    if not citation_memory_ids:
        return _CitationCheckResult(
            status=ReportSectionCitationCheckStatus.PENDING,
            message='No citation memory ids supplied',
        )

    filters = [
        AgentMemory.id.in_(citation_memory_ids),
        AgentMemory.organization_id == organization_id,
        AgentMemory.memory_type == AgentMemoryType.CITATION,
        AgentMemory.deleted_at.is_(None),
        or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > audit_now_naive()),
    ]
    if not is_system_admin(actor) and not is_org_admin(actor):
        filters.append(or_(AgentMemory.account_id.is_(None), AgentMemory.account_id == actor.account_id))

    memories = list(db.scalars(select(AgentMemory).where(*filters)).all())
    found_ids = {memory.id for memory in memories}
    missing_ids = [citation_id for citation_id in citation_memory_ids if citation_id not in found_ids]
    if missing_ids:
        return _CitationCheckResult(
            status=ReportSectionCitationCheckStatus.FAILED,
            message=f'Invalid or invisible citation memory ids: {", ".join(missing_ids[:5])}',
        )
    blocked_ids = [
        memory.id
        for memory in memories
        if not _citation_allows_report_export(memory)
    ]
    if blocked_ids:
        return _CitationCheckResult(
            status=ReportSectionCitationCheckStatus.FAILED,
            message=f'Citation export authorization failed: {", ".join(blocked_ids[:5])}',
            export_forbidden=True,
        )
    return _CitationCheckResult(status=ReportSectionCitationCheckStatus.PASSED)


def _check_evidence(
    *,
    db: Session,
    organization_id: str,
    report_id: str,
    evidence_ids: list[str],
) -> _CitationCheckResult:
    if not evidence_ids:
        return _CitationCheckResult(
            status=ReportSectionCitationCheckStatus.PENDING,
            message='No evidence ids supplied',
        )

    stmt = (
        select(ComplianceEvidence)
        .join(DetectionReport, ComplianceEvidence.report_id == DetectionReport.id)
        .where(
            ComplianceEvidence.id.in_(evidence_ids),
            ComplianceEvidence.report_id == report_id,
            ComplianceEvidence.deleted_at.is_(None),
            DetectionReport.organization_id == organization_id,
            DetectionReport.deleted_at.is_(None),
        )
    )
    found_ids = {evidence.id for evidence in db.scalars(stmt).all()}
    missing_ids = [evidence_id for evidence_id in evidence_ids if evidence_id not in found_ids]
    if missing_ids:
        return _CitationCheckResult(
            status=ReportSectionCitationCheckStatus.FAILED,
            message=f'Invalid or invisible evidence ids: {", ".join(missing_ids[:5])}',
        )
    return _CitationCheckResult(status=ReportSectionCitationCheckStatus.PASSED)


def _clean_required_text(value: str, *, field_name: str, max_length: int | None = None) -> str:
    cleaned = ' '.join(value.strip().split()) if field_name != 'draft_content' else value.strip()
    if not cleaned:
        raise EHSException(
            f'{field_name} is required',
            code='REPORT_SECTION_REQUIRED_FIELD',
            status_code=400,
            details={'field': field_name},
        )
    return cleaned[:max_length] if max_length is not None else cleaned


def _clean_optional_text(value: str | None, *, max_length: int) -> str | None:
    cleaned = (value or '').strip()
    return cleaned[:max_length] if cleaned else None


def _dump_citation_ids(citation_memory_ids: list[str]) -> str | None:
    if not citation_memory_ids:
        return None
    return json.dumps(citation_memory_ids, ensure_ascii=False)


def _dump_evidence_ids(evidence_ids: list[str]) -> str | None:
    if not evidence_ids:
        return None
    return json.dumps(evidence_ids, ensure_ascii=False)


def _load_citation_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def _load_evidence_ids(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def _citation_allows_report_export(memory: AgentMemory) -> bool:
    metadata = _json_dict(memory.metadata_json)
    if metadata.get('citation_authorized_for_export') is True:
        return True
    return (
        metadata.get('authorized') is True
        and metadata.get('allow_ai_retrieval') is True
        and metadata.get('allow_excerpt_export') is True
    )


def _json_dict(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _section_out(section: ReportSection) -> ReportSectionOut:
    return ReportSectionOut(
        id=section.id,
        organization_id=section.organization_id,
        report_id=section.report_id,
        section_key=section.section_key,
        title=section.title,
        draft_content=section.draft_content,
        citation_memory_ids=_load_citation_ids(section.citation_memory_ids_json),
        citation_check_status=section.citation_check_status,
        citation_check_message=section.citation_check_message,
        evidence_ids=_load_evidence_ids(section.evidence_ids_json),
        evidence_check_status=section.evidence_check_status,
        evidence_check_message=section.evidence_check_message,
        review_status=section.review_status,
        review_note=section.review_note,
        reviewed_by_id=section.reviewed_by_id,
        reviewed_at=section.reviewed_at,
        created_by_id=section.created_by_id,
        created_at=section.created_at,
        updated_at=section.updated_at,
    )
