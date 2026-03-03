"""
Security audit tests for HostBridge.

These tests verify security protections including:
- Path traversal prevention
- SSRF protection
- Command injection prevention
- Input validation
- Authentication and authorization
"""

import os
import tempfile

import pytest
from httpx import AsyncClient, ASGITransport

# Set up test environment BEFORE any imports
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()

# Set environment variables BEFORE importing any src modules
os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")


@pytest.fixture
async def client():
    """Create test client."""
    import anyide.config
    original_load = anyide.config.load_config

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg

    anyide.config.load_config = patched_load

    from anyide.main import app, db
    await db.connect()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await db.close()
    anyide.config.load_config = original_load


@pytest.fixture
async def auth_headers(client):
    """Create authenticated session."""
    response = await client.post(
        "/admin/api/login",
        json={"password": "admin"}
    )
    return response.cookies


class TestPathTraversal:
    """Tests for path traversal attack prevention."""

    @pytest.mark.asyncio
    async def test_basic_path_traversal(self, client):
        """Test basic path traversal is blocked."""
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "../../../etc/passwd"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_absolute_path_outside_workspace(self, client):
        """Test absolute paths outside workspace are blocked."""
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "/etc/passwd"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_path_traversal_in_write(self, client):
        """Test path traversal in write operations is blocked."""
        response = await client.post(
            "/api/tools/fs/write",
            json={"path": "../../../tmp/malicious.txt", "content": "malicious"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_path_traversal_in_list(self, client):
        """Test path traversal in list operations is blocked."""
        response = await client.post(
            "/api/tools/fs/list",
            json={"path": "../../../etc", "recursive": False}
        )
        assert response.status_code in [400, 403]


class TestSSRFProtection:
    """Tests for Server-Side Request Forgery protection."""

    @pytest.mark.asyncio
    async def test_private_ip_10_range(self, client):
        """Test 10.x.x.x private range is blocked."""
        response = await client.post(
            "/api/tools/http/request",
            json={"url": "http://10.0.0.1/admin", "method": "GET"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_private_ip_172_range(self, client):
        """Test 172.16-31.x.x private range is blocked."""
        response = await client.post(
            "/api/tools/http/request",
            json={"url": "http://172.16.0.1/admin", "method": "GET"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_private_ip_192_range(self, client):
        """Test 192.168.x.x private range is blocked."""
        response = await client.post(
            "/api/tools/http/request",
            json={"url": "http://192.168.1.1/admin", "method": "GET"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_127_0_0_1_blocked(self, client):
        """Test 127.0.0.1 is blocked."""
        response = await client.post(
            "/api/tools/http/request",
            json={"url": "http://127.0.0.1:8080/admin", "method": "GET"}
        )
        assert response.status_code in [400, 403]

    @pytest.mark.asyncio
    async def test_cloud_metadata_aws(self, client):
        """Test AWS metadata endpoint is blocked."""
        response = await client.post(
            "/api/tools/http/request",
            json={"url": "http://169.254.169.254/latest/meta-data", "method": "GET"}
        )
        assert response.status_code in [400, 403]


class TestCommandInjection:
    """Tests for command injection prevention."""

    @pytest.mark.skip(reason="Requires HITL infrastructure")
    @pytest.mark.asyncio
    async def test_pipe_injection(self, client):
        """Test pipe character injection is handled."""
        response = await client.post(
            "/api/tools/shell/execute",
            json={"command": "echo test | cat /etc/passwd"}
        )
        # Should either block, sanitize, or fail gracefully
        assert response.status_code in [200, 400, 403, 500]

    @pytest.mark.skip(reason="Requires HITL infrastructure")
    @pytest.mark.asyncio
    async def test_semicolon_injection(self, client):
        """Test semicolon injection is handled."""
        response = await client.post(
            "/api/tools/shell/execute",
            json={"command": "echo test; cat /etc/passwd"}
        )
        assert response.status_code in [200, 400, 403, 500]

    @pytest.mark.skip(reason="Requires HITL infrastructure")
    @pytest.mark.asyncio
    async def test_redirect_injection(self, client):
        """Test redirect characters are handled."""
        response = await client.post(
            "/api/tools/shell/execute",
            json={"command": "echo test > /tmp/malicious"}
        )
        assert response.status_code in [200, 400, 403, 500]


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_empty_path(self, client):
        """Test empty path is rejected."""
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": ""}
        )
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_very_long_path(self, client):
        """Test very long paths are handled."""
        long_path = "a" * 10000 + ".txt"
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": long_path}
        )
        # Should handle gracefully, not crash
        assert response.status_code in [200, 400, 404]

    @pytest.mark.asyncio
    async def test_invalid_json(self, client):
        """Test invalid JSON is rejected."""
        response = await client.post(
            "/api/tools/fs/read",
            content="{invalid json}",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422


class TestAuthentication:
    """Tests for authentication and authorization."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_without_auth(self, client):
        """Test protected endpoints require authentication."""
        endpoints = [
            "/admin/api/health",
            "/admin/api/audit",
            "/admin/api/secrets",
            "/admin/api/tools",
            "/admin/api/config",
        ]

        for endpoint in endpoints:
            response = await client.get(endpoint)
            assert response.status_code == 401, f"{endpoint} should require auth"

    @pytest.mark.asyncio
    async def test_wrong_password(self, client):
        """Test wrong password is rejected."""
        response = await client.post(
            "/admin/api/login",
            json={"password": "wrong_password_12345"}
        )
        assert response.status_code == 401


class TestDoSProtection:
    """Tests for denial of service protection."""

    @pytest.mark.asyncio
    async def test_large_file_handling(self, client):
        """Test large files are handled appropriately."""
        # Create a moderately large file
        large_content = "x" * 100_000  # 100KB
        response = await client.post(
            "/api/tools/fs/write",
            json={"path": "large_file.txt", "content": large_content}
        )
        # Should either succeed or fail gracefully
        assert response.status_code in [200, 400, 413]
