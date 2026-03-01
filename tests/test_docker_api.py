"""Integration tests for Docker API endpoints."""

import os
import tempfile

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

# Set safe defaults before importing anyide.main (which initializes global services)
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()
os.environ.setdefault("WORKSPACE_BASE_DIR", TEST_WORKSPACE)
os.environ.setdefault("DB_PATH", os.path.join(TEST_DATA_DIR, "hostbridge.db"))

from anyide.main import app


@pytest.fixture(autouse=True)
async def connected_db():
    """Ensure app database is connected for each test."""
    from anyide.main import db

    await db.connect()
    try:
        yield
    finally:
        await db.close()


@pytest.fixture
def mock_docker_tools():
    """Mock Docker tools."""
    import anyide.main as main_module

    docker_module = main_module.module_registry.modules.get("docker")
    assert docker_module is not None, "docker module must be loaded for docker API tests"

    with patch.object(docker_module, "docker_tools") as mock:
        # Keep backward-compat global in sync for admin API/tests that import it.
        original_global = main_module.docker_tools
        main_module.docker_tools = mock
        try:
            yield mock
        finally:
            main_module.docker_tools = original_global


@pytest.mark.asyncio
async def test_docker_list_endpoint(mock_docker_tools):
    """Test docker_list endpoint."""
    # Mock response
    from anyide.models import DockerListResponse
    mock_docker_tools.list_containers = AsyncMock(return_value=DockerListResponse(
        containers=[
            {
                "id": "abc123",
                "name": "test-container",
                "image": "nginx:latest",
                "status": "Up 2 hours",
                "state": "running",
                "ports": ["0.0.0.0:8080->80/tcp"],
                "created": "2024-01-01T00:00:00",
            }
        ],
        total_count=1,
    ))
    
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/tools/docker/list",
            json={"all": True}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 1
    assert len(data["containers"]) == 1
    assert data["containers"][0]["name"] == "test-container"


@pytest.mark.asyncio
async def test_docker_inspect_endpoint(mock_docker_tools):
    """Test docker_inspect endpoint."""
    from anyide.models import DockerInspectResponse
    mock_docker_tools.inspect_container = AsyncMock(return_value=DockerInspectResponse(
        id="abc123",
        name="test-container",
        image="nginx:latest",
        status="running",
        config={"hostname": "test"},
        network={"networks": ["bridge"]},
        mounts=[],
        ports={},
        created="2024-01-01T00:00:00",
        state={"status": "running", "running": True},
    ))
    
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/tools/docker/inspect",
            json={"container": "test-container"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "test-container"
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_docker_logs_endpoint(mock_docker_tools):
    """Test docker_logs endpoint."""
    from anyide.models import DockerLogsResponse
    mock_docker_tools.get_logs = AsyncMock(return_value=DockerLogsResponse(
        logs="Log line 1\nLog line 2\n",
        container="test-container",
        line_count=2,
    ))
    
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/tools/docker/logs",
            json={"container": "test-container", "tail": 100}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["container"] == "test-container"
    assert data["line_count"] == 2
    assert "Log line 1" in data["logs"]


@pytest.mark.asyncio
async def test_docker_action_endpoint_requires_hitl(mock_docker_tools):
    """Test docker_action endpoint requires HITL."""
    from anyide.models import DockerActionResponse
    
    # Mock HITL manager to auto-approve
    with patch('anyide.main.hitl_manager') as mock_hitl:
        mock_hitl.create_request = AsyncMock(return_value=MagicMock(id="hitl-test-id"))
        mock_hitl.wait_for_decision = AsyncMock(return_value=("approved", None))
        
        mock_docker_tools.container_action = AsyncMock(return_value=DockerActionResponse(
            container="test-container",
            action="restart",
            success=True,
            previous_status="running",
            new_status="running",
            message="Successfully restarted container",
        ))
        
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/tools/docker/action",
                json={"container": "test-container", "action": "restart"}
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"] == "restart"
        
        # Verify HITL was triggered
        mock_hitl.create_request.assert_called_once()


@pytest.mark.asyncio
async def test_docker_list_sub_app_endpoint(mock_docker_tools):
    """Test docker_list sub-app endpoint."""
    from anyide.models import DockerListResponse
    mock_docker_tools.list_containers = AsyncMock(return_value=DockerListResponse(
        containers=[],
        total_count=0,
    ))
    
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/tools/docker/list",
            json={"all": False}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_count"] == 0


@pytest.mark.asyncio
async def test_docker_error_handling(mock_docker_tools):
    """Test Docker error handling."""
    mock_docker_tools.list_containers = AsyncMock(
        side_effect=RuntimeError("Docker daemon not running")
    )
    
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/tools/docker/list",
            json={"all": True}
        )
    
    assert response.status_code == 500
    data = response.json()
    assert data["error"] is True
    assert "error_type" in data


@pytest.mark.asyncio
async def test_docker_container_not_found(mock_docker_tools):
    """Test container not found error."""
    mock_docker_tools.inspect_container = AsyncMock(
        side_effect=ValueError("Container not found: nonexistent")
    )
    
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/tools/docker/inspect",
            json={"container": "nonexistent"}
        )
    
    assert response.status_code == 400
    data = response.json()
    assert data["error"] is True
    assert "not found" in data["message"].lower()
