from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.dao.base_repository import BaseRepository
from app.models.base import audit_now_naive
from app.models.db_models import (
    StandardChunk,
    StandardDocument,
    StandardSource,
    StandardSourceReviewStatus,
    StandardSourceType,
)


class StandardSourceDAO(BaseRepository[StandardSource]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardSource)

    def create_source(self, *, fields: dict[str, Any]) -> StandardSource:
        entity = StandardSource(**fields)
        self.session.add(entity)
        self.session.flush()
        return entity

    def list_sources(
        self,
        *,
        review_status: StandardSourceReviewStatus | None = None,
        source_type: StandardSourceType | None = None,
        limit: int = 100,
    ) -> list[StandardSource]:
        filters: list[Any] = []
        if review_status is not None:
            filters.append(StandardSource.review_status == review_status)
        if source_type is not None:
            filters.append(StandardSource.source_type == source_type)
        stmt = (
            select(StandardSource)
            .where(*filters)
            .order_by(StandardSource.updated_at.desc(), StandardSource.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        return list(self.session.scalars(stmt).all())


class StandardDocumentDAO(BaseRepository[StandardDocument]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardDocument)

    def get_by_file_hash(self, file_hash: str) -> StandardDocument | None:
        stmt = select(StandardDocument).where(StandardDocument.file_hash == file_hash)
        return self.session.scalars(stmt).one_or_none()

    def upsert_by_file_hash(self, *, file_hash: str, fields: dict[str, Any]) -> StandardDocument:
        existing = self.get_by_file_hash(file_hash)
        if existing is not None:
            for key, value in fields.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = audit_now_naive()
            self.session.flush()
            return existing

        entity = StandardDocument(file_hash=file_hash, **fields)
        self.session.add(entity)
        self.session.flush()
        return entity

    def list_by_source_id(self, source_id: str) -> list[StandardDocument]:
        stmt = select(StandardDocument).where(StandardDocument.source_id == source_id)
        return list(self.session.scalars(stmt).all())


class StandardChunkDAO(BaseRepository[StandardChunk]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, StandardChunk)

    def get_by_chunk_id(self, chunk_id: str) -> StandardChunk | None:
        stmt = select(StandardChunk).where(StandardChunk.chunk_id == chunk_id)
        return self.session.scalars(stmt).one_or_none()

    def clear_for_document(self, document_id: str) -> int:
        stmt = select(StandardChunk).where(StandardChunk.document_id == document_id)
        chunks = list(self.session.scalars(stmt).all())
        for chunk in chunks:
            self.session.delete(chunk)
        self.session.flush()
        return len(chunks)

    def upsert_by_chunk_id(self, *, chunk_id: str, fields: dict[str, Any]) -> StandardChunk:
        existing = self.get_by_chunk_id(chunk_id)
        if existing is not None:
            for key, value in fields.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)
            existing.updated_at = audit_now_naive()
            self.session.flush()
            return existing

        entity = StandardChunk(chunk_id=chunk_id, **fields)
        self.session.add(entity)
        self.session.flush()
        return entity

    def search(
        self,
        *,
        query: str | None,
        standard_code: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        visible_organization_id: str | None = None,
        authorized_only: bool = True,
        include_sensitive: bool = False,
        limit: int = 10,
    ) -> list[StandardChunk]:
        filters: list[Any] = []
        if visible_organization_id is not None:
            filters.append(
                or_(
                    StandardDocument.organization_id.is_(None),
                    StandardDocument.organization_id == visible_organization_id,
                )
            )
        if authorized_only:
            today = audit_now_naive().date()
            filters.extend(
                [
                    StandardDocument.source_id.is_not(None),
                    StandardDocument.source_review_status == StandardSourceReviewStatus.APPROVED,
                    StandardDocument.allow_ai_retrieval == 1,
                    StandardSource.review_status == StandardSourceReviewStatus.APPROVED,
                    StandardSource.allow_ai_retrieval == 1,
                    or_(
                        StandardSource.effective_from.is_(None),
                        StandardSource.effective_from <= today,
                    ),
                    or_(
                        StandardSource.effective_to.is_(None), StandardSource.effective_to >= today
                    ),
                ]
            )
        if not include_sensitive:
            filters.append(StandardChunk.is_sensitive == 0)
            filters.append(StandardDocument.is_sensitive == 0)
        if standard_code:
            filters.append(StandardChunk.standard_code == standard_code.strip())
        if domain:
            filters.append(StandardChunk.domain == domain.strip())
        if service_type:
            filters.append(StandardChunk.service_type == service_type.strip())

        terms = _query_terms(query)
        if terms:
            term_clauses: list[Any] = []
            for term in terms:
                like = f'%{term}%'
                term_clauses.extend(
                    [
                        StandardChunk.text_chunk.ilike(like),
                        StandardChunk.standard_code.ilike(like),
                        StandardChunk.standard_name.ilike(like),
                        StandardChunk.clause.ilike(like),
                    ]
                )
            filters.append(or_(*term_clauses))

        stmt = (
            select(StandardChunk)
            .join(StandardDocument, StandardDocument.id == StandardChunk.document_id)
            .join(
                StandardSource,
                StandardSource.id == StandardDocument.source_id,
                isouter=not authorized_only,
            )
            .options(joinedload(StandardChunk.document).joinedload(StandardDocument.source))
            .where(*filters)
            .order_by(
                StandardChunk.standard_code.asc(),
                StandardChunk.chunk_index.asc(),
                StandardChunk.updated_at.desc(),
            )
            .limit(max(1, min(limit, 50)))
        )
        return list(self.session.scalars(stmt).all())


def _query_terms(query: str | None) -> Sequence[str]:
    text = ' '.join((query or '').strip().split())
    if not text:
        return []
    terms: list[str] = []
    terms.extend(re.findall(r'[A-Za-z0-9][A-Za-z0-9./_-]{1,}', text))
    terms.extend(
        char for char in text if '\u4e00' <= char <= '\u9fff' and char not in _CJK_STOP_CHARS
    )
    if not terms:
        terms = [item for item in text.split(' ') if len(item) >= 2]

    unique: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique[:16] or [text[:80]]


_CJK_STOP_CHARS = set('的是了和与及或在为对把被请问什么哪个哪些一下一个这个那个如何怎么多少')
