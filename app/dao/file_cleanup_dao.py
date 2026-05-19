"""DAO：查询已软删除且超过保留期的任务文件路径。"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.db_models import AssessmentTask


class FileCleanupDAO:
    def __init__(self, session: Session) -> None:
        self.session = session

    def fetch_expired_file_paths(self, retention_days: int, batch_size: int = 200) -> list[tuple[str, str]]:
        """
        返回已软删除且超过保留天数的任务 (task_id, file_path) 列表。
        仅返回 file_path 非空的记录。
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        stmt = (
            select(AssessmentTask.id, AssessmentTask.file_path)
            .where(
                AssessmentTask.deleted_at.isnot(None),
                AssessmentTask.deleted_at < cutoff,
                AssessmentTask.file_path.isnot(None),
                AssessmentTask.file_path != '',
            )
            .execution_options(include_deleted=True)
            .limit(batch_size)
        )
        rows = self.session.execute(stmt).all()
        return [(str(r[0]), str(r[1])) for r in rows]

    def clear_file_path(self, task_id: str) -> None:
        """文件删除后将 file_path 置空，防止重复清理。"""
        task = self.session.get(AssessmentTask, task_id, options=[], execution_options={'include_deleted': True})
        if task is not None:
            task.file_path = ''
            self.session.commit()
