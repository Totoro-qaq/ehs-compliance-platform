from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.dao.pagination import (
    apply_where_clauses,
    fetch_scalar_rows_page,
    normalize_page_params,
)
from app.models.base import ModelBase, audit_now_naive

T = TypeVar('T', bound=ModelBase)


class BaseRepository(Generic[T]):
    """通用增删改查（软删），大数据量列表统一走分页。"""

    def __init__(self, session: Session, model: type[T]) -> None:
        self.session = session
        self.model = model

    def save_and_refresh(self, entity: T) -> T:
        self.session.add(entity)
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def get_by_id(self, entity_id: str) -> T | None:
        return self.session.get(self.model, entity_id)

    def get_by_id_include_deleted(self, entity_id: str) -> T | None:
        stmt = select(self.model).where(self.model.id == entity_id)
        return self.session.scalars(
            stmt,
            execution_options={'include_deleted': True},
        ).one_or_none()

    def list_page(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        filters: Sequence[ColumnElement[bool]] = (),
        order_by: Sequence[ColumnElement[Any]] | None = None,
        include_deleted: bool = False,
        max_page_size: int | None = None,
    ) -> tuple[list[T], int]:
        np_kw: dict[str, int] = {}
        if max_page_size is not None:
            np_kw['max_page_size'] = max_page_size
        params = normalize_page_params(page=page, page_size=page_size, **np_kw)

        stmt: Select[Any] = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)
        stmt, count_stmt = apply_where_clauses(stmt, count_stmt, filters)

        if order_by:
            stmt = stmt.order_by(*order_by)
        else:
            stmt = stmt.order_by(self.model.created_at.desc())

        exec_opts = {'include_deleted': True} if include_deleted else {}
        rows, total = fetch_scalar_rows_page(
            self.session,
            list_stmt=stmt,
            count_stmt=count_stmt,
            params=params,
            execution_options=exec_opts or None,
        )
        return rows, total

    def update_by_id(self, entity_id: str, **fields: Any) -> T | None:
        entity = self.get_by_id(entity_id)
        if entity is None:
            return None
        for key, value in fields.items():
            setattr(entity, key, value)
        if 'updated_at' not in fields:
            entity.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(entity)
        return entity

    def soft_delete_by_id(self, entity_id: str) -> bool:
        entity = self.get_by_id(entity_id)
        if entity is None:
            return False
        now = audit_now_naive()
        entity.deleted_at = now
        entity.updated_at = now
        self.session.commit()
        return True

    def restore_soft_deleted(self, entity_id: str) -> bool:
        entity = self.get_by_id_include_deleted(entity_id)
        if entity is None:
            return False
        if entity.deleted_at is None:
            return True
        entity.deleted_at = None
        entity.updated_at = audit_now_naive()
        self.session.commit()
        self.session.refresh(entity)
        return True
