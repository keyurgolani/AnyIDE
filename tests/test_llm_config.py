"""Tests for llm.endpoints config schema and provider validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from anyide.config import load_config


def _write_config(tmp_path: Path, body: str) -> str:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(body, encoding="utf-8")
    return str(config_path)


def test_load_config_parses_llm_endpoints(tmp_path):
    config_path = _write_config(
        tmp_path,
        """
llm:
  endpoints:
    - id: "primary"
      provider: "openai"
      base_url: "https://api.openai.com/v1"
      api_key_secret: "OPENAI_API_KEY"
      default_model: "gpt-4o-mini"
      timeout: 45
    - id: "local"
      provider: "ollama"
      base_url: "http://host.docker.internal:11434/v1"
      default_model: "llama3.2"
""",
    )

    config = load_config(config_path)

    assert len(config.llm.endpoints) == 2
    assert config.llm.endpoints[0].id == "primary"
    assert config.llm.endpoints[0].provider == "openai"
    assert config.llm.endpoints[1].id == "local"
    assert config.llm.endpoints[1].provider == "ollama"


def test_llm_endpoint_ids_must_be_unique(tmp_path):
    config_path = _write_config(
        tmp_path,
        """
llm:
  endpoints:
    - id: "dup"
      provider: "openai"
      base_url: "https://api.openai.com/v1"
      api_key_secret: "OPENAI_API_KEY"
      default_model: "gpt-4o-mini"
    - id: "dup"
      provider: "ollama"
      base_url: "http://host.docker.internal:11434/v1"
      default_model: "llama3.2"
""",
    )

    with pytest.raises(ValidationError, match="Duplicate llm endpoint id"):
        load_config(config_path)


@pytest.mark.parametrize(
    "provider",
    ["openai", "openai_compatible", "anthropic", "google"],
)
def test_non_ollama_provider_requires_api_key_secret(tmp_path, provider):
    config_path = _write_config(
        tmp_path,
        f"""
llm:
  endpoints:
    - id: "missing-key"
      provider: "{provider}"
      base_url: "https://example.test"
      default_model: "model-1"
""",
    )

    with pytest.raises(ValidationError, match="api_key_secret is required"):
        load_config(config_path)


def test_ollama_endpoint_allows_missing_api_key_secret(tmp_path):
    config_path = _write_config(
        tmp_path,
        """
llm:
  endpoints:
    - id: "local"
      provider: "ollama"
      base_url: "http://host.docker.internal:11434/v1"
      default_model: "llama3.2"
""",
    )

    config = load_config(config_path)
    endpoint = config.llm.endpoints[0]
    assert endpoint.provider == "ollama"
    assert endpoint.api_key_secret is None


def test_llm_endpoint_timeout_must_be_positive(tmp_path):
    config_path = _write_config(
        tmp_path,
        """
llm:
  endpoints:
    - id: "primary"
      provider: "openai"
      base_url: "https://api.openai.com/v1"
      api_key_secret: "OPENAI_API_KEY"
      default_model: "gpt-4o-mini"
      timeout: 0
""",
    )

    with pytest.raises(ValidationError):
        load_config(config_path)
