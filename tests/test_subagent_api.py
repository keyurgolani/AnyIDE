"""API tests for subagent module registration, execution, and safety controls."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from anyide.config import LLMEndpointConfig, SubagentTypeConfig
from anyide.core.llm_client import LLMClientError, LLMResponse

# Set up test environment before app import.
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()
TEST_PROMPTS_DIR = tempfile.mkdtemp()


def _seed_prompt_files() -> dict[str, str]:
    prompt_optimizer = Path(TEST_PROMPTS_DIR) / "prompt_optimizer.md"
    prompt_optimizer.write_text(
        "You are a prompt optimizer. Keep outputs concise.\\n"
        "Task input: {{input}}\\n"
        "Extra context: {{context}}\\n",
        encoding="utf-8",
    )

    json_extractor = Path(TEST_PROMPTS_DIR) / "json_extractor.md"
    json_extractor.write_text(
        "You are a JSON extractor. Return JSON only.\\n"
        "Input: {{input}}\\n",
        encoding="utf-8",
    )

    return {
        "prompt_optimizer": str(prompt_optimizer),
        "json_extractor": str(json_extractor),
    }


@pytest.fixture
async def client():
    prompt_files = _seed_prompt_files()

    os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
    os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")

    import anyide.config
    from anyide.core.llm_client import LLMClient

    original_load = anyide.config.load_config

    llm_endpoints = [
        LLMEndpointConfig(
            id="primary",
            provider="ollama",
            base_url="http://host.docker.internal:11434/v1",
            default_model="llama3.2",
        )
    ]
    subagent_types = {
        "prompt_optimizer": SubagentTypeConfig(
            display_name="Prompt Optimizer",
            description="Optimizes prompts",
            llm_endpoint="primary",
            model="llama3.2:70b",
            temperature=0.3,
            max_tokens=1024,
            system_prompt_file=prompt_files["prompt_optimizer"],
            allow_model_override=True,
            allow_temperature_override=True,
        ),
        "json_extractor": SubagentTypeConfig(
            display_name="JSON Extractor",
            description="Extracts JSON",
            llm_endpoint="primary",
            temperature=0.2,
            max_tokens=512,
            system_prompt_file=prompt_files["json_extractor"],
            response_format="json",
            allow_model_override=False,
            allow_temperature_override=False,
        ),
    }

    def patched_load(config_path: str = "config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        cfg.llm.endpoints = llm_endpoints
        cfg.subagents.types = subagent_types
        return cfg

    anyide.config.load_config = patched_load

    from anyide.main import app, db

    await db.connect()
    from anyide import main as main_module

    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)
    main_module.config.llm.endpoints = llm_endpoints
    main_module.config.subagents.types = subagent_types
    main_module.llm_client = LLMClient(main_module.config.llm, main_module.secret_manager)
    if main_module.module_context is not None:
        main_module.module_context.llm_client = main_module.llm_client

    subagent_module = main_module.module_registry.modules.get("subagent")
    if subagent_module is not None:
        subagent_module.subagent_tools._llm_client = main_module.llm_client
        subagent_module.subagent_tools._subagents_config = main_module.config.subagents

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac

    await db.close()
    anyide.config.load_config = original_load


class TestSubagentAPI:
    @pytest.mark.asyncio
    async def test_subagent_endpoints_exist_in_openapi(self, client):
        response = await client.get("/openapi.json")
        assert response.status_code == 200

        paths = response.json()["paths"]
        assert "/api/tools/subagent/list" in paths
        assert "/api/tools/subagent/run" in paths

    @pytest.mark.asyncio
    async def test_subagent_subapp_openapi_exists(self, client):
        response = await client.get("/tools/subagent/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert "Subagent" in spec["info"]["title"]
        assert "/list" in spec["paths"]
        assert "/run" in spec["paths"]

    @pytest.mark.asyncio
    async def test_subagent_list_returns_configured_types(self, client):
        response = await client.post("/api/tools/subagent/list")
        assert response.status_code == 200

        payload = response.json()
        type_ids = [item["type_id"] for item in payload["types"]]

        assert "prompt_optimizer" in type_ids
        assert "json_extractor" in type_ids

    @pytest.mark.asyncio
    async def test_subagent_run_executes_llm_and_returns_metadata(self, client, monkeypatch):
        from anyide import main as main_module

        complete_mock = AsyncMock(
            return_value=LLMResponse(
                endpoint_id="primary",
                provider="ollama",
                model="llama3.2:70b",
                content="optimized result",
                usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                latency_ms=37,
                raw=None,
            )
        )
        monkeypatch.setattr(main_module.llm_client, "complete", complete_mock)

        response = await client.post(
            "/api/tools/subagent/run",
            json={
                "type": "prompt_optimizer",
                "input": "Improve this prompt",
                "context": "For senior engineers",
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["type"] == "prompt_optimizer"
        assert payload["response"] == "optimized result"
        assert payload["endpoint_used"] == "primary"
        assert payload["model_used"] == "llama3.2:70b"
        assert payload["latency_ms"] == 37
        assert payload["usage"]["total_tokens"] == 15

        call_kwargs = complete_mock.await_args.kwargs
        assert call_kwargs["endpoint_id"] == "primary"
        assert call_kwargs["model"] == "llama3.2:70b"
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 1024
        assert "Improve this prompt" in call_kwargs["messages"][0]["content"]
        assert "For senior engineers" in call_kwargs["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_subagent_run_passes_json_mode_when_configured(self, client, monkeypatch):
        from anyide import main as main_module

        complete_mock = AsyncMock(
            return_value=LLMResponse(
                endpoint_id="primary",
                provider="ollama",
                model="llama3.2",
                content='{"items": []}',
                usage={"input_tokens": 4, "output_tokens": 4, "total_tokens": 8},
                latency_ms=15,
                raw=None,
            )
        )
        monkeypatch.setattr(main_module.llm_client, "complete", complete_mock)

        response = await client.post(
            "/api/tools/subagent/run",
            json={
                "type": "json_extractor",
                "input": "Extract TODO items",
            },
        )

        assert response.status_code == 200
        assert response.json()["response_format"] == "json"
        assert complete_mock.await_args.kwargs["response_format"] == "json"

    @pytest.mark.asyncio
    async def test_subagent_run_rejects_disallowed_model_override(self, client):
        response = await client.post(
            "/api/tools/subagent/run",
            json={
                "type": "json_extractor",
                "input": "Extract TODO items",
                "override_model": "some-other-model",
            },
        )

        assert response.status_code == 400
        payload = response.json()
        assert payload["error_type"] == "invalid_parameter"
        assert "override_model is disabled" in payload["message"]

    @pytest.mark.asyncio
    async def test_subagent_run_respects_hitl_policy(self, client, monkeypatch):
        from anyide import main as main_module
        from anyide.config import ToolPolicyConfig

        main_module.config.tools.subagent["run"] = ToolPolicyConfig(policy="hitl")

        monkeypatch.setattr(
            main_module.hitl_manager,
            "create_request",
            AsyncMock(return_value=SimpleNamespace(id="req-subagent-1")),
        )
        monkeypatch.setattr(
            main_module.hitl_manager,
            "wait_for_decision",
            AsyncMock(return_value="rejected"),
        )

        response = await client.post(
            "/api/tools/subagent/run",
            json={"type": "prompt_optimizer", "input": "Improve this prompt"},
        )

        assert response.status_code == 403
        payload = response.json()
        assert payload["error_type"] == "security_error"

        main_module.config.tools.subagent.pop("run", None)

    @pytest.mark.asyncio
    async def test_subagent_run_maps_connection_failures(self, client, monkeypatch):
        from anyide import main as main_module

        async def raise_connection_error(*_args, **_kwargs):
            raise LLMClientError(
                error_type="connection_error",
                message="upstream unavailable",
                endpoint_id="primary",
                provider="ollama",
            )

        monkeypatch.setattr(main_module.llm_client, "complete", raise_connection_error)

        response = await client.post(
            "/api/tools/subagent/run",
            json={"type": "prompt_optimizer", "input": "Improve this prompt"},
        )

        assert response.status_code == 502
        payload = response.json()
        assert payload["error_type"] == "connection_error"

    @pytest.mark.asyncio
    async def test_subagent_run_maps_config_failures(self, client, monkeypatch):
        from anyide import main as main_module

        async def raise_config_error(*_args, **_kwargs):
            raise LLMClientError(
                error_type="config_error",
                message="unknown endpoint",
                endpoint_id="missing",
                provider="unknown",
            )

        monkeypatch.setattr(main_module.llm_client, "complete", raise_config_error)

        response = await client.post(
            "/api/tools/subagent/run",
            json={"type": "prompt_optimizer", "input": "Improve this prompt"},
        )

        assert response.status_code == 400
        payload = response.json()
        assert payload["error_type"] == "invalid_parameter"
        assert "unknown endpoint" in payload["message"]
