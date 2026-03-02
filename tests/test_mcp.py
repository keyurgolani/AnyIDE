"""Tests for MCP endpoint."""

import os
import tempfile
import pytest
from httpx import AsyncClient, ASGITransport

# Set up test environment BEFORE any imports
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()


@pytest.fixture
async def client():
    """Create test client."""
    # Set environment variables before importing
    os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
    os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")

    # Patch config loading
    import anyide.config
    original_load = anyide.config.load_config

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg

    anyide.config.load_config = patched_load

    # Now import the app and initialize database
    from anyide.main import app, db, mcp, hitl_manager

    # Connect to database before tests
    await db.connect()

    # Update workspace manager base dir
    from anyide import main as main_module
    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)

    # The MCP server's session manager will be started lazily on first request
    # No need to manually start it - the FastApiHttpSessionManager handles this
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    # Cleanup: shutdown the MCP transport after tests
    if hasattr(mcp, '_http_transport') and mcp._http_transport:
        await mcp._http_transport.shutdown()

    # Stop HITL manager cleanup task
    await hitl_manager.stop()

    # Close database connection
    await db.close()

    # Restore originals
    anyide.config.load_config = original_load


class TestMCPStreamableHTTP:
    """Test MCP Streamable HTTP endpoint functionality."""
    
    @pytest.mark.asyncio
    async def test_mcp_initialize(self, client):
        """Test MCP initialize handshake."""
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        response = await client.post(
            "/mcp",
            json=init_request,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        
        assert response.status_code == 200
        result = response.json()
        
        # Check response structure
        assert "jsonrpc" in result
        assert result["jsonrpc"] == "2.0"
        assert "result" in result
        assert "protocolVersion" in result["result"]
        assert "capabilities" in result["result"]
        assert "serverInfo" in result["result"]
        
        # Check server info
        server_info = result["result"]["serverInfo"]
        assert "name" in server_info
        assert server_info["name"] == "AnyIDE"
        
        # Check for session ID in headers
        session_id = response.headers.get("Mcp-Session-Id")
        # Session ID is optional but recommended
        if session_id:
            assert len(session_id) > 0
    
    @pytest.mark.asyncio
    async def test_mcp_tools_list(self, client):
        """Test listing tools via MCP."""
        # First initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }
        
        init_response = await client.post(
            "/mcp",
            json=init_request,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        
        session_id = init_response.headers.get("Mcp-Session-Id")
        
        # Now list tools
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        
        response = await client.post("/mcp", json=list_request, headers=headers)
        
        assert response.status_code == 200
        result = response.json()
        
        # Check response structure
        assert "result" in result
        assert "tools" in result["result"]
        
        tools = result["result"]["tools"]
        assert len(tools) > 0
        
        # Check that our tools are present
        tool_names = [tool["name"] for tool in tools]
        assert "fs_read" in tool_names
        assert "fs_write" in tool_names
        assert "workspace_info" in tool_names
        
        # Check tool structure
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
    
    @pytest.mark.asyncio
    async def test_mcp_transport_is_streamable_http(self, client):
        """Verify that Streamable HTTP transport is being used (not legacy SSE)."""
        # Streamable HTTP uses POST for all requests
        # Legacy SSE would use GET and return event stream
        
        # Try POST (should work with Streamable HTTP)
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }
        
        response = await client.post(
            "/mcp",
            json=init_request,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/json"
        
        # Verify it's not SSE (which would have text/event-stream)
        assert "text/event-stream" not in response.headers.get("content-type", "")


class TestMCPToolParity:
    """Test MCP and OpenAPI tool surface parity."""

    # Expected tool operation IDs from OpenAPI (root endpoints only, not sub-app)
    EXPECTED_TOOL_IDS = {
        # Filesystem tools
        "fs_read", "fs_write", "fs_list", "fs_search",
        # Workspace tools
        "workspace_info", "workspace_secrets_list",
        # Shell tools
        "shell_execute",
        # Git tools
        "git_status", "git_log", "git_diff", "git_commit", "git_push",
        "git_pull", "git_checkout", "git_branch", "git_list_branches",
        "git_stash", "git_show", "git_remote",
        # Docker tools
        "docker_list", "docker_inspect", "docker_logs", "docker_action",
        # HTTP tools
        "http_request",
        # Memory tools
        "memory_store", "memory_get", "memory_search", "memory_update",
        "memory_delete", "memory_link", "memory_children", "memory_ancestors",
        "memory_related", "memory_subtree", "memory_roots", "memory_stats",
        # Plan tools
        "plan_create", "plan_execute", "plan_update_task", "plan_status", "plan_list", "plan_cancel",
        # Language tools
        "lang_read_file", "lang_skeleton", "lang_diff", "lang_apply_patch",
        "lang_create_file", "lang_index", "lang_search_symbols",
        "lang_reference_graph", "lang_validate",
        # Skills tools
        "skills_list", "skills_read", "skills_read_file", "skills_search", "skills_install",
    }

    # Admin/auth operation IDs that should NEVER appear in MCP
    EXCLUDED_OPERATION_IDS = {
        # Admin login/logout
        "login", "logout",
        # Admin API endpoints (these use admin tag)
        "get_audit_logs", "get_system_health", "list_secrets", "reload_secrets",
        "get_detailed_health", "list_tools", "get_tool_schema", "get_config",
        "get_filtered_audit_logs", "export_audit_logs", "list_containers",
        "get_container_logs", "get_dashboard_stats",
    }

    # Tool tags that should be included in MCP
    TOOL_TAGS = {
        "filesystem", "workspace", "shell", "git", "docker", "http", "memory", "plan", "language", "skills"
    }

    @pytest.mark.asyncio
    async def test_mcp_contains_all_expected_tools(self, client):
        """Test that MCP contains all expected tool operation IDs including Docker tools."""
        # First initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        init_response = await client.post(
            "/mcp",
            json=init_request,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )

        session_id = init_response.headers.get("Mcp-Session-Id")

        # List tools
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        response = await client.post("/mcp", json=list_request, headers=headers)

        assert response.status_code == 200
        result = response.json()

        mcp_tool_names = set(tool["name"] for tool in result["result"]["tools"])

        # Check that all expected tools are present
        missing_tools = self.EXPECTED_TOOL_IDS - mcp_tool_names
        assert not missing_tools, f"MCP is missing expected tools: {missing_tools}"

    @pytest.mark.asyncio
    async def test_mcp_excludes_admin_operations(self, client):
        """Test that MCP does NOT expose admin/auth/non-tool operations."""
        # First initialize
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        init_response = await client.post(
            "/mcp",
            json=init_request,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )

        session_id = init_response.headers.get("Mcp-Session-Id")

        # List tools
        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        response = await client.post("/mcp", json=list_request, headers=headers)

        assert response.status_code == 200
        result = response.json()

        mcp_tool_names = set(tool["name"] for tool in result["result"]["tools"])

        # Check that excluded operations are NOT present
        leaked_operations = self.EXCLUDED_OPERATION_IDS & mcp_tool_names
        assert not leaked_operations, f"MCP incorrectly exposes admin operations: {leaked_operations}"

    @pytest.mark.asyncio
    async def test_openapi_mcp_tool_parity(self, client):
        """Test that OpenAPI tool operation IDs match MCP tool names."""
        from anyide.main import app

        # Get OpenAPI spec
        openapi_spec = app.openapi()

        # Extract operation IDs from OpenAPI spec for tool routes only
        openapi_tool_ops = set()
        for path, path_item in openapi_spec.get("paths", {}).items():
            # Only include /api/tools/* paths
            if path.startswith("/api/tools/"):
                for method, operation in path_item.items():
                    if method in ("get", "post", "put", "patch", "delete"):
                        if isinstance(operation, dict) and "operationId" in operation:
                            openapi_tool_ops.add(operation["operationId"])

        # Get MCP tools
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        init_response = await client.post(
            "/mcp",
            json=init_request,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )

        session_id = init_response.headers.get("Mcp-Session-Id")

        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        response = await client.post("/mcp", json=list_request, headers=headers)

        assert response.status_code == 200
        result = response.json()

        mcp_tool_names = set(tool["name"] for tool in result["result"]["tools"])

        # MCP tools should be a subset of OpenAPI tools (MCP may expose fewer, but not more)
        extra_in_mcp = mcp_tool_names - openapi_tool_ops
        assert not extra_in_mcp, f"MCP has tools not in OpenAPI: {extra_in_mcp}"

        # All expected tools should be in both
        expected_in_both = self.EXPECTED_TOOL_IDS & openapi_tool_ops & mcp_tool_names
        missing_from_either = self.EXPECTED_TOOL_IDS - expected_in_both
        assert not missing_from_either, f"Expected tools missing from OpenAPI or MCP: {missing_from_either}"

    @pytest.mark.asyncio
    async def test_docker_tools_in_mcp(self, client):
        """Test that Docker tools are included in MCP (regression test for G1 gap)."""
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }

        init_response = await client.post(
            "/mcp",
            json=init_request,
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )

        session_id = init_response.headers.get("Mcp-Session-Id")

        list_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        response = await client.post("/mcp", json=list_request, headers=headers)

        assert response.status_code == 200
        result = response.json()

        mcp_tool_names = set(tool["name"] for tool in result["result"]["tools"])

        # Specifically check Docker tools
        docker_tools = {"docker_list", "docker_inspect", "docker_logs", "docker_action"}
        missing_docker = docker_tools - mcp_tool_names
        assert not missing_docker, f"Docker tools missing from MCP: {missing_docker}"
