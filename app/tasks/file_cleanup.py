"""Celery Beat 定时任务：清理已软删除且超过保留期的上传文件。"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.logging_setup import get_logger
from app.dao.file_cleanup_dao import FileCleanupDAO
from app.tasks.worker import celery_app

_log = get_logger(__name__)


@celery_app.task(name='app.tasks.file_cleanup.cleanup_expired_uploads')
def cleanup_expired_uploads() -> dict[str, int]:
    """
    扫描已软删除且超过 upload_retention_days 的任务，删除对应磁盘文件并清空 file_path。
    每次最多处理 200 条，避免长事务。
    """
    db = SessionLocal()
    dao = FileCleanupDAO(db)
    deleted_count = 0
    skipped_count = 0
    try:
        expired = dao.fetch_expired_file_paths(
            retention_days=settings.upload_retention_days,
            batch_size=200,
        )
        if not expired:
            _log.info('文件清理：无过期文件需要处理')
            return {'deleted': 0, 'skipped': 0}

        for task_id, file_path in expired:
            path = Path(file_path)
            try:
                if path.is_file():
                    path.unlink()
                    deleted_count += 1
                    _log.info('已删除过期文件: %s (task_id=%s)', file_path, task_id)
                else:
                    skipped_count += 1
                dao.clear_file_path(task_id)
            except OSError as exc:
                _log.warning('删除文件失败: %s, 原因: %s', file_path, exc)
                skipped_count += 1

        _log.info('文件清理完成: deleted=%d, skipped=%d', deleted_count, skipped_count)
    finally:
        db.close()

    return {'deleted': deleted_count, 'skipped': skipped_count}
