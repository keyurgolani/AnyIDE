"""Unified LLM client with provider adapter normalization."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field

from anyide.config import LLMConfig, LLMEndpointConfig
from anyide.core.llm_adapters import (
    AnthropicAdapter,
    GoogleAdapter,
    LLMAdapterError,
    OpenAIAdapter,
)


ADAPTER_MAP = {
    "openai": OpenAIAdapter,
    "openai_compatible": OpenAIAdapter,
    "ollama": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "google": GoogleAdapter,
}


@dataclass
class ResolvedLLMEndpoint:
    """Endpoint config resolved for execution (includes secret value)."""

    id: str
    provider: str
    base_url: str
    default_model: str
    timeout: int
    max_tokens: Optional[int]
    temperature: Optional[float]
    api_key_secret: Optional[str]
    resolved_api_key: Optional[str]


class LLMResponse(BaseModel):
    """Normalized LLM completion response."""

    endpoint_id: str = Field(..., description="Endpoint ID used for the request")
    provider: str = Field(..., description="Provider name")
    model: str = Field(..., description="Model used for the request")
    content: str = Field(..., description="Generated response content")
    finish_reason: Optional[str] = Field(None, description="Provider finish reason")
    usage: dict[str, int] = Field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        description="Normalized token usage",
    )
    latency_ms: int = Field(..., description="Request latency in milliseconds")
    raw: Any = Field(None, description="Provider raw response object")


class LLMClientError(RuntimeError):
    """Normalized LLM client error."""

    def __init__(
        self,
        error_type: str,
        message: str,
        *,
        endpoint_id: Optional[str] = None,
        provider: Optional[str] = None,
        retryable: bool = False,
        status_code: Optional[int] = None,
        raw_error: Any = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.endpoint_id = endpoint_id
        self.provider = provider
        self.retryable = retryable
        self.status_code = status_code
        self.raw_error = raw_error


class LLMClient:
    """Unified client that routes requests to provider adapters."""

    def __init__(self, config: LLMConfig, secret_manager: Any):
        self._config = config
        self._secret_manager = secret_manager
        self._endpoint_by_id = {endpoint.id: endpoint for endpoint in config.endpoints}

    def get_endpoint(self, endpoint_id: str) -> LLMEndpointConfig:
        endpoint = self._endpoint_by_id.get(endpoint_id)
        if endpoint is None:
            available = sorted(self._endpoint_by_id.keys())
            raise LLMClientError(
                error_type="config_error",
                message=f"Unknown llm endpoint id '{endpoint_id}'. Available: {available}",
                endpoint_id=endpoint_id,
            )
        return endpoint

    def list_endpoints(self) -> list[LLMEndpointConfig]:
        return [endpoint.model_copy(deep=True) for endpoint in self._config.endpoints]

    async def complete(
        self,
        endpoint_id: str,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: str | None = None,
        system: str | None = None,
    ) -> LLMResponse:
        endpoint = self.get_endpoint(endpoint_id)
        resolved_endpoint = self._resolve_endpoint(endpoint)
        adapter_cls = ADAPTER_MAP.get(resolved_endpoint.provider)
        if adapter_cls is None:
            raise LLMClientError(
                error_type="config_error",
                message=f"Unsupported llm provider '{resolved_endpoint.provider}'",
                endpoint_id=endpoint_id,
                provider=resolved_endpoint.provider,
            )

        adapter = adapter_cls(resolved_endpoint)
        start = time.time()

        try:
            normalized = await adapter.complete(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                system=system,
            )
        except LLMAdapterError as exc:
            raise LLMClientError(
                error_type=exc.error_type,
                message=exc.message,
                endpoint_id=endpoint_id,
                provider=resolved_endpoint.provider,
                retryable=exc.retryable,
                status_code=exc.status_code,
                raw_error=exc.raw_error,
            ) from exc
        except LLMClientError:
            raise
        except Exception as exc:  # pragma: no cover - safety net
            raise LLMClientError(
                error_type="provider_error",
                message=str(exc),
                endpoint_id=endpoint_id,
                provider=resolved_endpoint.provider,
                raw_error=exc,
            ) from exc

        if hasattr(normalized, "model_dump"):
            normalized_payload = normalized.model_dump()
        elif isinstance(normalized, dict):
            normalized_payload = normalized
        else:
            normalized_payload = {
                "content": getattr(normalized, "content", ""),
                "model": getattr(normalized, "model", resolved_endpoint.default_model),
                "finish_reason": getattr(normalized, "finish_reason", None),
                "usage": getattr(normalized, "usage", {}),
                "raw": getattr(normalized, "raw", None),
            }

        elapsed_ms = int((time.time() - start) * 1000)
        return LLMResponse(
            endpoint_id=endpoint_id,
            provider=resolved_endpoint.provider,
            model=normalized_payload.get("model") or resolved_endpoint.default_model,
            content=normalized_payload.get("content", ""),
            finish_reason=normalized_payload.get("finish_reason"),
            usage=normalized_payload.get("usage") or {},
            latency_ms=elapsed_ms,
            raw=normalized_payload.get("raw"),
        )

    def _resolve_endpoint(self, endpoint: LLMEndpointConfig) -> ResolvedLLMEndpoint:
        resolved_api_key: Optional[str] = None

        if endpoint.api_key_secret:
            try:
                resolved_api_key = self._resolve_secret(endpoint.api_key_secret)
            except Exception as exc:
                raise LLMClientError(
                    error_type="secret_not_found",
                    message=(
                        f"Failed to resolve api key secret '{endpoint.api_key_secret}' "
                        f"for endpoint '{endpoint.id}': {exc}"
                    ),
                    endpoint_id=endpoint.id,
                    provider=endpoint.provider,
                    raw_error=exc,
                ) from exc

        return ResolvedLLMEndpoint(
            id=endpoint.id,
            provider=endpoint.provider,
            base_url=endpoint.base_url,
            default_model=endpoint.default_model,
            timeout=endpoint.timeout,
            max_tokens=endpoint.max_tokens,
            temperature=endpoint.temperature,
            api_key_secret=endpoint.api_key_secret,
            resolved_api_key=resolved_api_key,
        )

    def _resolve_secret(self, key: str) -> str:
        # Support both direct-key interfaces and SecretManager template resolution.
        if hasattr(self._secret_manager, "get") and callable(self._secret_manager.get):
            return self._secret_manager.get(key)
        if hasattr(self._secret_manager, "resolve_value") and callable(
            self._secret_manager.resolve_value
        ):
            return self._secret_manager.resolve_value(f"{{{{secret:{key}}}}}")
        raise ValueError("Secret manager does not support key resolution")
