import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import (
    AssessmentTask,
    AssessmentTimelineEvent,
    TaskStatus,
    check_status_transition,
)
from app.schemas.ehs_schema import EHSAssessmentResult


class AssessmentDAO(BaseRepository[AssessmentTask]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AssessmentTask)

    def create_task(
        self,
        *,
        organization_id: str,
        filename: str,
        task_name: str | None,
        content_type: str,
        file_path: str,
        created_by_id: str | None = None,
    ) -> AssessmentTask:
        task = AssessmentTask(
            organization_id=organization_id,
            task_name=task_name,
            filename=filename,
            content_type=content_type,
            file_path=file_path,
            status=TaskStatus.PENDING,
            progress=0,
            created_by_id=created_by_id,
        )
        return self.save_and_refresh(task)

    def append_timeline_event(
        self,
        *,
        task_id: str,
        status: TaskStatus,
        progress: int,
        message: str | None = None,
        elapsed_ms: int | None = None,
    ) -> AssessmentTimelineEvent:
        event = AssessmentTimelineEvent(
            task_id=task_id,
            status=status,
            progress=progress,
            message=message,
            elapsed_ms=elapsed_ms,
        )
        self.session.add(event)
        self.session.commit()
        self.session.refresh(event)
        return event

    def list_timeline_events(self, task_id: str) -> list[AssessmentTimelineEvent]:
        stmt = (
            select(AssessmentTimelineEvent)
            .where(AssessmentTimelineEvent.task_id == task_id)
            .order_by(AssessmentTimelineEvent.created_at.asc(), AssessmentTimelineEvent.id.asc())
        )
        return list(self.session.scalars(stmt).all())

    def clear_timeline_events(self, task_id: str) -> None:
        self.session.execute(
            delete(AssessmentTimelineEvent).where(AssessmentTimelineEvent.task_id == task_id)
        )
        self.session.commit()

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
        self.clear_timeline_events(task_id)
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
