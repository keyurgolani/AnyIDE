"""Module matrix integration coverage for enabled/disabled combinations."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from httpx import ASGITransport, AsyncClient

from anyide.config import Config
from anyide.core.audit import AuditLogger
from anyide.core.database import Database
from anyide.core.hitl import HITLManager
from anyide.core.policy import PolicyEngine
from anyide.core.secrets import SecretManager
from anyide.core.workspace import WorkspaceManager
from anyide.modules import ModuleContext, ModuleRegistry, ModuleResolutionError
from anyide.modules.base import ToolModule


async def _noop_dispatch(_category: str, _name: str, _params: dict) -> dict:
    return {}


async def _noop_execute_tool(*_args, **_kwargs):
    return {}


def _identity_request(request):
    return request


def _build_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    modules_env: str,
) -> tuple[FastAPI, ModuleRegistry, FastApiMCP]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "test.db"
    secrets_file = tmp_path / "secrets.env"
    secrets_file.write_text("TEST_KEY=test-value\n", encoding="utf-8")

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


MODULE_MATRIX_CASES = [
    pytest.param(
        "all",
        {
            "/api/tools/fs/read",
            "/api/tools/workspace/info",
            "/api/tools/shell/execute",
            "/api/tools/git/status",
            "/api/tools/docker/list",
            "/api/tools/http/request",
            "/api/tools/memory/store",
            "/api/tools/plan/create",
            "/api/tools/language/validate",
            "/api/tools/skills/list",
            "/api/tools/subagent/list",
        },
        set(),
        {
            "fs_read",
            "workspace_info",
            "shell_execute",
            "git_status",
            "docker_list",
            "http_request",
            "memory_store",
            "plan_create",
            "lang_validate",
            "skills_list",
            "subagent_list",
        },
        set(),
        id="all-modules",
    ),
    pytest.param(
        "all,-docker,-http",
        {
            "/api/tools/fs/read",
            "/api/tools/workspace/info",
            "/api/tools/shell/execute",
            "/api/tools/git/status",
            "/api/tools/memory/store",
            "/api/tools/plan/create",
            "/api/tools/language/validate",
            "/api/tools/skills/list",
            "/api/tools/subagent/list",
        },
        {
            "/api/tools/docker/list",
            "/api/tools/http/request",
        },
        {
            "fs_read",
            "workspace_info",
            "shell_execute",
            "git_status",
            "memory_store",
            "plan_create",
            "lang_validate",
            "skills_list",
            "subagent_list",
        },
        {
            "docker_list",
            "http_request",
        },
        id="minus-docker-http",
    ),
    pytest.param(
        "fs,workspace,language",
        {
            "/api/tools/fs/read",
            "/api/tools/workspace/info",
            "/api/tools/language/validate",
        },
        {
            "/api/tools/shell/execute",
            "/api/tools/git/status",
            "/api/tools/docker/list",
            "/api/tools/http/request",
            "/api/tools/memory/store",
            "/api/tools/plan/create",
            "/api/tools/skills/list",
            "/api/tools/subagent/list",
        },
        {
            "fs_read",
            "workspace_info",
            "lang_validate",
        },
        {
            "shell_execute",
            "git_status",
            "docker_list",
            "http_request",
            "memory_store",
            "plan_create",
            "skills_list",
            "subagent_list",
        },
        id="explicit-allowlist",
    ),
]


@pytest.mark.parametrize(
    "modules_env,present_paths,absent_paths,present_tools,absent_tools",
    MODULE_MATRIX_CASES,
)
@pytest.mark.asyncio
async def test_module_matrix_openapi_and_mcp(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    modules_env: str,
    present_paths: set[str],
    absent_paths: set[str],
    present_tools: set[str],
    absent_tools: set[str],
):
    """OpenAPI + MCP reflect module matrix combinations consistently."""
    app, registry, mcp = _build_registry(tmp_path, monkeypatch, modules_env)
    assert registry.load_order

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            openapi = (await client.get("/openapi.json")).json()
            paths = set(openapi.get("paths", {}).keys())

            for expected in present_paths:
                assert expected in paths, f"missing expected OpenAPI path for {modules_env}: {expected}"
            for unexpected in absent_paths:
                assert unexpected not in paths, f"unexpected OpenAPI path for {modules_env}: {unexpected}"

            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
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

            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if session_id:
                headers["Mcp-Session-Id"] = session_id

            list_response = await client.post(
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                headers=headers,
            )
            payload = list_response.json()
            tool_names = {tool["name"] for tool in payload["result"]["tools"]}

            for expected in present_tools:
                assert expected in tool_names, f"missing expected MCP tool for {modules_env}: {expected}"
            for unexpected in absent_tools:
                assert unexpected not in tool_names, f"unexpected MCP tool for {modules_env}: {unexpected}"
    finally:
        if hasattr(mcp, "_http_transport") and mcp._http_transport:
            await mcp._http_transport.shutdown()


def test_module_dependency_edges_for_enabled_and_disabled_dependencies():
    """Dependency edges must load in topological order and fail when missing from selection."""

    class CoreModule(ToolModule):
        MODULE_NAME = "core"

        @property
        def name(self):
            return self.MODULE_NAME

        @property
        def display_name(self):
            return "Core"

        @property
        def description(self):
            return "Core module"

        @property
        def dependencies(self):
            return []

        def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
            return None

    class DependentModule(ToolModule):
        MODULE_NAME = "dependent"

        @property
        def name(self):
            return self.MODULE_NAME

        @property
        def display_name(self):
            return "Dependent"

        @property
        def description(self):
            return "Dependent module"

        @property
        def dependencies(self):
            return ["core"]

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
    available = {"core": CoreModule, "dependent": DependentModule}

    load_order = registry.resolve_load_order(["dependent", "core"], available)
    assert load_order == ["core", "dependent"]

    with pytest.raises(ModuleResolutionError, match="depends on 'core', but it is not enabled"):
        registry.resolve_load_order(["dependent"], available)

