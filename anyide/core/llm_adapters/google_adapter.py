"""Google Gemini adapter using google-generativeai SDK."""

from __future__ import annotations

import asyncio
from typing import Any

from anyide.core.llm_adapters.base import (
    LLMAdapter,
    LLMAdapterError,
    LLMAdapterResponse,
)


class GoogleAdapter(LLMAdapter):
    """Adapter for Google Gemini models."""

    def __init__(self, endpoint):
        self.endpoint = endpoint

        import google.generativeai as genai  # Imported lazily for optional dependency safety.

        self._genai = genai
        if endpoint.resolved_api_key:
            self._genai.configure(api_key=endpoint.resolved_api_key)
        self._model = self._genai.GenerativeModel(endpoint.default_model)

    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        **kwargs,
    ) -> dict:
        prompt = self._messages_to_prompt(messages, kwargs.get("system"))

        generation_config: dict[str, Any] = {}
        temperature = kwargs.get("temperature")
        if temperature is None:
            temperature = self.endpoint.temperature
        if temperature is not None:
            generation_config["temperature"] = temperature

        max_tokens = kwargs.get("max_tokens")
        if max_tokens is None:
            max_tokens = self.endpoint.max_tokens
        if max_tokens is not None:
            generation_config["max_output_tokens"] = max_tokens

        use_model = self._model
        if model and model != self.endpoint.default_model:
            use_model = self._genai.GenerativeModel(model)

        try:
            response = await asyncio.to_thread(
                use_model.generate_content,
                prompt,
                generation_config=generation_config or None,
            )
            return self._normalize_response(response, model or self.endpoint.default_model)
        except Exception as exc:  # pragma: no cover - behavior exercised via tests
            raise self._normalize_error(exc) from exc

    def _messages_to_prompt(self, messages: list[dict], explicit_system: str | None) -> str:
        prompt_lines: list[str] = []
        system_blocks: list[str] = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            if role == "system":
                if content:
                    system_blocks.append(str(content))
                continue
            prompt_lines.append(f"{role.capitalize()}: {content}")

        if explicit_system:
            system_blocks.insert(0, explicit_system)

        if system_blocks:
            prompt_lines.insert(0, f"System: {' '.join(system_blocks)}")

        return "\n".join(prompt_lines)

    def _normalize_response(self, response: Any, model_name: str) -> LLMAdapterResponse:
        usage_meta = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage_meta, "prompt_token_count", 0) or 0
        output_tokens = getattr(usage_meta, "candidates_token_count", 0) or 0
        total_tokens = getattr(usage_meta, "total_token_count", 0) or (input_tokens + output_tokens)

        return LLMAdapterResponse(
            content=getattr(response, "text", "") or "",
            model=model_name,
            finish_reason=None,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            raw=response,
        )

    def _normalize_error(self, exc: Exception) -> LLMAdapterError:
        class_name = exc.__class__.__name__.lower()
        message = str(exc)

        error_type = "provider_error"
        retryable = False
        if "ratelimit" in class_name or "quota" in message.lower():
            error_type = "rate_limit"
            retryable = True
        elif "authentication" in class_name or "api key" in message.lower():
            error_type = "authentication_error"
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
            raw_error=exc,
        )
