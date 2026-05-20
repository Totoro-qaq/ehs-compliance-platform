from __future__ import annotations

from enum import Enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ModelBase


class AccountRole(str, Enum):
    ADMIN = 'ADMIN'
    USER = 'USER'


class TaskStatus(str, Enum):
    PENDING = 'PENDING'
    PARSING = 'PARSING'
    AI_ANALYZING = 'AI_ANALYZING'
    VALIDATING = 'VALIDATING'
    PERSISTING = 'PERSISTING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'


# 合法的状态跳转（任何状态均可跳到 FAILED）
_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.PARSING, TaskStatus.FAILED}),
    TaskStatus.PARSING: frozenset({TaskStatus.AI_ANALYZING, TaskStatus.FAILED}),
    TaskStatus.AI_ANALYZING: frozenset({TaskStatus.VALIDATING, TaskStatus.FAILED}),
    TaskStatus.VALIDATING: frozenset({TaskStatus.PERSISTING, TaskStatus.FAILED}),
    TaskStatus.PERSISTING: frozenset({TaskStatus.SUCCESS, TaskStatus.FAILED}),
    TaskStatus.SUCCESS: frozenset(),
    TaskStatus.FAILED: frozenset(),
}


def check_status_transition(current: TaskStatus, target: TaskStatus) -> None:
    """校验状态跳转合法性，非法时抛 ValueError。"""
    allowed = _VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(f'非法状态跳转: {current.value} → {target.value}')


class Account(ModelBase):
    """B 端登录账号（密码仅存哈希）。"""

    __tablename__ = 'accounts'

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AccountRole] = mapped_column(
        SAEnum(AccountRole), nullable=False, default=AccountRole.USER
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=True,
        index=True,
    )
    # 注册必填；历史/bootstrap 管理员可为空。库层唯一（MySQL 允许多条 NULL）
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)


class Organization(ModelBase):
    __tablename__ = 'organizations'

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    tasks: Mapped[list['AssessmentTask']] = relationship(back_populates='organization')


class AssessmentTask(ModelBase):
    __tablename__ = 'assessment_tasks'

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 文本型 PDF / 后续格式解析后的正文摘录（大文本注意库表体量）
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('accounts.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    organization: Mapped[Organization] = relationship(back_populates='tasks')
    timeline_events: Mapped[list['AssessmentTimelineEvent']] = relationship(
        back_populates='task',
        cascade='all, delete-orphan',
        order_by='AssessmentTimelineEvent.created_at',
    )


class AssessmentTimelineEvent(ModelBase):
    __tablename__ = 'assessment_timeline_events'

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('assessment_tasks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    task: Mapped[AssessmentTask] = relationship(back_populates='timeline_events')
