"""Integration tests for API endpoints."""

import os
import sys
import tempfile
import pytest
from pathlib import Path
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
    import src.config
    original_load = src.config.load_config
    
    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg
    
    src.config.load_config = patched_load
    
    # Now import the app and initialize database
    from src.main import app, db
    
    # Connect to database before tests
    await db.connect()
    
    from src import main as main_module
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
    src.config.load_config = original_load


@pytest.fixture
def test_workspace():
    """Create test workspace with files."""
    workspace = Path(TEST_WORKSPACE)
    
    # Create test files
    (workspace / "test.txt").write_text("Test content\n")
    (workspace / "config.yaml").write_text("key: value\n")
    
    yield str(workspace)


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    async def test_health_check(self, client):
        """Test health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestFsReadEndpoint:
    """Test fs_read endpoint."""
    
    async def test_read_file_root_app(self, client, test_workspace):
        """Test reading file via root app endpoint."""
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "test.txt"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Test content\n"
        assert data["line_count"] == 1
        assert data["encoding"] == "utf-8"
        assert "path" in data
        assert "size_bytes" in data
    
    async def test_read_file_sub_app(self, client, test_workspace):
        """Test reading file via sub-app endpoint."""
        response = await client.post(
            "/tools/fs/read",
            json={"path": "test.txt"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Test content\n"
    
    async def test_read_nonexistent_file(self, client, test_workspace):
        """Test reading nonexistent file."""
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "nonexistent.txt"},
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data["error"] is True
        assert data["error_type"] == "file_not_found"
        assert "suggestion_tool" in data
    
    async def test_read_with_path_escape(self, client, test_workspace):
        """Test reading with path escape attempt."""
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "../../etc/passwd"},
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"] is True
        assert data["error_type"] == "security_error"
    
    async def test_read_with_line_range(self, client, test_workspace):
        """Test reading with line range."""
        # Create a multi-line file
        workspace = Path(test_workspace)
        (workspace / "multiline.txt").write_text("Line 1\nLine 2\nLine 3\n")
        
        response = await client.post(
            "/api/tools/fs/read",
            json={
                "path": "multiline.txt",
                "line_start": 2,
                "line_end": 2,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == "Line 2\n"


class TestWorkspaceInfoEndpoint:
    """Test workspace_info endpoint."""
    
    async def test_workspace_info_root_app(self, client, test_workspace):
        """Test workspace info via root app endpoint."""
        response = await client.post("/api/tools/workspace/info")
        
        assert response.status_code == 200
        data = response.json()
        assert "default_workspace" in data
        assert "available_directories" in data
        assert "disk_usage" in data
        assert "tool_categories" in data
        assert "secret_count" in data
        
        # Check disk usage structure
        assert "total" in data["disk_usage"]
        assert "used" in data["disk_usage"]
        assert "free" in data["disk_usage"]
    
    async def test_workspace_info_sub_app(self, client, test_workspace):
        """Test workspace info via sub-app endpoint."""
        response = await client.post("/tools/workspace/info")
        
        assert response.status_code == 200
        data = response.json()
        assert "default_workspace" in data


class TestOpenAPISpec:
    """Test OpenAPI specification."""
    
    async def test_root_openapi_spec(self, client):
        """Test root app OpenAPI spec."""
        response = await client.get("/openapi.json")
        
        assert response.status_code == 200
        spec = response.json()
        
        assert spec["info"]["title"] == "AnyIDE"
        assert "paths" in spec
        
        # Check that tools are present
        assert "/api/tools/fs/read" in spec["paths"]
        assert "/api/tools/workspace/info" in spec["paths"]
    
    async def test_fs_sub_app_openapi_spec(self, client):
        """Test filesystem sub-app OpenAPI spec."""
        response = await client.get("/tools/fs/openapi.json")
        
        assert response.status_code == 200
        spec = response.json()
        
        assert "Filesystem" in spec["info"]["title"]
        assert "/read" in spec["paths"]
    
    async def test_workspace_sub_app_openapi_spec(self, client):
        """Test workspace sub-app OpenAPI spec."""
        response = await client.get("/tools/workspace/openapi.json")
        
        assert response.status_code == 200
        spec = response.json()
        
        assert "Workspace" in spec["info"]["title"]
        assert "/info" in spec["paths"]


class TestAuditLogging:
    """Test audit logging."""
    
    async def test_successful_execution_logged(self, client, test_workspace):
        """Test that successful execution is logged."""
        # Make a request
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "test.txt"},
        )
        
        assert response.status_code == 200
        
        # Check audit log (we'll verify this by checking the database)
        from src.main import audit_logger
        
        logs = await audit_logger.get_recent_logs(limit=1)
        assert len(logs) > 0
        
        last_log = logs[0]
        assert last_log["tool_name"] == "read"
        assert last_log["tool_category"] == "fs"
        assert last_log["status"] == "success"
        assert last_log["protocol"] == "openapi"
    
    async def test_failed_execution_logged(self, client, test_workspace):
        """Test that failed execution is logged."""
        # Make a request that will fail
        response = await client.post(
            "/api/tools/fs/read",
            json={"path": "nonexistent.txt"},
        )
        
        assert response.status_code == 404
        
        # Check audit log
        from src.main import audit_logger
        
        # Get more logs to find the error one (in case previous tests added logs)
        logs = await audit_logger.get_recent_logs(limit=10)
        assert len(logs) > 0
        
        # Find the error log for this specific request
        error_logs = [log for log in logs if log["status"] == "error" and log["tool_name"] == "read"]
        assert len(error_logs) > 0
        
        last_log = error_logs[0]
        assert last_log["tool_name"] == "read"
        assert last_log["status"] == "error"
        assert last_log["error_message"] is not None
