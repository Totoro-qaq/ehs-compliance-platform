from __future__ import annotations

from typing import Protocol

from app.core.config import settings
from app.services.rag.ragflow_client import RagflowClient
from app.services.rag.schemas import RagChunkOut, RagChunkSearchResponse, RagHealthResponse


class RagProvider(Protocol):
    def healthcheck(self) -> RagHealthResponse:
        pass

    def search_chunks(
        self,
        *,
        query: str,
        standard_code: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        document_id: str | None = None,
        limit: int = 10,
    ) -> RagChunkSearchResponse:
        pass

    def get_clause(
        self,
        *,
        standard_code: str,
        clause: str,
        limit: int = 5,
    ) -> RagChunkSearchResponse:
        pass


class DisabledRagProvider:
    def __init__(self, *, reason: str) -> None:
        self.reason = reason

    def healthcheck(self) -> RagHealthResponse:
        return RagHealthResponse(
            configured=False,
            ok=False,
            base_url=_configured_base_url(),
            dataset_ids=settings.ragflow_dataset_id_list,
            error=self.reason,
        )

    def search_chunks(
        self,
        *,
        query: str,
        standard_code: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        document_id: str | None = None,
        limit: int = 10,
    ) -> RagChunkSearchResponse:
        return RagChunkSearchResponse(
            configured=False,
            query=query.strip() or None,
            dataset_ids=settings.ragflow_dataset_id_list,
            items=[],
            limit=_normalize_limit(limit),
            error=self.reason,
        )

    def get_clause(
        self,
        *,
        standard_code: str,
        clause: str,
        limit: int = 5,
    ) -> RagChunkSearchResponse:
        query = ' '.join(part for part in (standard_code.strip(), clause.strip()) if part)
        return self.search_chunks(query=query, standard_code=standard_code, limit=limit)


class RagflowProvider:
    def __init__(self, *, client: RagflowClient) -> None:
        self.client = client

    def healthcheck(self) -> RagHealthResponse:
        return self.client.healthcheck()

    def search_chunks(
        self,
        *,
        query: str,
        standard_code: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        document_id: str | None = None,
        limit: int = 10,
    ) -> RagChunkSearchResponse:
        return self.client.search_chunks(
            query=query,
            standard_code=standard_code,
            domain=domain,
            service_type=service_type,
            document_id=document_id,
            limit=limit,
        )

    def get_clause(
        self,
        *,
        standard_code: str,
        clause: str,
        limit: int = 5,
    ) -> RagChunkSearchResponse:
        query = ' '.join(part for part in (standard_code.strip(), clause.strip()) if part)
        return self.client.search_chunks(
            query=query,
            standard_code=standard_code,
            clause=clause,
            limit=limit,
        )


class RagflowService:
    @staticmethod
    def healthcheck() -> RagHealthResponse:
        return get_configured_rag_provider().healthcheck()

    @staticmethod
    def search_chunks(
        *,
        query: str,
        standard_code: str | None = None,
        domain: str | None = None,
        service_type: str | None = None,
        document_id: str | None = None,
        limit: int = 10,
    ) -> RagChunkSearchResponse:
        return get_configured_rag_provider().search_chunks(
            query=query,
            standard_code=standard_code,
            domain=domain,
            service_type=service_type,
            document_id=document_id,
            limit=limit,
        )

    @staticmethod
    def get_clause(*, standard_code: str, clause: str, limit: int = 5) -> RagChunkSearchResponse:
        return get_configured_rag_provider().get_clause(
            standard_code=standard_code,
            clause=clause,
            limit=limit,
        )


def get_configured_rag_provider() -> RagProvider:
    if not settings.ragflow_base_url.strip():
        return DisabledRagProvider(reason='RAGFLOW_BASE_URL is not configured')
    if not settings.ragflow_api_key.strip():
        return DisabledRagProvider(reason='RAGFLOW_API_KEY is not configured')
    if not settings.ragflow_dataset_id_list:
        return DisabledRagProvider(reason='RAGFLOW_DATASET_IDS is not configured')
    return RagflowProvider(
        client=RagflowClient(
            base_url=settings.ragflow_base_url,
            api_key=settings.ragflow_api_key,
            dataset_ids=settings.ragflow_dataset_id_list,
            timeout_seconds=settings.ragflow_timeout_seconds,
        )
    )


def chunk_search_response_to_dict(response: RagChunkSearchResponse) -> dict[str, object]:
    return response.model_dump(mode='json')


def chunk_to_dict(chunk: RagChunkOut) -> dict[str, object]:
    return chunk.model_dump(mode='json')


def _configured_base_url() -> str | None:
    base_url = settings.ragflow_base_url.strip()
    return base_url or None


def _normalize_limit(value: int) -> int:
    return max(1, min(value, 50))
