import json

from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import AssessmentTask, TaskStatus, check_status_transition
from app.schemas.ehs_schema import EHSAssessmentResult


class AssessmentDAO(BaseRepository[AssessmentTask]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AssessmentTask)

    def create_task(
        self,
        *,
        organization_id: str,
        filename: str,
        content_type: str,
        file_path: str,
        created_by_id: str | None = None,
    ) -> AssessmentTask:
        task = AssessmentTask(
            organization_id=organization_id,
            filename=filename,
            content_type=content_type,
            file_path=file_path,
            status=TaskStatus.PENDING,
            progress=0,
            created_by_id=created_by_id,
        )
        return self.save_and_refresh(task)

    def update_status(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        progress: int,
        error_message: str | None = None,
    ) -> AssessmentTask | None:
        task = self.get_by_id(task_id)
        if task is None:
            return None
        check_status_transition(task.status, status)
        fields: dict = {'status': status, 'progress': progress, 'error_message': error_message}
        return self.update_by_id(task_id, **fields)

    def reset_failed_for_requeue(self, *, task_id: str) -> AssessmentTask | None:
        task = self.get_by_id(task_id)
        if task is None:
            return None
        task.status = TaskStatus.PENDING
        task.progress = 0
        task.error_message = None
        task.result_json = None
        task.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(task)
        return task

    def save_result(self, *, task_id: str, result: EHSAssessmentResult) -> AssessmentTask | None:
        task = self.get_by_id(task_id)
        if task is None:
            return None
        task.status = TaskStatus.SUCCESS
        task.progress = 100
        task.result_json = json.dumps(result.model_dump(), ensure_ascii=False)
        task.error_message = None
        task.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(task)
        return task
