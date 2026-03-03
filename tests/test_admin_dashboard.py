"""Tests for admin dashboard API endpoints and related UX behavior."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
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
    from anyide.main import app, db

    # Connect to database before tests
    await db.connect()

    from anyide import main as main_module
    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac

    # Cleanup
    await db.close()

    # Restore originals
    anyide.config.load_config = original_load


@pytest.fixture
async def auth_headers(client):
    """Create authenticated session by logging in."""
    response = await client.post(
        "/admin/api/login",
        json={"password": "admin"}
    )
    assert response.status_code == 200

    # Avoid deprecated per-request cookies=... by attaching cookies to the client.
    for key, value in response.cookies.items():
        client.cookies.set(key, value)
    return response.cookies


class TestDetailedHealthEndpoint:
    """Tests for the detailed health endpoint."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database."""
        db = AsyncMock()
        db.connection = AsyncMock()
        return db

    @pytest.fixture
    def mock_app_state(self):
        """Create mock app state."""
        app_state = MagicMock()
        app_state.start_time = 1000.0
        return app_state

    @pytest.mark.asyncio
    async def test_detailed_health_returns_all_metrics(self, client, auth_headers):
        """Test that detailed health returns all expected metrics."""
        response = await client.get("/admin/api/health/detailed")

        assert response.status_code == 200
        data = response.json()

        # Check all required fields are present
        required_fields = [
            "uptime", "pending_hitl", "tools_executed", "error_rate",
            "memory_used_mb", "memory_total_mb", "memory_percent",
            "cpu_percent", "db_size_mb", "db_path",
            "workspace_size_mb", "workspace_path",
            "websocket_connections", "python_version", "platform", "version"
        ]

        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_detailed_health_requires_auth(self, client):
        """Test that detailed health requires authentication."""
        response = await client.get("/admin/api/health/detailed")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_detailed_health_returns_numeric_values(self, client, auth_headers):
        """Test that numeric fields contain numeric values."""
        response = await client.get("/admin/api/health/detailed")

        assert response.status_code == 200
        data = response.json()

        assert isinstance(data["uptime"], int)
        assert isinstance(data["pending_hitl"], int)
        assert isinstance(data["tools_executed"], int)
        assert isinstance(data["error_rate"], (int, float))
        assert isinstance(data["memory_used_mb"], (int, float))
        assert isinstance(data["memory_total_mb"], (int, float))
        assert isinstance(data["memory_percent"], (int, float))
        assert isinstance(data["cpu_percent"], (int, float))


class TestToolExplorerEndpoint:
    """Tests for the tool explorer endpoints."""

    @pytest.mark.asyncio
    async def test_list_tools_returns_tools(self, client, auth_headers):
        """Test that list tools returns a list of tools."""
        response = await client.get("/admin/api/tools")

        assert response.status_code == 200
        data = response.json()

        assert "tools" in data
        assert "total" in data
        assert isinstance(data["tools"], list)
        assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_list_tools_requires_auth(self, client):
        """Test that list tools requires authentication."""
        response = await client.get("/admin/api/tools")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_tool_schema_has_required_fields(self, client, auth_headers):
        """Test that each tool has required fields."""
        response = await client.get("/admin/api/tools")

        assert response.status_code == 200
        data = response.json()

        required_fields = ["name", "category", "description", "input_schema", "requires_hitl"]

        for tool in data["tools"]:
            for field in required_fields:
                assert field in tool, f"Tool missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_specific_tool_schema(self, client, auth_headers):
        """Test getting schema for a specific tool."""
        # First get the list of tools
        list_response = await client.get("/admin/api/tools")
        assert list_response.status_code == 200

        tools = list_response.json()["tools"]
        if len(tools) > 0:
            tool = tools[0]
            response = await client.get(
                f"/admin/api/tools/{tool['category']}/{tool['name']}",
            )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == tool["name"]
            assert data["category"] == tool["category"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_tool_returns_404(self, client, auth_headers):
        """Test that getting a nonexistent tool returns 404."""
        response = await client.get("/admin/api/tools/nonexistent/nonexistent_tool")
        assert response.status_code == 404


class TestConfigEndpoint:
    """Tests for the configuration viewer endpoint."""

    @pytest.mark.asyncio
    async def test_get_config_returns_config(self, client, auth_headers):
        """Test that get config returns configuration."""
        response = await client.get("/admin/api/config")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        required_fields = [
            "auth_enabled", "workspace_path", "database_path",
            "log_level", "http_config", "policy_rules_count", "tool_configs", "llm_endpoints"
        ]

        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_get_config_requires_auth(self, client):
        """Test that get config requires authentication."""
        response = await client.get("/admin/api/config")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_config_http_config_has_required_fields(self, client, auth_headers):
        """Test that http_config has required fields."""
        response = await client.get("/admin/api/config")

        assert response.status_code == 200
        data = response.json()

        http_config = data["http_config"]
        http_fields = [
            "block_private_ips", "block_metadata_endpoints",
            "allow_domains", "block_domains", "timeout_seconds"
        ]

        for field in http_fields:
            assert field in http_config, f"Missing http_config field: {field}"


class TestAuditLogFiltering:
    """Tests for audit log filtering and export."""

    @pytest.mark.asyncio
    async def test_filtered_audit_logs_returns_logs(self, client, auth_headers):
        """Test that filtered audit logs returns logs."""
        response = await client.get("/admin/api/audit/filtered")

        assert response.status_code == 200
        data = response.json()

        assert "logs" in data
        assert "total" in data
        assert "filtered" in data
        assert isinstance(data["logs"], list)

    @pytest.mark.asyncio
    async def test_filtered_audit_logs_requires_auth(self, client):
        """Test that filtered audit logs requires authentication."""
        response = await client.get("/admin/api/audit/filtered")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_filtered_audit_logs_with_status_filter(self, client, auth_headers):
        """Test filtering audit logs by status."""
        response = await client.get(
            "/admin/api/audit/filtered?status=success",
        )

        assert response.status_code == 200
        data = response.json()

        # All returned logs should have status=success
        for log in data["logs"]:
            assert log["status"] == "success"


class TestLLMAdminEndpoints:
    """Tests for admin-only LLM configuration endpoints."""

    @pytest.mark.asyncio
    async def test_list_llm_endpoints_requires_auth(self, client):
        response = await client.get("/admin/api/llm/endpoints")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_llm_endpoints_returns_sanitized_list(self, client, auth_headers):
        response = await client.get("/admin/api/llm/endpoints")
        assert response.status_code == 200

        data = response.json()
        assert "endpoints" in data
        assert "total" in data
        assert isinstance(data["endpoints"], list)

    @pytest.mark.asyncio
    async def test_llm_test_endpoint_requires_auth(self, client):
        response = await client.post(
            "/admin/api/llm/test",
            json={"endpoint_id": "missing"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_llm_test_endpoint_handles_unknown_endpoint(self, client, auth_headers):
        response = await client.post(
            "/admin/api/llm/test",
            json={"endpoint_id": "missing"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is False
        assert data["error_type"] == "config_error"

    @pytest.mark.asyncio
    async def test_filtered_audit_logs_with_category_filter(self, client, auth_headers):
        """Test filtering audit logs by category."""
        response = await client.get(
            "/admin/api/audit/filtered?tool_category=fs",
        )

        assert response.status_code == 200
        data = response.json()

        # All returned logs should have tool_category=fs
        for log in data["logs"]:
            assert log["tool_category"] == "fs"

    @pytest.mark.asyncio
    async def test_filtered_audit_logs_with_pagination(self, client, auth_headers):
        """Test pagination of filtered audit logs."""
        response = await client.get(
            "/admin/api/audit/filtered?limit=10&offset=0",
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data["logs"]) <= 10


class TestAuditLogExport:
    """Tests for audit log export functionality."""

    @pytest.mark.asyncio
    async def test_export_audit_logs_json(self, client, auth_headers):
        """Test exporting audit logs as JSON."""
        response = await client.get(
            "/admin/api/audit/export?format=json",
        )

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")

        # Should be valid JSON
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_export_audit_logs_csv(self, client, auth_headers):
        """Test exporting audit logs as CSV."""
        response = await client.get(
            "/admin/api/audit/export?format=csv",
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")
        assert ".csv" in response.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_export_audit_logs_requires_auth(self, client):
        """Test that export requires authentication."""
        response = await client.get("/admin/api/audit/export?format=json")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_with_filters(self, client, auth_headers):
        """Test exporting with filters applied."""
        response = await client.get(
            "/admin/api/audit/export?format=json&status=success",
        )

        assert response.status_code == 200
        data = response.json()

        # All exported logs should have status=success
        for log in data:
            assert log["status"] == "success"


class TestDashboardStatsEndpoint:
    """Tests for the dashboard stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_dashboard_stats(self, client, auth_headers):
        """Test getting dashboard stats."""
        response = await client.get("/admin/api/stats")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        required_fields = [
            "tool_stats", "status_stats", "hourly_stats",
            "duration_stats", "pending_hitl"
        ]

        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_dashboard_stats_requires_auth(self, client):
        """Test that dashboard stats requires authentication."""
        response = await client.get("/admin/api/stats")
        assert response.status_code == 401


class TestContainerEndpoints:
    """Tests for container management endpoints."""

    @pytest.mark.asyncio
    async def test_list_containers(self, client, auth_headers):
        """Test listing containers."""
        response = await client.get("/admin/api/containers")

        # This may fail if Docker is not available, so we just check the endpoint exists
        assert response.status_code in [200, 503]

    @pytest.mark.asyncio
    async def test_list_containers_requires_auth(self, client):
        """Test that listing containers requires authentication."""
        response = await client.get("/admin/api/containers")
        assert response.status_code == 401


class TestWebSocketConnectionTracking:
    """Tests for WebSocket connection tracking."""

    def test_increment_ws_connections(self):
        """Test incrementing WebSocket connection count."""
        from anyide.admin_api import increment_ws_connections, websocket_connections

        initial = websocket_connections
        increment_ws_connections()

        from anyide.admin_api import websocket_connections as new_count
        assert new_count == initial + 1

    def test_decrement_ws_connections(self):
        """Test decrementing WebSocket connection count."""
        from anyide.admin_api import decrement_ws_connections, websocket_connections

        initial = websocket_connections
        decrement_ws_connections()

        from anyide.admin_api import websocket_connections as new_count
        assert new_count == max(0, initial - 1)

    def test_decrement_does_not_go_negative(self):
        """Test that decrement doesn't go below zero."""
        from anyide.admin_api import decrement_ws_connections

        # Decrement many times
        for _ in range(10):
            decrement_ws_connections()

        from anyide.admin_api import websocket_connections as new_count
        assert new_count >= 0


@pytest.mark.asyncio
class TestAuthenticationFlow:
    """Tests for the complete authentication flow."""

    async def test_login_with_valid_password(self, client):
        """Test login with valid password."""
        response = await client.post(
            "/admin/api/login",
            json={"password": "admin"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "token" in data

    async def test_login_with_invalid_password(self, client):
        """Test login with invalid password."""
        response = await client.post(
            "/admin/api/login",
            json={"password": "wrong_password"}
        )

        assert response.status_code == 401

    async def test_login_uses_anyide_admin_password_env_override(self, client, monkeypatch):
        """ANYIDE_ADMIN_PASSWORD should override config and legacy defaults."""
        monkeypatch.setenv("ANYIDE_ADMIN_PASSWORD", "env-secret-123")
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

        from anyide import main as main_module
        from anyide.config import load_config

        monkeypatch.setattr(main_module, "config", load_config())

        wrong = await client.post(
            "/admin/api/login",
            json={"password": "admin"},
        )
        correct = await client.post(
            "/admin/api/login",
            json={"password": "env-secret-123"},
        )

        assert wrong.status_code == 401
        assert correct.status_code == 200
        assert "session_token" in correct.cookies

    async def test_logout(self, client, auth_headers):
        """Test logout."""
        response = await client.post("/admin/api/logout")
        assert response.status_code == 200

    async def test_protected_endpoint_accepts_bearer_token(self, client):
        """Protected admin endpoints should accept Bearer token auth fallback."""
        login_response = await client.post(
            "/admin/api/login",
            json={"password": "admin"},
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]

        response = await client.get(
            "/admin/api/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    async def test_access_protected_endpoint_after_logout(self, client, auth_headers):
        """Test that protected endpoints are inaccessible after logout."""
        # Logout
        await client.post("/admin/api/logout")

        # Try to access protected endpoint
        response = await client.get("/admin/api/health")
        assert response.status_code == 401
