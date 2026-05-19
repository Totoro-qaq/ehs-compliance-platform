from __future__ import annotations

import sys
from pathlib import Path

from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging_setup import configure_logging, get_logger
from app.core.request_context import reset_request_id, set_request_id
from app.core.sse_broker import publish_task_progress
from app.dao.assessment_dao import AssessmentDAO
from app.models.db_models import TaskStatus
from app.services.dify_service import DifyWorkflowError, fetch_assessment_result
from app.services.pdf_text_service import DocumentTextExtractError, extract_text_from_document_file

_log = get_logger(__name__)


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

# Windows defaults to prefork, which is fragile for this project. Use solo by default.
if sys.platform == 'win32':
    celery_app.conf.worker_pool = 'solo'

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


@celery_app.task(name='app.tasks.worker.run_assessment_task')
def run_assessment_task(task_id: str, request_id: str | None = None) -> None:
    request_token = set_request_id(request_id)
    db = SessionLocal()
    dao = AssessmentDAO(db)
    try:
        task = dao.get_by_id(task_id)
        if task is None:
            _log.warning('Assessment task does not exist: task_id=%s', task_id)
            return

        dao.update_status(task_id=task_id, status=TaskStatus.PARSING, progress=12)
        publish_task_progress(task_id, TaskStatus.PARSING.value, 12)
        body = _load_body_text(task_id, task.file_path, task.filename, task.parsed_text, dao)
        if not body:
            raise RuntimeError(
                'No usable document text was extracted. Upload a text-bearing PDF/TXT/DOCX/DOC/CSV file, '
                'or ensure parsed_text is already present in the database.'
            )

        dao.update_status(task_id=task_id, status=TaskStatus.AI_ANALYZING, progress=45)
        publish_task_progress(task_id, TaskStatus.AI_ANALYZING.value, 45)
        validated = fetch_assessment_result(
            document_text=body,
            filename=task.filename,
            task_id=task_id,
        )

        dao.update_status(task_id=task_id, status=TaskStatus.VALIDATING, progress=82)
        publish_task_progress(task_id, TaskStatus.VALIDATING.value, 82)
        dao.update_status(task_id=task_id, status=TaskStatus.PERSISTING, progress=94)
        publish_task_progress(task_id, TaskStatus.PERSISTING.value, 94)
        dao.save_result(task_id=task_id, result=validated)
        publish_task_progress(task_id, TaskStatus.SUCCESS.value, 100)
    except DifyWorkflowError as exc:
        _log.exception('Dify workflow call failed: task_id=%s', task_id)
        dao.update_status(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=100,
            error_message=str(exc)[:2000],
        )
        publish_task_progress(task_id, TaskStatus.FAILED.value, 100, str(exc)[:500])
    except Exception as exc:
        _log.exception('Assessment task failed: task_id=%s', task_id)
        dao.update_status(
            task_id=task_id,
            status=TaskStatus.FAILED,
            progress=100,
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
        reset_request_id(request_token)
