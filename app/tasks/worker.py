from __future__ import annotations

import sys
import time
from pathlib import Path

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging_setup import configure_logging, get_logger
from app.core.request_context import (
    get_trace_id,
    reset_request_id,
    reset_trace_context,
    set_request_id,
    set_trace_context,
)
from app.core.sse_broker import publish_task_progress
from app.dao.assessment_dao import AssessmentDAO
from app.models.db_models import TaskStatus
from app.schemas.ehs_schema import EHSAssessmentResult
from app.services.dify_service import (
    DifyResultStructureError,
    DifyWorkflowError,
    fetch_assessment_result,
)
from app.services.pdf_text_service import DocumentTextExtractError, extract_text_from_document_file

_log = get_logger(__name__)
_NEEDS_REVIEW_SUMMARY_MAX_CHARS = 20000


def _mark_status(
    dao: AssessmentDAO,
    *,
    task_id: str,
    status: TaskStatus,
    progress: int,
    started_at: float,
    message: str | None = None,
    error_message: str | None = None,
) -> None:
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    dao.update_status(
        task_id=task_id,
        status=status,
        progress=progress,
        error_message=error_message,
    )
    dao.append_timeline_event(
        task_id=task_id,
        status=status,
        progress=progress,
        message=message or status.value,
        elapsed_ms=elapsed_ms,
    )


@worker_process_init.connect
def _init_worker_logging(**_kwargs) -> None:
    settings.validate_production()
    configure_logging(
        log_dir=settings.log_dir,
        log_file=settings.log_worker_file,
        log_level=settings.log_level,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )


celery_app = Celery(
    'ehs_worker',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Windows defaults to prefork, which is fragile for this project. Use threads so one
# slow blocking Dify call does not leave later uploads stuck in PENDING.
if sys.platform == 'win32':
    celery_app.conf.worker_pool = 'threads'
    celery_app.conf.worker_concurrency = 4

celery_app.conf.beat_schedule = {
    'cleanup-expired-uploads': {
        'task': 'app.tasks.file_cleanup.cleanup_expired_uploads',
        'schedule': 60 * 60 * 24,
    },
}
celery_app.conf.include = [*celery_app.conf.get('include', []), 'app.tasks.file_cleanup']


def _load_body_text(
    task_id: str,
    file_path: str,
    filename: str,
    existing_parsed: str | None,
    dao: AssessmentDAO,
) -> str:
    text = (existing_parsed or '').strip()
    if text:
        return text

    path = Path(file_path)
    if not path.is_file():
        raise RuntimeError(f'File does not exist: {path}')

    try:
        text = extract_text_from_document_file(path).strip()
    except DocumentTextExtractError as exc:
        raise RuntimeError(f'Document text extraction failed: {exc}') from exc

    if text:
        dao.update_by_id(task_id, parsed_text=text)
    return text


def _build_needs_review_result(exc: DifyResultStructureError) -> EHSAssessmentResult:
    raw_output = (exc.raw_output or '').strip()
    summary = raw_output or '模型返回结果未满足结构化契约，需人工复核。'
    truncated = len(summary) > _NEEDS_REVIEW_SUMMARY_MAX_CHARS
    if truncated:
        summary = summary[:_NEEDS_REVIEW_SUMMARY_MAX_CHARS]

    metadata = {
        'needs_review': True,
        'reason': str(exc),
    }
    if raw_output:
        metadata['raw_output_chars'] = len(raw_output)
        metadata['raw_output_truncated'] = truncated
    return EHSAssessmentResult(risks=[], summary=summary, metadata=metadata)


@celery_app.task(name='app.tasks.worker.run_assessment_task')
def run_assessment_task(
    task_id: str,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> None:
    request_token = set_request_id(request_id)
    trace_token = set_trace_context(trace_id=trace_id)
    db = SessionLocal()
    dao = AssessmentDAO(db)
    started_at = time.perf_counter()
    try:
        task = dao.get_by_id(task_id)
        if task is None:
            _log.warning('Assessment task does not exist: task_id=%s', task_id)
            return
        if task.status != TaskStatus.PENDING:
            _log.info(
                'Assessment task skipped because it is not pending task_id=%s status=%s',
                task_id,
                task.status.value,
            )
            publish_task_progress(
                task_id,
                task.status.value,
                task.progress,
                task.error_message[:500] if task.error_message else None,
            )
            return

        _log.info(
            'Assessment task started task_id=%s request_id=%s trace_id=%s',
            task_id,
            request_id,
            get_trace_id(),
        )
        _mark_status(
            dao,
            task_id=task_id,
            status=TaskStatus.PARSING,
            progress=12,
            started_at=started_at,
            message='解析文档',
        )
        publish_task_progress(task_id, TaskStatus.PARSING.value, 12)
        body = _load_body_text(task_id, task.file_path, task.filename, task.parsed_text, dao)
        if not body:
            raise RuntimeError(
                'No usable document text was extracted. Upload a text-bearing PDF/TXT/DOCX/DOC/CSV file, '
                'or ensure parsed_text is already present in the database.'
            )

        _mark_status(
            dao,
            task_id=task_id,
            status=TaskStatus.AI_ANALYZING,
            progress=45,
            started_at=started_at,
            message='Dify 工作流分析',
        )
        publish_task_progress(task_id, TaskStatus.AI_ANALYZING.value, 45)
        try:
            validated = fetch_assessment_result(
                document_text=body,
                filename=task.filename,
                task_id=task_id,
            )
        except DifyResultStructureError as exc:
            _log.warning(
                'Dify workflow returned unstructured result task_id=%s error=%s',
                task_id,
                exc,
            )
            review_result = _build_needs_review_result(exc)
            _mark_status(
                dao,
                task_id=task_id,
                status=TaskStatus.VALIDATING,
                progress=82,
                started_at=started_at,
                message='校验结构化结果',
            )
            publish_task_progress(task_id, TaskStatus.VALIDATING.value, 82)
            _mark_status(
                dao,
                task_id=task_id,
                status=TaskStatus.PERSISTING,
                progress=94,
                started_at=started_at,
                message='保存待复核结果',
            )
            publish_task_progress(task_id, TaskStatus.PERSISTING.value, 94)
            error_message = str(exc)[:2000]
            dao.save_result(
                task_id=task_id,
                result=review_result,
                status=TaskStatus.NEEDS_REVIEW,
                error_message=error_message,
            )
            dao.append_timeline_event(
                task_id=task_id,
                status=TaskStatus.NEEDS_REVIEW,
                progress=100,
                message='模型返回未结构化，需人工复核',
                elapsed_ms=int((time.perf_counter() - started_at) * 1000),
            )
            publish_task_progress(task_id, TaskStatus.NEEDS_REVIEW.value, 100, error_message[:500])
            return

        _mark_status(
            dao,
            task_id=task_id,
            status=TaskStatus.VALIDATING,
            progress=82,
            started_at=started_at,
            message='校验结构化结果',
        )
        publish_task_progress(task_id, TaskStatus.VALIDATING.value, 82)
        _mark_status(
            dao,
            task_id=task_id,
            status=TaskStatus.PERSISTING,
            progress=94,
            started_at=started_at,
            message='保存评价结果',
        )
        publish_task_progress(task_id, TaskStatus.PERSISTING.value, 94)
        dao.save_result(task_id=task_id, result=validated)
        dao.append_timeline_event(
            task_id=task_id,
            status=TaskStatus.SUCCESS,
            progress=100,
            message='任务完成',
            elapsed_ms=int((time.perf_counter() - started_at) * 1000),
        )
        publish_task_progress(task_id, TaskStatus.SUCCESS.value, 100)
    except DifyWorkflowError as exc:
        _log.exception('Dify workflow call failed: task_id=%s', task_id)
        _mark_status(
            dao,
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=100,
            started_at=started_at,
            message='Dify 调用失败',
            error_message=str(exc)[:2000],
        )
        publish_task_progress(task_id, TaskStatus.FAILED.value, 100, str(exc)[:500])
    except Exception as exc:
        _log.exception('Assessment task failed: task_id=%s', task_id)
        _mark_status(
            dao,
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=100,
            started_at=started_at,
            message='任务执行失败',
            error_message=(str(exc) or 'Task execution failed; see worker logs for details')[:2000],
        )
        publish_task_progress(
            task_id,
            TaskStatus.FAILED.value,
            100,
            (str(exc) or 'Task execution failed')[:500],
        )
    finally:
        db.close()
        reset_trace_context(trace_token)
        reset_request_id(request_token)
