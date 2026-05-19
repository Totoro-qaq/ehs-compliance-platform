"""ORM 基类：主键、时间戳、软删除字段。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import new_uuid_str


class Base(DeclarativeBase):
    pass


_SHANGHAI = ZoneInfo('Asia/Shanghai')


def audit_now_naive() -> datetime:
    """库表审计时间：北京时间（Asia/Shanghai）墙钟，naive DATETIME 入库。"""
    return datetime.now(_SHANGHAI).replace(tzinfo=None)


class ModelBase(Base):
    """所有业务表的抽象基类；软删过滤通过 Session 级事件统一附加。"""

    __abstract__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid_str)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=audit_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=audit_now_naive,
        onupdate=audit_now_naive,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
