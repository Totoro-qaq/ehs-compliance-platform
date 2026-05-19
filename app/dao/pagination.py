"""
内部分页辅助：统一页码、每页条数、offset/limit 与 Session 执行方式。
后续改默认上限、游标分页、或统一审计钩子时可只改此模块。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200
MIN_PAGE_SIZE = 1
MIN_PAGE = 1


@dataclass(frozen=True, slots=True)
class PageParams:
    """规范化后的分页参数。"""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def normalize_page_params(
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    *,
    max_page_size: int = MAX_PAGE_SIZE,
    min_page_size: int = MIN_PAGE_SIZE,
    min_page: int = MIN_PAGE,
) -> PageParams:
    """将外部传入的 page / page_size 收紧到合法区间。"""
    p = max(min_page, page)
    ps = min(max(min_page_size, page_size), max_page_size)
    return PageParams(page=p, page_size=ps)


def apply_where_clauses(
    list_stmt: Select[Any],
    count_stmt: Select[Any],
    filters: Sequence[ColumnElement[bool]],
) -> tuple[Select[Any], Select[Any]]:
    """对列表查询与 count 查询应用同一组 WHERE，避免条件漂移。"""
    for cond in filters:
        list_stmt = list_stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    return list_stmt, count_stmt


def fetch_scalar_rows_page(
    session: Session,
    *,
    list_stmt: Select[Any],
    count_stmt: Select[Any],
    params: PageParams,
    execution_options: dict[str, Any] | None = None,
) -> tuple[list[Any], int]:
    """
    执行 count + 分页 select，返回 (行列表, total)。
    使用 scalars().all()，适用于 ORM select(entity) 行。
    """
    opts = execution_options if execution_options else {}
    total = int(session.execute(count_stmt, execution_options=opts).scalar_one())
    paged = list_stmt.offset(params.offset).limit(params.page_size)
    rows = list(session.execute(paged, execution_options=opts).scalars().all())
    return rows, total
