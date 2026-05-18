from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.core.config import settings
from app.models.base import Base, ModelBase


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    class_=Session,
    expire_on_commit=False,
)


@event.listens_for(Session, 'do_orm_execute', propagate=True)
def _apply_soft_delete_loader_criteria(orm_execute_state: ORMExecuteState) -> None:
    """
    隐式软删：对所有继承 ModelBase 的实体，SELECT 自动加 deleted_at IS NULL。
    需要包含已删数据时：session.execute(stmt, execution_options={'include_deleted': True})
    选用 do_orm_execute + with_loader_criteria 的原因：
    - SQLAlchemy 2.0 已无全局 Query 钩子，Session 事件是官方推荐的横切点；
    - 比手写 BaseQuery 兼容 Core/ORM 混合语句，且可 propagate 到 relationship 懒加载。
    """
    if not orm_execute_state.is_select:
        return
    if orm_execute_state.execution_options.get('include_deleted', False):
        return
    orm_execute_state.statement = orm_execute_state.statement.options(
        with_loader_criteria(
            ModelBase,
            lambda cls: cls.deleted_at.is_(None),
            propagate_to_loaders=True,
            track_closure_variables=False,
        )
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
