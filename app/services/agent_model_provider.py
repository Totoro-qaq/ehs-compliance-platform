from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import settings
from app.core.exceptions import EHSException
from app.core.logging_setup import get_logger

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AgentModelMetadata:
    provider_name: str
    model_name: str


class AgentModelProvider(Protocol):
    name: str
    model_name: str

    async def generate(self, *, messages: list[dict[str, str]]) -> str:
        pass


class OllamaAgentModelProvider:
    name = 'ollama'

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds

    async def generate(self, *, messages: list[dict[str, str]]) -> str:
        payload = {
            'model': self.model_name,
            'messages': messages,
            'stream': False,
            'options': {
                'num_predict': 320,
                'temperature': 0.2,
            },
        }
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f'{self.base_url}/api/chat', json=payload)
            response.raise_for_status()
            data = response.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _logger.info(
            'agent.model completed provider=%s model=%s elapsed_ms=%s prompt_messages=%s',
            self.name,
            self.model_name,
            elapsed_ms,
            len(messages),
        )
        content_text = data.get('message', {}).get('content') or data.get('response')
        if not content_text:
            raise RuntimeError('Ollama 返回为空')
        return str(content_text).strip()


class MockAgentModelProvider:
    name = 'mock'
    model_name = 'mock-agent-model'

    def __init__(self, *, response: str = 'AGENT_MOCK_RESPONSE') -> None:
        self.response = response

    async def generate(self, *, messages: list[dict[str, str]]) -> str:
        _logger.info(
            'agent.model completed provider=%s model=%s prompt_messages=%s',
            self.name,
            self.model_name,
            len(messages),
        )
        return self.response


def get_configured_agent_model_metadata() -> AgentModelMetadata:
    provider_name = settings.agent_llm_provider.strip().lower() or 'ollama'
    if provider_name == 'ollama':
        return AgentModelMetadata(
            provider_name=provider_name,
            model_name=settings.ollama_chat_model,
        )
    if provider_name == 'mock':
        return AgentModelMetadata(
            provider_name=provider_name,
            model_name=MockAgentModelProvider.model_name,
        )
    return AgentModelMetadata(provider_name=provider_name, model_name='unsupported')


def get_configured_agent_model_provider() -> AgentModelProvider:
    metadata = get_configured_agent_model_metadata()
    if metadata.provider_name == 'ollama':
        return OllamaAgentModelProvider(
            base_url=settings.ollama_base_url,
            model_name=settings.ollama_chat_model,
            timeout_seconds=settings.agent_request_timeout_seconds,
        )
    if metadata.provider_name == 'mock':
        return MockAgentModelProvider()
    raise EHSException(
        '当前 Agent LLM provider 暂未接入',
        code='AGENT_PROVIDER_NOT_SUPPORTED',
        status_code=503,
        details={'provider': metadata.provider_name},
    )
