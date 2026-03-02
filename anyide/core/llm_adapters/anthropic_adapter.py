"""Anthropic SDK adapter."""

from __future__ import annotations

from typing import Any

from anyide.core.llm_adapters.base import (
    LLMAdapter,
    LLMAdapterError,
    LLMAdapterResponse,
)


class AnthropicAdapter(LLMAdapter):
    """Adapter for Anthropic Messages API."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        from anthropic import AsyncAnthropic  # Imported lazily for optional dependency safety.

        self.client = AsyncAnthropic(
            api_key=endpoint.resolved_api_key,
            timeout=endpoint.timeout,
        )

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        **kwargs,
    ) -> dict:
        system_blocks: list[str] = []
        user_messages: list[dict] = []

        for message in messages:
            role = message.get("role")
            if role == "system":
                content = message.get("content")
                if content:
                    system_blocks.append(str(content))
            else:
                user_messages.append(message)

        explicit_system = kwargs.get("system")
        system = explicit_system if explicit_system is not None else "\n\n".join(system_blocks)

        request: dict[str, Any] = {
            "model": model or self.endpoint.default_model,
            "messages": user_messages,
            "system": system or "",
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

        try:
            response = await self.client.messages.create(**request)
            return self._normalize_response(response)
        except Exception as exc:  # pragma: no cover - behavior exercised via tests
            raise self._normalize_error(exc) from exc

    def _normalize_response(self, response: Any) -> LLMAdapterResponse:
        text_parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", "") == "text":
                text = getattr(block, "text", "")
                if text:
                    text_parts.append(text)

        usage_obj = getattr(response, "usage", None)
        input_tokens = getattr(usage_obj, "input_tokens", 0) or 0
        output_tokens = getattr(usage_obj, "output_tokens", 0) or 0

        return LLMAdapterResponse(
            content="".join(text_parts),
            model=getattr(response, "model", self.endpoint.default_model),
            finish_reason=getattr(response, "stop_reason", None),
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            raw=response,
        )

    def _normalize_error(self, exc: Exception) -> LLMAdapterError:
        class_name = exc.__class__.__name__.lower()
        status_code = getattr(exc, "status_code", None)

        error_type = "provider_error"
        retryable = False
        if "ratelimit" in class_name or status_code == 429:
            error_type = "rate_limit"
            retryable = True
        elif "authentication" in class_name or status_code in (401, 403):
            error_type = "authentication_error"
        elif "timeout" in class_name:
            error_type = "timeout"
            retryable = True
        elif "connection" in class_name:
            error_type = "connection_error"
            retryable = True

        return LLMAdapterError(
            error_type=error_type,
            message=str(exc),
            provider=self.endpoint.provider,
            retryable=retryable,
            status_code=status_code,
            raw_error=exc,
        )
