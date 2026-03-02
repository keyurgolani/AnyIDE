"""OpenAI SDK adapter for openai/ollama/openai-compatible providers."""

from __future__ import annotations

from typing import Any

from anyide.core.llm_adapters.base import (
    LLMAdapter,
    LLMAdapterError,
    LLMAdapterResponse,
)


class OpenAIAdapter(LLMAdapter):
    """Adapter for OpenAI Chat Completions-compatible providers."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        from openai import AsyncOpenAI  # Imported lazily for optional dependency safety.

        api_key = endpoint.resolved_api_key
        if not api_key:
            # OpenAI SDK requires an API key even for local compatibility servers.
            api_key = "ollama"

        self.client = AsyncOpenAI(
            base_url=endpoint.base_url,
            api_key=api_key,
            timeout=endpoint.timeout,
        )

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        **kwargs,
    ) -> dict:
        request: dict[str, Any] = {
            "model": model or self.endpoint.default_model,
            "messages": messages,
        }

        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = self.endpoint.temperature
        if temperature is not None:
            request["temperature"] = temperature

        max_tokens = kwargs.get("max_tokens")
        if max_tokens is None:
            max_tokens = self.endpoint.max_tokens
        if max_tokens is not None:
            request["max_tokens"] = max_tokens

        response_format = kwargs.get("response_format")
        if response_format == "json":
            request["response_format"] = {"type": "json_object"}
        elif response_format:
            request["response_format"] = response_format

        try:
            response = await self.client.chat.completions.create(**request)
            return self._normalize_response(response)
        except Exception as exc:  # pragma: no cover - behavior exercised via tests
            raise self._normalize_error(exc) from exc

    def _normalize_response(self, response: Any) -> LLMAdapterResponse:
        content = ""
        choices = getattr(response, "choices", None) or []
        if choices:
            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            content = getattr(message, "content", "") or ""

        usage_obj = getattr(response, "usage", None)
        usage = {
            "input_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
        }

        finish_reason = None
        if choices:
            finish_reason = getattr(choices[0], "finish_reason", None)

        return LLMAdapterResponse(
            content=content,
            model=getattr(response, "model", self.endpoint.default_model),
            finish_reason=finish_reason,
            usage=usage,
            raw=response,
        )

    def _normalize_error(self, exc: Exception) -> LLMAdapterError:
        error_type = "provider_error"
        retryable = False
        class_name = exc.__class__.__name__.lower()
        message = str(exc)
        status_code = getattr(exc, "status_code", None)

        if "ratelimit" in class_name or status_code == 429:
            error_type = "rate_limit"
            retryable = True
        elif "authentication" in class_name or status_code in (401, 403):
            error_type = "authentication_error"
        elif "permission" in class_name:
            error_type = "permission_error"
        elif "timeout" in class_name:
            error_type = "timeout"
            retryable = True
        elif "connection" in class_name:
            error_type = "connection_error"
            retryable = True

        return LLMAdapterError(
            error_type=error_type,
            message=message,
            provider=self.endpoint.provider,
            retryable=retryable,
            status_code=status_code,
            raw_error=exc,
        )
