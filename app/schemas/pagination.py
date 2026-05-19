from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, computed_field

T = TypeVar('T')


class Page(BaseModel, Generic[T]):
    """统一分页响应。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T] = Field(description='当前页数据列表')
    total: int = Field(ge=0, description='符合条件的总条数')
    page: int = Field(ge=1, description='当前页码（从 1 起）')
    page_size: int = Field(ge=1, le=200, description='每页条数')

    @computed_field
    @property
    def pages(self) -> int:
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size
