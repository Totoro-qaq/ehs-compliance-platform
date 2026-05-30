from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.core.exceptions import EHSException
from app.services.rag.schemas import RagChunkOut, RagChunkSearchResponse, RagHealthResponse


class RagflowClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        dataset_ids: list[str],
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key.strip()
        self.dataset_ids = [item.strip() for item in dataset_ids if item.strip()]
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def healthcheck(self) -> RagHealthResponse:
        try:
            with self._client() as client:
                response = client.get('/api/v1/datasets', params={'page': 1, 'page_size': 1})
                self._ensure_success(response)
        except Exception as exc:
            return RagHealthResponse(
                configured=True,
                ok=False,
                base_url=self.base_url,
                dataset_ids=self.dataset_ids,
                error=f'{type(exc).__name__}: {exc}',
            )
        return RagHealthResponse(
            configured=True,
            ok=True,
            base_url=self.base_url,
            dataset_ids=self.dataset_ids,
        )

    def search_chunks(
        self,
        *,
        query: str,
        standard_code: str | None = None,
        clause: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        document_id: str | None = None,
        limit: int = 10,
    ) -> RagChunkSearchResponse:
        normalized_query = ' '.join(query.strip().split())
        if not normalized_query:
            raise EHSException(
                'RAGFlow query is required',
                code='RAGFLOW_QUERY_REQUIRED',
                status_code=400,
            )

        max_items = _normalize_limit(limit)
        payload = _retrieval_payload(
            query=normalized_query,
            dataset_ids=self.dataset_ids,
            standard_code=standard_code,
            clause=clause,
            domain=domain,
            service_type=service_type,
            document_id=document_id,
            limit=max_items,
        )
        with self._client() as client:
            response = client.post('/api/v1/retrieval', json=payload)
            data = self._json_data(response)

        chunks = [
            _chunk_out(item, default_dataset_id=self._default_dataset_id())
            for item in _response_chunks(data)
        ]
        authorized_chunks = [item for item in chunks if _retrieval_authorized(item)]
        return RagChunkSearchResponse(
            configured=True,
            query=normalized_query,
            dataset_ids=self.dataset_ids,
            items=authorized_chunks,
            blocked_count=len(chunks) - len(authorized_chunks),
            limit=max_items,
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
            },
            transport=self.transport,
        )

    def _json_data(self, response: httpx.Response) -> dict[str, Any]:
        self._ensure_success(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise EHSException(
                'RAGFlow returned invalid JSON',
                code='RAGFLOW_INVALID_RESPONSE',
                status_code=502,
            ) from exc
        if not isinstance(data, dict):
            raise EHSException(
                'RAGFlow returned invalid response',
                code='RAGFLOW_INVALID_RESPONSE',
                status_code=502,
            )
        code = data.get('code')
        if code not in (None, 0, '0', 200, '200'):
            raise EHSException(
                'RAGFlow request failed',
                code='RAGFLOW_REQUEST_FAILED',
                status_code=502,
                details={'ragflow_code': code, 'message': data.get('message') or data.get('msg')},
            )
        payload = data.get('data', data)
        return payload if isinstance(payload, dict) else {'items': payload}

    @staticmethod
    def _ensure_success(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EHSException(
                'RAGFlow HTTP request failed',
                code='RAGFLOW_HTTP_ERROR',
                status_code=502,
                details={'status_code': response.status_code, 'body': response.text[:500]},
            ) from exc

    def _default_dataset_id(self) -> str | None:
        return self.dataset_ids[0] if self.dataset_ids else None


def _retrieval_payload(
    *,
    query: str,
    dataset_ids: list[str],
    standard_code: str | None,
    clause: str | None,
    domain: str | None,
    service_type: str | None,
    document_id: str | None,
    limit: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'question': query,
        'dataset_ids': dataset_ids,
        'page': 1,
        'page_size': limit,
    }
    if document_id:
        payload['document_ids'] = [document_id.strip()]

    filters = _drop_empty(
        {
            'standard_code': standard_code,
            'clause': clause,
            'domain': domain,
            'service_type': service_type,
        }
    )
    if filters:
        payload['metadata_condition'] = filters
    return payload


def _response_chunks(data: dict[str, Any]) -> list[Mapping[str, Any]]:
    raw_items = data.get('chunks') or data.get('items') or data.get('records') or []
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, Mapping)]


def _chunk_out(item: Mapping[str, Any], *, default_dataset_id: str | None) -> RagChunkOut:
    metadata = _metadata(item)
    authorization = _authorization_fields(item=item, metadata=metadata)
    return RagChunkOut(
        dataset_id=_text(item, 'dataset_id') or _text(metadata, 'dataset_id') or default_dataset_id,
        document_id=_text(item, 'document_id') or _text(metadata, 'document_id'),
        chunk_id=_text(item, 'chunk_id') or _text(item, 'id') or _text(metadata, 'chunk_id'),
        standard_code=_text(item, 'standard_code') or _text(metadata, 'standard_code'),
        standard_name=_text(item, 'standard_name') or _text(metadata, 'standard_name'),
        clause=_text(item, 'clause') or _text(metadata, 'clause'),
        page=_int_value(item.get('page') or metadata.get('page') or item.get('page_start')),
        version=_text(item, 'version') or _text(metadata, 'version'),
        effective_date=_text(item, 'effective_date') or _text(metadata, 'effective_date'),
        source_uri=_text(item, 'source_uri') or _text(item, 'url') or _text(metadata, 'source_uri'),
        authorized=authorization['authorized'],
        license_id=_text(item, 'license_id') or _text(metadata, 'license_id'),
        source_review_status=_text(item, 'source_review_status')
        or _text(metadata, 'source_review_status'),
        allow_ai_retrieval=authorization['allow_ai_retrieval'],
        allow_excerpt_export=authorization['allow_excerpt_export'],
        chunk_text=_text(item, 'content') or _text(item, 'chunk_text') or _text(item, 'text') or '',
        score=_float_value(
            item.get('score')
            or item.get('similarity')
            or item.get('vector_similarity')
            or metadata.get('score')
        ),
        metadata=metadata,
    )


def _metadata(item: Mapping[str, Any]) -> dict[str, Any]:
    raw = item.get('metadata')
    return dict(raw) if isinstance(raw, Mapping) else {}


def _text(item: Mapping[str, Any], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    text = ' '.join(str(value).strip().split())
    return text or None


def _int_value(value: Any) -> int | None:
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _authorization_fields(
    *, item: Mapping[str, Any], metadata: Mapping[str, Any]
) -> dict[str, bool]:
    explicit_authorized = _optional_bool(item.get('authorized'))
    if explicit_authorized is None:
        explicit_authorized = _optional_bool(metadata.get('authorized'))

    explicit_ai_retrieval = _optional_bool(item.get('allow_ai_retrieval'))
    if explicit_ai_retrieval is None:
        explicit_ai_retrieval = _optional_bool(metadata.get('allow_ai_retrieval'))

    if explicit_ai_retrieval is None:
        allow_ai_retrieval = explicit_authorized is True
    else:
        allow_ai_retrieval = explicit_ai_retrieval is True

    authorized = allow_ai_retrieval if explicit_authorized is None else explicit_authorized is True
    allow_excerpt_export = _optional_bool(item.get('allow_excerpt_export'))
    if allow_excerpt_export is None:
        allow_excerpt_export = _optional_bool(metadata.get('allow_excerpt_export'))

    return {
        'authorized': authorized and allow_ai_retrieval,
        'allow_ai_retrieval': allow_ai_retrieval,
        'allow_excerpt_export': allow_excerpt_export is True,
    }


def _retrieval_authorized(chunk: RagChunkOut) -> bool:
    return chunk.authorized and chunk.allow_ai_retrieval


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    text = str(value).strip().lower()
    if text in {'1', 'true', 'yes', 'y', 'approved', 'allow', 'allowed'}:
        return True
    if text in {'0', 'false', 'no', 'n', 'rejected', 'deny', 'denied'}:
        return False
    return None


def _drop_empty(value: dict[str, str | None]) -> dict[str, str]:
    return {key: item.strip() for key, item in value.items() if item and item.strip()}


def _normalize_limit(value: int) -> int:
    return max(1, min(value, 50))
