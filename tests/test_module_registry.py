"""Tests for modular plug-and-play architecture registry and exposure parity."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from httpx import ASGITransport, AsyncClient

from src.audit import AuditLogger
from src.config import Config
from src.database import Database
from src.hitl import HITLManager
from src.modules import ModuleContext, ModuleRegistry, ModuleResolutionError
from src.modules.base import ToolModule
from src.policy import PolicyEngine
from src.secrets import SecretManager
from src.workspace import WorkspaceManager


async def _noop_dispatch(_category: str, _name: str, _params: dict) -> dict:
    return {}


async def _noop_execute_tool(*_args, **_kwargs):
    return {}


def _identity_request(request):
    return request


def _build_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, modules_env: str) -> tuple[FastAPI, ModuleRegistry, FastApiMCP]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "test.db"
    secrets_file = tmp_path / "secrets.env"
    secrets_file.write_text("TEST_KEY=test-value\n")

    monkeypatch.setenv("ANYIDE_MODULES", modules_env)

    config = Config()
    config.workspace.base_dir = str(workspace)
    config.secrets.file = str(secrets_file)

    db = Database(str(db_path))
    context = ModuleContext(
        config=config,
        db=db,
        workspace_manager=WorkspaceManager(str(workspace)),
        audit_logger=AuditLogger(db),
        policy_engine=PolicyEngine(config),
        hitl_manager=HITLManager(db, config.hitl.default_ttl_seconds),
        secret_manager=SecretManager(str(secrets_file)),
        logger=None,
        execute_tool=_noop_execute_tool,
        resolve_request_secrets=_identity_request,
        tool_dispatch=_noop_dispatch,
    )

    app = FastAPI(title="AnyIDE Test App")
    registry = ModuleRegistry(context)
    registry.load_modules(app)

    mcp = FastApiMCP(app, include_tags=registry.mcp_tags)
    mcp.mount_http()

    return app, registry, mcp


def test_anyide_modules_selection_all_minus(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """ANYIDE_MODULES supports all,-module syntax and ordering is deterministic."""
    _, registry, _ = _build_registry(tmp_path, monkeypatch, "all,-docker,-http")
    assert "docker" not in registry.load_order
    assert "http" not in registry.load_order
    assert "fs" in registry.load_order
    assert "workspace" in registry.load_order


def test_dependency_resolution_detects_missing_and_circular(monkeypatch: pytest.MonkeyPatch):
    """Registry enforces missing/circular dependency errors."""

    class DummyContext:  # minimal context for dependency tests
        pass

    class A(ToolModule):
        MODULE_NAME = "a"

        @property
        def name(self):
            return self.MODULE_NAME

        @property
        def display_name(self):
            return "A"

        @property
        def description(self):
            return "A"

        @property
        def dependencies(self):
            return ["missing"]

        def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
            return None

    class B(ToolModule):
        MODULE_NAME = "b"

        @property
        def name(self):
            return self.MODULE_NAME

        @property
        def display_name(self):
            return "B"

        @property
        def description(self):
            return "B"

        @property
        def dependencies(self):
            return ["c"]

        def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
            return None

    class C(ToolModule):
        MODULE_NAME = "c"

        @property
        def name(self):
            return self.MODULE_NAME

        @property
        def display_name(self):
            return "C"

        @property
        def description(self):
            return "C"

        @property
        def dependencies(self):
            return ["b"]

        def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
            return None

    context = ModuleContext(
        config=Config(),
        db=None,
        workspace_manager=None,
        audit_logger=None,
        policy_engine=None,
        hitl_manager=None,
        secret_manager=None,
        logger=None,
        execute_tool=_noop_execute_tool,
        resolve_request_secrets=_identity_request,
        tool_dispatch=_noop_dispatch,
    )
    registry = ModuleRegistry(context)

    with pytest.raises(ModuleResolutionError, match="depends on unknown module 'missing'"):
        registry.resolve_load_order(["a"], {"a": A})

    with pytest.raises(ModuleResolutionError, match="Circular module dependency"):
        registry.resolve_load_order(["b", "c"], {"b": B, "c": C})


@pytest.mark.asyncio
async def test_openapi_and_mcp_reflect_disabled_modules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Disabling modules removes their tools from OpenAPI and MCP discovery."""
    app, _registry, mcp = _build_registry(tmp_path, monkeypatch, "all,-docker,-http")

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            openapi = (await client.get("/openapi.json")).json()
            paths = set(openapi.get("paths", {}).keys())

            assert "/api/tools/fs/read" in paths
            assert "/api/tools/docker/list" not in paths
            assert "/api/tools/http/request" not in paths

            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
            init_response = await client.post(
                "/mcp",
                json=init_request,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            session_id = init_response.headers.get("Mcp-Session-Id")

            list_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            response = await client.post("/mcp", json=list_request, headers=headers)
            payload = response.json()
            tool_names = {tool["name"] for tool in payload["result"]["tools"]}

            assert "fs_read" in tool_names
            assert "docker_list" not in tool_names
            assert "http_request" not in tool_names
    finally:
        if hasattr(mcp, "_http_transport") and mcp._http_transport:
            await mcp._http_transport.shutdown()
