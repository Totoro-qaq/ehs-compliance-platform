from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import EHSException
from app.dao.standard_library_dao import StandardChunkDAO, StandardDocumentDAO, StandardSourceDAO
from app.models.base import audit_now_naive
from app.models.db_models import (
    StandardChunk,
    StandardDocument,
    StandardSource,
    StandardSourceReviewStatus,
    StandardSourceType,
)
from app.schemas.auth_context import CurrentUser
from app.schemas.standard_schema import (
    StandardChunkOut,
    StandardChunkSearchResponse,
    StandardDocumentManifestItem,
    StandardManifestDocumentResult,
    StandardManifestImportRequest,
    StandardManifestImportResponse,
    StandardSourceCreate,
    StandardSourceOut,
    StandardSourceReviewRequest,
)
from app.services.access_control import ensure_admin, ensure_user_has_organization, is_system_admin


class StandardLibraryService:
    @staticmethod
    def list_sources(
        *,
        db: Session,
        actor: CurrentUser,
        review_status: StandardSourceReviewStatus | None = None,
        source_type: StandardSourceType | None = None,
        limit: int = 100,
    ) -> list[StandardSourceOut]:
        ensure_admin(actor)
        sources = StandardSourceDAO(db).list_sources(
            review_status=review_status,
            source_type=source_type,
            limit=limit,
        )
        return [_source_out(item) for item in sources]

    @staticmethod
    def create_source(
        *,
        db: Session,
        actor: CurrentUser,
        payload: StandardSourceCreate,
    ) -> StandardSourceOut:
        ensure_admin(actor)
        source = StandardSourceDAO(db).create_source(fields=_source_create_fields(payload))
        db.commit()
        db.refresh(source)
        return _source_out(source)

    @staticmethod
    def review_source(
        *,
        db: Session,
        actor: CurrentUser,
        source_id: str,
        payload: StandardSourceReviewRequest,
    ) -> StandardSourceOut:
        ensure_admin(actor)
        source = StandardSourceDAO(db).get_by_id(source_id)
        if source is None:
            raise EHSException(
                'Standard source not found',
                code='STANDARD_SOURCE_NOT_FOUND',
                status_code=404,
            )

        _apply_source_review(source=source, payload=payload, actor=actor)
        for document in StandardDocumentDAO(db).list_by_source_id(source.id):
            _apply_document_authorization(document=document, source=source)
        db.commit()
        db.refresh(source)
        return _source_out(source)

    @staticmethod
    def import_manifest(
        *,
        db: Session,
        actor: CurrentUser,
        payload: StandardManifestImportRequest,
    ) -> StandardManifestImportResponse:
        ensure_admin(actor)

        document_dao = StandardDocumentDAO(db)
        chunk_dao = StandardChunkDAO(db)
        results: list[StandardManifestDocumentResult] = []
        documents_created = 0
        documents_updated = 0
        chunks_written_total = 0
        chunks_skipped_total = 0

        for item in payload.documents:
            source = _load_manifest_source(db=db, item=item)
            existing = document_dao.get_by_file_hash(item.file_hash)
            created = existing is None
            doc_fields = _document_fields(item, source=source)
            document = document_dao.upsert_by_file_hash(file_hash=item.file_hash, fields=doc_fields)
            if created:
                documents_created += 1
            else:
                documents_updated += 1

            if payload.replace_chunks:
                chunk_dao.clear_for_document(document.id)

            chunks_written = 0
            chunks_skipped = 0
            for chunk in item.chunks:
                chunk_is_sensitive = bool(item.is_sensitive or chunk.is_sensitive)
                if chunk_is_sensitive and not payload.allow_sensitive_chunks:
                    chunks_skipped += 1
                    continue

                text_hash = chunk.text_hash or _sha256_text(chunk.text_chunk)
                chunk_id = chunk.chunk_id or _chunk_id(
                    file_hash=item.file_hash,
                    chunk_index=chunk.chunk_index,
                    text_hash=text_hash,
                )
                fields = {
                    'document_id': document.id,
                    'chunk_index': chunk.chunk_index,
                    'standard_code': item.standard_code,
                    'standard_name': item.standard_name,
                    'clause': chunk.clause,
                    'domain': item.domain,
                    'service_type': item.service_type,
                    'effective_from': item.effective_from,
                    'effective_to': item.effective_to,
                    'text_chunk': chunk.text_chunk,
                    'text_hash': text_hash,
                    'page_start': chunk.page_start,
                    'page_end': chunk.page_end,
                    'is_sensitive': 1 if chunk_is_sensitive else 0,
                    'milvus_collection': chunk.milvus_collection
                    or (settings.milvus_collection if chunk.milvus_id else None),
                    'milvus_id': chunk.milvus_id,
                    'embedding_model': chunk.embedding_model
                    or settings.standard_embedding_model
                    or None,
                    'indexed_at': audit_now_naive() if chunk.milvus_id else None,
                    'metadata_json': _json_or_none(chunk.metadata),
                }
                chunk_dao.upsert_by_chunk_id(chunk_id=chunk_id, fields=fields)
                chunks_written += 1

            chunks_written_total += chunks_written
            chunks_skipped_total += chunks_skipped
            results.append(
                StandardManifestDocumentResult(
                    document_id=document.id,
                    standard_code=document.standard_code,
                    file_hash=document.file_hash,
                    source_id=document.source_id,
                    source_review_status=_coerce_review_status(document.source_review_status),
                    allow_ai_retrieval=bool(document.allow_ai_retrieval),
                    created=created,
                    chunks_written=chunks_written,
                    chunks_skipped_sensitive=chunks_skipped,
                )
            )

        db.commit()

        return StandardManifestImportResponse(
            documents_total=len(payload.documents),
            documents_created=documents_created,
            documents_updated=documents_updated,
            chunks_written=chunks_written_total,
            chunks_skipped_sensitive=chunks_skipped_total,
            documents=results,
        )

    @staticmethod
    def search_chunks(
        *,
        db: Session,
        actor: CurrentUser,
        query: str | None,
        standard_code: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        include_sensitive: bool = False,
        include_unapproved: bool = False,
        limit: int = 10,
    ) -> StandardChunkSearchResponse:
        effective_include_sensitive = include_sensitive and is_system_admin(actor)
        effective_include_unapproved = include_unapproved and is_system_admin(actor)
        visible_organization_id = (
            None if is_system_admin(actor) else ensure_user_has_organization(actor)
        )
        max_items = max(1, min(limit, 50))
        chunks = StandardChunkDAO(db).search(
            query=query,
            standard_code=standard_code,
            domain=domain,
            service_type=service_type,
            visible_organization_id=visible_organization_id,
            authorized_only=not effective_include_unapproved,
            include_sensitive=effective_include_sensitive,
            limit=max_items,
        )
        return StandardChunkSearchResponse(
            query=(query or '').strip() or None,
            include_sensitive=effective_include_sensitive,
            include_unapproved=effective_include_unapproved,
            items=[_chunk_out(item) for item in chunks],
            limit=max_items,
        )


def _source_create_fields(payload: StandardSourceCreate) -> dict[str, Any]:
    return {
        'source_name': payload.source_name.strip(),
        'source_type': payload.source_type,
        'provider_name': _strip_or_none(payload.provider_name),
        'license_no': _strip_or_none(payload.license_no),
        'license_scope': _strip_or_none(payload.license_scope),
        'organization_id': _strip_or_none(payload.organization_id),
        'allow_storage': 1 if payload.allow_storage else 0,
        'allow_vectorization': 1 if payload.allow_vectorization else 0,
        'allow_ai_retrieval': 1 if payload.allow_ai_retrieval else 0,
        'allow_excerpt_export': 1 if payload.allow_excerpt_export else 0,
        'effective_from': payload.effective_from,
        'effective_to': payload.effective_to,
        'review_status': StandardSourceReviewStatus.PENDING,
        'notes': _strip_or_none(payload.notes),
    }


def _apply_source_review(
    *,
    source: StandardSource,
    payload: StandardSourceReviewRequest,
    actor: CurrentUser,
) -> None:
    for field in (
        'allow_storage',
        'allow_vectorization',
        'allow_ai_retrieval',
        'allow_excerpt_export',
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(source, field, 1 if value else 0)
    if 'effective_from' in payload.model_fields_set:
        source.effective_from = payload.effective_from
    if 'effective_to' in payload.model_fields_set:
        source.effective_to = payload.effective_to
    if payload.notes is not None:
        source.notes = payload.notes.strip() or None

    source.review_status = payload.review_status
    if payload.review_status in {
        StandardSourceReviewStatus.REJECTED,
        StandardSourceReviewStatus.EXPIRED,
    }:
        source.allow_storage = 0
        source.allow_vectorization = 0
        source.allow_ai_retrieval = 0
        source.allow_excerpt_export = 0
    source.reviewed_by_id = actor.account_id
    source.reviewed_at = audit_now_naive()
    source.updated_at = audit_now_naive()


def _load_manifest_source(
    *, db: Session, item: StandardDocumentManifestItem
) -> StandardSource | None:
    if not item.source_id:
        return None
    source = StandardSourceDAO(db).get_by_id(item.source_id)
    if source is None:
        raise EHSException(
            'Standard source not found',
            code='STANDARD_SOURCE_NOT_FOUND',
            status_code=400,
            details={'source_id': item.source_id},
        )
    _ensure_source_allows_storage(source)
    return source


def _ensure_source_allows_storage(source: StandardSource) -> None:
    status = _source_effective_status(source)
    if status in {StandardSourceReviewStatus.REJECTED, StandardSourceReviewStatus.EXPIRED}:
        raise EHSException(
            'Standard source is not valid for storage',
            code='STANDARD_SOURCE_STORAGE_FORBIDDEN',
            status_code=400,
            details={'source_id': source.id, 'review_status': status.value},
        )
    if not bool(source.allow_storage):
        raise EHSException(
            'Standard source does not allow storage',
            code='STANDARD_SOURCE_STORAGE_FORBIDDEN',
            status_code=400,
            details={'source_id': source.id},
        )


def _document_fields(
    item: StandardDocumentManifestItem, *, source: StandardSource | None
) -> dict[str, Any]:
    storage_backend = item.storage_backend.strip().lower() or 'minio'
    bucket = item.bucket or (settings.minio_bucket if storage_backend == 'minio' else None)
    object_key = _clean_object_key(item.object_key)
    source_path = item.source_path or _source_path(
        storage_backend=storage_backend,
        bucket=bucket,
        object_key=object_key,
        standard_code=item.standard_code,
        file_hash=item.file_hash,
    )
    source_filename = item.source_filename or _source_filename(
        object_key=object_key,
        source_path=source_path,
        standard_code=item.standard_code,
        source_format=item.source_format,
    )
    source_format = item.source_format or _suffix(source_filename)
    authorization = _document_authorization_fields(source=source)
    return {
        'standard_code': item.standard_code,
        'standard_name': item.standard_name,
        'domain': item.domain,
        'service_type': item.service_type,
        'organization_id': source.organization_id if source is not None else None,
        'source_id': source.id if source is not None else None,
        'license_id': item.license_id or (source.license_no if source is not None else None),
        **authorization,
        'storage_backend': storage_backend,
        'bucket': bucket,
        'object_key': object_key,
        'object_version': item.object_version,
        'source_path': source_path,
        'source_filename': source_filename,
        'source_format': source_format,
        'file_size_bytes': item.file_size_bytes,
        'version': item.version,
        'effective_from': item.effective_from,
        'effective_to': item.effective_to,
        'status': item.status.strip().upper() or 'ACTIVE',
        'is_sensitive': 1 if item.is_sensitive else 0,
        'metadata_json': _json_or_none(item.metadata),
    }


def _document_authorization_fields(*, source: StandardSource | None) -> dict[str, Any]:
    if source is None:
        return {
            'source_review_status': StandardSourceReviewStatus.PENDING,
            'allow_ai_retrieval': 0,
            'allow_excerpt_export': 0,
        }
    status = _source_effective_status(source)
    approved = status == StandardSourceReviewStatus.APPROVED
    return {
        'source_review_status': status,
        'allow_ai_retrieval': 1 if approved and bool(source.allow_ai_retrieval) else 0,
        'allow_excerpt_export': 1 if approved and bool(source.allow_excerpt_export) else 0,
    }


def _apply_document_authorization(*, document: StandardDocument, source: StandardSource) -> None:
    fields = _document_authorization_fields(source=source)
    document.source_review_status = fields['source_review_status']
    document.allow_ai_retrieval = fields['allow_ai_retrieval']
    document.allow_excerpt_export = fields['allow_excerpt_export']
    document.license_id = document.license_id or source.license_no
    document.organization_id = source.organization_id
    document.updated_at = audit_now_naive()


def _clean_object_key(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lstrip('/')


def _source_path(
    *,
    storage_backend: str,
    bucket: str | None,
    object_key: str | None,
    standard_code: str,
    file_hash: str,
) -> str:
    if storage_backend == 'minio' and bucket and object_key:
        return f'minio://{bucket}/{object_key}'
    return f'manifest://{standard_code}/{file_hash}'


def _source_filename(
    *,
    object_key: str | None,
    source_path: str,
    standard_code: str,
    source_format: str | None,
) -> str:
    if object_key:
        return PurePosixPath(object_key).name[:255]
    if source_path:
        candidate = PurePosixPath(source_path).name or PureWindowsPath(source_path).name
        if candidate and candidate != source_path:
            return candidate[:255]
    suffix = f'.{source_format.lstrip(".")}' if source_format else ''
    return f'{standard_code}{suffix}'[:255]


def _suffix(filename: str) -> str | None:
    suffix = PurePosixPath(filename).suffix.lower().lstrip('.')
    return suffix or None


def _json_or_none(value: dict[str, Any]) -> str | None:
    if not value:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _chunk_id(*, file_hash: str, chunk_index: int, text_hash: str) -> str:
    raw = f'{file_hash}:{chunk_index}:{text_hash}'
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:24]
    return f'std-chunk-{digest}'


def _chunk_out(item: StandardChunk) -> StandardChunkOut:
    document = item.document
    source_review_status = _document_source_status(document)
    authorized = _document_authorized(document)
    return StandardChunkOut(
        id=item.id,
        document_id=item.document_id,
        chunk_id=item.chunk_id,
        chunk_index=item.chunk_index,
        standard_code=item.standard_code,
        standard_name=item.standard_name,
        clause=item.clause,
        domain=item.domain,
        service_type=item.service_type,
        organization_id=document.organization_id if document is not None else None,
        source_id=document.source_id if document is not None else None,
        license_id=document.license_id if document is not None else None,
        source_review_status=source_review_status,
        authorized=authorized,
        allow_ai_retrieval=authorized,
        allow_excerpt_export=_document_allows_excerpt_export(document),
        text_chunk=item.text_chunk,
        text_hash=item.text_hash,
        page_start=item.page_start,
        page_end=item.page_end,
        is_sensitive=bool(item.is_sensitive),
        milvus_collection=item.milvus_collection,
        milvus_id=item.milvus_id,
        embedding_model=item.embedding_model,
        indexed_at=item.indexed_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _source_out(source: StandardSource) -> StandardSourceOut:
    return StandardSourceOut(
        id=source.id,
        source_name=source.source_name,
        source_type=source.source_type,
        provider_name=source.provider_name,
        license_no=source.license_no,
        license_scope=source.license_scope,
        organization_id=source.organization_id,
        allow_storage=bool(source.allow_storage),
        allow_vectorization=bool(source.allow_vectorization),
        allow_ai_retrieval=bool(source.allow_ai_retrieval),
        allow_excerpt_export=bool(source.allow_excerpt_export),
        effective_from=source.effective_from,
        effective_to=source.effective_to,
        review_status=_source_effective_status(source),
        reviewed_by_id=source.reviewed_by_id,
        reviewed_at=source.reviewed_at,
        notes=source.notes,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _document_authorized(document: StandardDocument | None) -> bool:
    if document is None or not document.source_id or not bool(document.allow_ai_retrieval):
        return False
    if document.source is not None:
        return _source_allows_ai_retrieval(document.source)
    return (
        _coerce_review_status(document.source_review_status) == StandardSourceReviewStatus.APPROVED
    )


def _document_allows_excerpt_export(document: StandardDocument | None) -> bool:
    if document is None or not document.source_id or not bool(document.allow_excerpt_export):
        return False
    if document.source is not None:
        return _source_effective_status(
            document.source
        ) == StandardSourceReviewStatus.APPROVED and bool(document.source.allow_excerpt_export)
    return (
        _coerce_review_status(document.source_review_status) == StandardSourceReviewStatus.APPROVED
    )


def _source_allows_ai_retrieval(source: StandardSource) -> bool:
    return _source_effective_status(source) == StandardSourceReviewStatus.APPROVED and bool(
        source.allow_ai_retrieval
    )


def _document_source_status(document: StandardDocument | None) -> StandardSourceReviewStatus:
    if document is None:
        return StandardSourceReviewStatus.PENDING
    if document.source is not None:
        return _source_effective_status(document.source)
    return _coerce_review_status(document.source_review_status)


def _source_effective_status(source: StandardSource) -> StandardSourceReviewStatus:
    status = _coerce_review_status(source.review_status)
    if status != StandardSourceReviewStatus.APPROVED:
        return status
    today = audit_now_naive().date()
    if source.effective_from is not None and source.effective_from > today:
        return StandardSourceReviewStatus.EXPIRED
    if source.effective_to is not None and source.effective_to < today:
        return StandardSourceReviewStatus.EXPIRED
    return status


def _coerce_review_status(value: Any) -> StandardSourceReviewStatus:
    if isinstance(value, StandardSourceReviewStatus):
        return value
    try:
        return StandardSourceReviewStatus(str(value))
    except ValueError:
        return StandardSourceReviewStatus.PENDING


def _strip_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None
