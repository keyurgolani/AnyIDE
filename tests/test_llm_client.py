"""Tests for unified LLM client and provider adapters."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

from anyide.config import Config
from anyide.core.llm_client import (
    LLMClient,
    LLMClientError,
    ResolvedLLMEndpoint,
)
from anyide.core.llm_adapters.anthropic_adapter import AnthropicAdapter
from anyide.core.llm_adapters.base import LLMAdapterError
from anyide.core.llm_adapters.google_adapter import GoogleAdapter
from anyide.core.llm_adapters.openai_adapter import OpenAIAdapter


class _SecretStore:
    def __init__(self, secrets: dict[str, str]):
        self._secrets = secrets

    def get(self, key: str) -> str:
        if key not in self._secrets:
            raise KeyError(key)
        return self._secrets[key]


@pytest.mark.asyncio
async def test_llm_client_routes_to_adapter_and_resolves_secret(monkeypatch):
    config = Config(
        llm={
            "endpoints": [
                {
                    "id": "primary",
                    "provider": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key_secret": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                }
            ]
        }
    )

    captured: dict = {}

    class DummyAdapter:
        def __init__(self, endpoint):
            captured["endpoint"] = endpoint

        async def complete(self, messages, model=None, **kwargs):
            captured["messages"] = messages
            captured["model"] = model
            captured["kwargs"] = kwargs
            return {
                "content": "ok",
                "model": model or "gpt-4o-mini",
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                "raw": {"provider": "dummy"},
            }

    monkeypatch.setattr(
        "anyide.core.llm_client.ADAPTER_MAP",
        {"openai": DummyAdapter},
    )

    client = LLMClient(
        config=config.llm,
        secret_manager=_SecretStore({"OPENAI_API_KEY": "secret-value"}),
    )

    response = await client.complete(
        endpoint_id="primary",
        messages=[{"role": "user", "content": "hello"}],
        response_format="json",
    )

    assert captured["endpoint"].resolved_api_key == "secret-value"
    assert response.content == "ok"
    assert response.provider == "openai"
    assert response.endpoint_id == "primary"
    assert captured["kwargs"]["response_format"] == "json"


def test_llm_client_list_endpoints_returns_config_without_secrets():
    config = Config(
        llm={
            "endpoints": [
                {
                    "id": "local",
                    "provider": "ollama",
                    "base_url": "http://host.docker.internal:11434/v1",
                    "default_model": "llama3.2",
                }
            ]
        }
    )
    client = LLMClient(config=config.llm, secret_manager=_SecretStore({}))
    endpoints = client.list_endpoints()

    assert len(endpoints) == 1
    assert endpoints[0].id == "local"
    assert not hasattr(endpoints[0], "resolved_api_key")


@pytest.mark.asyncio
async def test_llm_client_errors_for_unknown_endpoint():
    client = LLMClient(config=Config().llm, secret_manager=_SecretStore({}))
    with pytest.raises(LLMClientError, match="Unknown llm endpoint id"):
        await client.complete(endpoint_id="missing", messages=[])


@pytest.mark.asyncio
async def test_llm_client_errors_when_secret_missing():
    config = Config(
        llm={
            "endpoints": [
                {
                    "id": "primary",
                    "provider": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "api_key_secret": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                }
            ]
        }
    )
    client = LLMClient(config=config.llm, secret_manager=_SecretStore({}))

    with pytest.raises(LLMClientError, match="OPENAI_API_KEY"):
        await client.complete(endpoint_id="primary", messages=[])


@pytest.mark.asyncio
async def test_openai_adapter_normalizes_response(monkeypatch):
    calls: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            calls["kwargs"] = kwargs
            return SimpleNamespace(
                model="gpt-4o-mini",
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="hello"),
                        finish_reason="stop",
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=10,
                    completion_tokens=4,
                    total_tokens=14,
                ),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            calls["init"] = kwargs
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_openai = ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeClient
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    adapter = OpenAIAdapter(
        ResolvedLLMEndpoint(
            id="primary",
            provider="openai",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            timeout=30,
            max_tokens=None,
            temperature=None,
            api_key_secret="OPENAI_API_KEY",
            resolved_api_key="secret-value",
        )
    )

    result = await adapter.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="gpt-4o",
        max_tokens=20,
    )

    assert calls["init"]["base_url"] == "https://api.openai.com/v1"
    assert calls["kwargs"]["model"] == "gpt-4o"
    assert result.content == "hello"
    assert result.usage["total_tokens"] == 14


@pytest.mark.asyncio
async def test_openai_adapter_normalizes_errors(monkeypatch):
    class RateLimitError(Exception):
        status_code = 429

    class FakeCompletions:
        async def create(self, **kwargs):
            raise RateLimitError("rate limited")

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=FakeCompletions())

    fake_openai = ModuleType("openai")
    fake_openai.AsyncOpenAI = FakeClient
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    adapter = OpenAIAdapter(
        ResolvedLLMEndpoint(
            id="primary",
            provider="openai",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            timeout=30,
            max_tokens=None,
            temperature=None,
            api_key_secret="OPENAI_API_KEY",
            resolved_api_key="secret-value",
        )
    )

    with pytest.raises(LLMAdapterError, match="rate limited"):
        await adapter.complete(messages=[{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_anthropic_adapter_maps_system_message(monkeypatch):
    calls: dict = {}

    class FakeMessages:
        async def create(self, **kwargs):
            calls["kwargs"] = kwargs
            return SimpleNamespace(
                model="claude-sonnet",
                stop_reason="end_turn",
                content=[SimpleNamespace(type="text", text="done")],
                usage=SimpleNamespace(input_tokens=6, output_tokens=3),
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.messages = FakeMessages()

    fake_anthropic = ModuleType("anthropic")
    fake_anthropic.AsyncAnthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)

    adapter = AnthropicAdapter(
        ResolvedLLMEndpoint(
            id="anthropic",
            provider="anthropic",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-20250514",
            timeout=30,
            max_tokens=128,
            temperature=None,
            api_key_secret="ANTHROPIC_API_KEY",
            resolved_api_key="secret-value",
        )
    )

    result = await adapter.complete(
        messages=[
            {"role": "system", "content": "You are concise"},
            {"role": "user", "content": "hello"},
        ],
    )

    assert calls["kwargs"]["system"] == "You are concise"
    assert calls["kwargs"]["messages"] == [{"role": "user", "content": "hello"}]
    assert result.content == "done"
    assert result.usage["input_tokens"] == 6


@pytest.mark.asyncio
async def test_google_adapter_normalizes_response(monkeypatch):
    calls: dict = {}

    class FakeResponse:
        text = "gemini-output"
        usage_metadata = SimpleNamespace(
            prompt_token_count=9,
            candidates_token_count=2,
            total_token_count=11,
        )

    class FakeModel:
        def __init__(self, model_name):
            calls["model_name"] = model_name

        def generate_content(self, prompt, generation_config=None):
            calls["prompt"] = prompt
            calls["generation_config"] = generation_config
            return FakeResponse()

    fake_genai = ModuleType("google.generativeai")

    def fake_configure(api_key):
        calls["api_key"] = api_key

    fake_genai.configure = fake_configure
    fake_genai.GenerativeModel = FakeModel

    google_pkg = ModuleType("google")
    google_pkg.generativeai = fake_genai
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.generativeai", fake_genai)

    adapter = GoogleAdapter(
        ResolvedLLMEndpoint(
            id="google",
            provider="google",
            base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.0-flash",
            timeout=30,
            max_tokens=64,
            temperature=0.2,
            api_key_secret="GOOGLE_API_KEY",
            resolved_api_key="secret-value",
        )
    )

    result = await adapter.complete(messages=[{"role": "user", "content": "hi"}])

    assert calls["api_key"] == "secret-value"
    assert calls["model_name"] == "gemini-2.0-flash"
    assert "hi" in calls["prompt"]
    assert result.content == "gemini-output"
    assert result.usage["total_tokens"] == 11
