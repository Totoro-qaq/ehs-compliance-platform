from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.dao.standard_library_dao import StandardChunkDAO, StandardDocumentDAO
from app.models.base import audit_now_naive
from app.models.db_models import AccountRole, StandardChunk
from app.schemas.auth_context import CurrentUser
from app.schemas.standard_schema import (
    StandardChunkOut,
    StandardChunkSearchResponse,
    StandardDocumentManifestItem,
    StandardManifestDocumentResult,
    StandardManifestImportRequest,
    StandardManifestImportResponse,
)
from app.services.access_control import ensure_admin


class StandardLibraryService:
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
            existing = document_dao.get_by_file_hash(item.file_hash)
            created = existing is None
            doc_fields = _document_fields(item)
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
                    'embedding_model': chunk.embedding_model or settings.standard_embedding_model or None,
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
        limit: int = 10,
    ) -> StandardChunkSearchResponse:
        effective_include_sensitive = include_sensitive and actor.role == AccountRole.ADMIN
        max_items = max(1, min(limit, 50))
        chunks = StandardChunkDAO(db).search(
            query=query,
            standard_code=standard_code,
            domain=domain,
            service_type=service_type,
            include_sensitive=effective_include_sensitive,
            limit=max_items,
        )
        return StandardChunkSearchResponse(
            query=(query or '').strip() or None,
            include_sensitive=effective_include_sensitive,
            items=[_chunk_out(item) for item in chunks],
            limit=max_items,
        )


def _document_fields(item: StandardDocumentManifestItem) -> dict[str, Any]:
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
    return {
        'standard_code': item.standard_code,
        'standard_name': item.standard_name,
        'domain': item.domain,
        'service_type': item.service_type,
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
