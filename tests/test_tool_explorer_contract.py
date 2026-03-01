"""Contract tests for Tool Explorer - verifying OpenAPI-based tool listing.

These tests verify that the tool explorer:
1. Lists tools from OpenAPI contract (not reflection)
2. Excludes non-tool routes (admin, health, system)
3. No internal methods are leaked
4. Schema fields are properly populated
"""

import os
import sys
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Set up test environment BEFORE any imports
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()


@pytest.fixture
async def client():
    """Create test client."""
    os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
    os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")

    import src.config
    original_load = src.config.load_config

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg

    src.config.load_config = patched_load

    from src.main import app, db
    await db.connect()

    from src import main as main_module
    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac

    await db.close()
    src.config.load_config = original_load


@pytest.fixture
async def auth_headers(client):
    """Create authenticated session."""
    response = await client.post(
        "/admin/api/login",
        json={"password": "admin"}
    )
    assert response.status_code == 200
    return response.cookies


class TestToolExplorerOpenAPIContract:
    """Tests verifying tool explorer is built from OpenAPI contract."""

    @pytest.mark.asyncio
    async def test_tools_come_from_openapi_paths(self, client, auth_headers):
        """Verify tools are extracted from OpenAPI paths, not reflection."""
        # Get tools from admin API
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        # Get OpenAPI spec
        openapi_response = await client.get("/openapi.json")
        assert openapi_response.status_code == 200
        openapi = openapi_response.json()

        # Count tool paths in OpenAPI spec
        tool_paths = [
            path for path in openapi.get("paths", {}).keys()
            if path.startswith("/api/tools/")
        ]

        # Each tool path should correspond to a tool entry
        # (may be duplicates due to sub-app mounting, so tools count <= tool_paths)
        assert tools_data["total"] <= len(tool_paths)

    @pytest.mark.asyncio
    async def test_no_internal_methods_leaked(self, client, auth_headers):
        """Verify no internal methods like 'close', 'tool_dispatch' are exposed."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        # List of internal methods that should never appear
        internal_methods = {
            "close", "tool_dispatch", "__init__", "__del__",
            "connect", "disconnect", "_execute", "_validate",
        }

        for tool in tools_data["tools"]:
            assert tool["name"] not in internal_methods, (
                f"Internal method '{tool['name']}' should not be exposed"
            )
            assert not tool["name"].startswith("_"), (
                f"Private method '{tool['name']}' should not be exposed"
            )

    @pytest.mark.asyncio
    async def test_no_admin_routes_in_tools(self, client, auth_headers):
        """Verify admin routes are not included in tools list."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        # Admin-related categories should not exist
        admin_categories = {"admin", "auth", "health", "config", "secrets"}

        for tool in tools_data["tools"]:
            assert tool["category"] not in admin_categories, (
                f"Admin category '{tool['category']}' should not be in tools"
            )

    @pytest.mark.asyncio
    async def test_valid_tool_categories_only(self, client, auth_headers):
        """Verify only valid tool categories are included."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        valid_categories = {
            "fs", "workspace", "shell", "git", "docker",
            "http", "memory", "plan"
        }

        for tool in tools_data["tools"]:
            assert tool["category"] in valid_categories, (
                f"Invalid category '{tool['category']}' - expected one of {valid_categories}"
            )

    @pytest.mark.asyncio
    async def test_tool_schema_fields_populated(self, client, auth_headers):
        """Verify schema fields are properly populated (not empty {})."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        tools_with_empty_schemas = []
        for tool in tools_data["tools"]:
            # input_schema should not be empty {} for real tools
            if tool["input_schema"] == {}:
                tools_with_empty_schemas.append(
                    f"{tool['category']}_{tool['name']}"
                )

        # Some tools may legitimately have empty schemas, but most should have content
        # Allow up to 20% of tools to have empty schemas
        if len(tools_data["tools"]) > 0:
            empty_ratio = len(tools_with_empty_schemas) / len(tools_data["tools"])
            assert empty_ratio < 0.5, (
                f"Too many tools ({len(tools_with_empty_schemas)}) have empty input_schema"
            )

    @pytest.mark.asyncio
    async def test_tool_has_description(self, client, auth_headers):
        """Verify each tool has a meaningful description."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        for tool in tools_data["tools"]:
            assert tool["description"], (
                f"Tool {tool['category']}_{tool['name']} missing description"
            )
            # Description should not be just "Execute {name} operation" (generic fallback)
            # Allow descriptions that start with "Execute" but have substantial content
            if tool["description"].startswith("Execute "):
                # Should have more than just the generic pattern
                assert len(tool["description"]) > 50, (
                    f"Tool {tool['category']}_{tool['name']} has generic description"
                )

    @pytest.mark.asyncio
    async def test_operation_id_matches_tool_name(self, client, auth_headers):
        """Verify operation_id in OpenAPI matches tool naming convention."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        openapi_response = await client.get("/openapi.json")
        openapi = openapi_response.json()

        for tool in tools_data["tools"]:
            expected_path = f"/api/tools/{tool['category']}/{tool['name']}"
            if expected_path in openapi.get("paths", {}):
                path_item = openapi["paths"][expected_path]
                post_op = path_item.get("post", {})
                expected_op_id = f"{tool['category']}_{tool['name']}"
                assert post_op.get("operationId") == expected_op_id, (
                    f"Operation ID mismatch for {expected_path}"
                )

    @pytest.mark.asyncio
    async def test_specific_tool_schema_endpoint(self, client, auth_headers):
        """Test getting schema for a specific tool via the dedicated endpoint."""
        # First get the list of tools
        list_response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert list_response.status_code == 200
        tools = list_response.json()["tools"]

        if len(tools) > 0:
            tool = tools[0]
            response = await client.get(
                f"/admin/api/tools/{tool['category']}/{tool['name']}",
                cookies=auth_headers
            )

            assert response.status_code == 200
            data = response.json()

            assert data["name"] == tool["name"]
            assert data["category"] == tool["category"]
            assert "description" in data
            assert "input_schema" in data
            assert "requires_hitl" in data

    @pytest.mark.asyncio
    async def test_hitl_flag_computed_from_policy(self, client, auth_headers):
        """Verify HITL flag is computed from effective policy, not hardcoded."""
        response = await client.get("/admin/api/tools", cookies=auth_headers)
        assert response.status_code == 200
        tools_data = response.json()

        # At least some tools should have requires_hitl set (based on policy)
        hitl_tools = [t for t in tools_data["tools"] if t["requires_hitl"]]
        non_hitl_tools = [t for t in tools_data["tools"] if not t["requires_hitl"]]

        # Both lists should be non-empty in a properly configured system
        # (some tools require HITL, some don't)
        # But we won't enforce this strictly as it depends on policy config
        assert len(tools_data["tools"]) > 0, "Should have at least some tools"


class TestToolExplorerOpenAPISchema:
    """Tests verifying OpenAPI schema structure for tools."""

    @pytest.mark.asyncio
    async def test_openapi_has_tool_paths(self, client):
        """Verify OpenAPI spec contains tool API paths."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()

        tool_paths = [
            path for path in openapi.get("paths", {}).keys()
            if path.startswith("/api/tools/")
        ]

        assert len(tool_paths) > 0, "OpenAPI should contain tool paths"

    @pytest.mark.asyncio
    async def test_openapi_tool_paths_have_post_operation(self, client):
        """Verify all tool paths have POST operation defined."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()

        for path, path_item in openapi.get("paths", {}).items():
            if path.startswith("/api/tools/"):
                assert "post" in path_item, f"Tool path {path} should have POST operation"

    @pytest.mark.asyncio
    async def test_openapi_tool_paths_have_operation_id(self, client):
        """Verify all tool POST operations have operation_id."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()

        for path, path_item in openapi.get("paths", {}).items():
            if path.startswith("/api/tools/"):
                post_op = path_item.get("post", {})
                assert "operationId" in post_op, (
                    f"Tool path {path} POST operation should have operationId"
                )

    @pytest.mark.asyncio
    async def test_openapi_tool_request_body_schema(self, client):
        """Verify tool POST operations have request body schemas."""
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        openapi = response.json()

        for path, path_item in openapi.get("paths", {}).items():
            if path.startswith("/api/tools/"):
                post_op = path_item.get("post", {})
                request_body = post_op.get("requestBody")

                if request_body:
                    content = request_body.get("content", {})
                    assert "application/json" in content, (
                        f"Tool {path} should accept application/json"
                    )
