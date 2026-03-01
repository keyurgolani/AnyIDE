"""Tests for Docker tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from anyide.modules.docker.tools import DockerTools, DOCKER_AVAILABLE
from anyide.models import (
    DockerListRequest,
    DockerInspectRequest,
    DockerLogsRequest,
    DockerActionRequest,
)


@pytest.fixture
def docker_tools():
    """Create DockerTools instance."""
    return DockerTools()


@pytest.fixture
def mock_docker():
    """Create mock Docker client."""
    mock = MagicMock()
    mock.version = AsyncMock(return_value={"Version": "20.10.0"})
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_container():
    """Create mock container."""
    container = MagicMock()
    container.show = AsyncMock(return_value={
        "Id": "abc123def456" * 5,  # Long ID
        "Name": "/test-container",
        "Config": {
            "Image": "nginx:latest",
            "Hostname": "test-host",
            "User": "root",
            "Env": ["PATH=/usr/bin", "HOME=/root"],
            "Cmd": ["nginx", "-g", "daemon off;"],
            "Entrypoint": ["/docker-entrypoint.sh"],
            "WorkingDir": "/app",
            "Labels": {"app": "test"},
        },
        "State": {
            "Status": "running",
            "Running": True,
            "Paused": False,
            "Restarting": False,
            "Pid": 12345,
            "ExitCode": 0,
            "StartedAt": "2024-01-01T00:00:00Z",
            "FinishedAt": "0001-01-01T00:00:00Z",
        },
        "NetworkSettings": {
            "Networks": {"bridge": {}},
            "IPAddress": "172.17.0.2",
            "Gateway": "172.17.0.1",
            "Ports": {
                "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]
            },
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": "/host/path",
                "Destination": "/container/path",
                "Mode": "rw",
                "RW": True,
            }
        ],
        "Created": "2024-01-01T00:00:00Z",
    })
    container.start = AsyncMock()
    container.stop = AsyncMock()
    container.restart = AsyncMock()
    container.pause = AsyncMock()
    container.unpause = AsyncMock()
    container.log = AsyncMock(return_value=["Log line 1\n", "Log line 2\n"])
    return container


class TestDockerList:
    """Tests for docker_list tool."""

    @pytest.mark.asyncio
    async def test_list_all_containers(self, docker_tools, mock_docker):
        """Test listing all containers."""
        # Create mock container objects with .show() method
        mock_container1 = MagicMock()
        mock_container1.show = AsyncMock(return_value={
            "Id": "abc123" * 10,
            "Name": "/container1",
            "Config": {"Image": "nginx:latest"},
            "State": {"Status": "running"},
            "NetworkSettings": {"IPAddress": "172.17.0.2", "Ports": {}},
            "Created": "2024-01-01T00:00:00Z",
        })

        mock_container2 = MagicMock()
        mock_container2.show = AsyncMock(return_value={
            "Id": "def456" * 10,
            "Name": "/container2",
            "Config": {"Image": "postgres:14"},
            "State": {"Status": "exited"},
            "NetworkSettings": {"IPAddress": "", "Ports": {}},
            "Created": "2024-01-01T01:00:00Z",
        })

        mock_docker.containers.list = AsyncMock(return_value=[mock_container1, mock_container2])

        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerListRequest(all=True)
            response = await docker_tools.list_containers(request)

        assert response.total_count == 2
        assert len(response.containers) == 2
        assert response.containers[0]["name"] == "container1"
        assert response.containers[0]["state"] == "running"
        assert response.containers[1]["name"] == "container2"
        assert response.containers[1]["state"] == "exited"

    @pytest.mark.asyncio
    async def test_list_running_only(self, docker_tools, mock_docker):
        """Test listing only running containers."""
        mock_container1 = MagicMock()
        mock_container1.show = AsyncMock(return_value={
            "Id": "abc123" * 10,
            "Name": "/container1",
            "Config": {"Image": "nginx:latest"},
            "State": {"Status": "running"},
            "NetworkSettings": {"IPAddress": "172.17.0.2", "Ports": {}},
            "Created": "2024-01-01T00:00:00Z",
        })

        mock_docker.containers.list = AsyncMock(return_value=[mock_container1])

        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerListRequest(all=False)
            response = await docker_tools.list_containers(request)

        assert response.total_count == 1
        assert response.containers[0]["state"] == "running"
    
    @pytest.mark.asyncio
    async def test_list_with_name_filter(self, docker_tools, mock_docker):
        """Test listing containers with name filter."""
        mock_docker.containers.list = AsyncMock(return_value=[])
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerListRequest(filter_name="nginx")
            await docker_tools.list_containers(request)
        
        # Verify filter was passed
        mock_docker.containers.list.assert_called_once()
        call_kwargs = mock_docker.containers.list.call_args[1]
        assert call_kwargs["filters"]["name"] == ["nginx"]
    
    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, docker_tools, mock_docker):
        """Test listing containers with status filter."""
        mock_docker.containers.list = AsyncMock(return_value=[])
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerListRequest(filter_status="running")
            await docker_tools.list_containers(request)
        
        # Verify filter was passed
        call_kwargs = mock_docker.containers.list.call_args[1]
        assert call_kwargs["filters"]["status"] == ["running"]
    
    @pytest.mark.asyncio
    async def test_list_docker_error(self, docker_tools, mock_docker):
        """Test handling Docker errors."""
        mock_docker.containers.list = AsyncMock(side_effect=Exception("Docker daemon not running"))
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerListRequest()
            with pytest.raises(RuntimeError, match="Failed to list containers"):
                await docker_tools.list_containers(request)


class TestDockerInspect:
    """Tests for docker_inspect tool."""
    
    @pytest.mark.asyncio
    async def test_inspect_container(self, docker_tools, mock_docker, mock_container):
        """Test inspecting a container."""
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerInspectRequest(container="test-container")
            response = await docker_tools.inspect_container(request)
        
        assert response.name == "test-container"
        assert response.image == "nginx:latest"
        assert response.status == "running"
        assert response.state["running"] is True
        assert response.state["pid"] == 12345
        assert response.config["hostname"] == "test-host"
        assert "bridge" in response.network["networks"]
        assert response.network["ip_address"] == "172.17.0.2"
        assert len(response.mounts) == 1
        assert response.mounts[0]["source"] == "/host/path"
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not DOCKER_AVAILABLE, reason="aiodocker not installed")
    async def test_inspect_container_not_found(self, docker_tools, mock_docker):
        """Test inspecting non-existent container."""
        import aiodocker.exceptions
        
        error = aiodocker.exceptions.DockerError(
            status=404,
            message="No such container"
        )
        mock_docker.containers.get = AsyncMock(side_effect=error)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerInspectRequest(container="nonexistent")
            with pytest.raises(ValueError, match="Container not found"):
                await docker_tools.inspect_container(request)


class TestDockerLogs:
    """Tests for docker_logs tool."""
    
    @pytest.mark.asyncio
    async def test_get_logs(self, docker_tools, mock_docker, mock_container):
        """Test getting container logs."""
        mock_docker.containers.get = AsyncMock(return_value=mock_container)

        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerLogsRequest(container="test-container", tail=100)
            response = await docker_tools.get_logs(request)

        assert response.container == "test-container"
        assert "Log line 1" in response.logs
        assert "Log line 2" in response.logs
        assert response.line_count == 2

        # Verify log parameters (since is only included if provided)
        mock_container.log.assert_called_once_with(
            stdout=True,
            stderr=True,
            tail=100,
            follow=False,
        )
    
    @pytest.mark.asyncio
    async def test_get_logs_with_since(self, docker_tools, mock_docker, mock_container):
        """Test getting logs with since parameter."""
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerLogsRequest(
                container="test-container",
                tail=50,
                since="2024-01-01T00:00:00"
            )
            await docker_tools.get_logs(request)
        
        # Verify since parameter was passed
        call_kwargs = mock_container.log.call_args[1]
        assert call_kwargs["since"] == "2024-01-01T00:00:00"
        assert call_kwargs["tail"] == 50
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not DOCKER_AVAILABLE, reason="aiodocker not installed")
    async def test_get_logs_container_not_found(self, docker_tools, mock_docker):
        """Test getting logs from non-existent container."""
        import aiodocker.exceptions
        
        error = aiodocker.exceptions.DockerError(
            status=404,
            message="No such container"
        )
        mock_docker.containers.get = AsyncMock(side_effect=error)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerLogsRequest(container="nonexistent")
            with pytest.raises(ValueError, match="Container not found"):
                await docker_tools.get_logs(request)


class TestDockerAction:
    """Tests for docker_action tool."""
    
    @pytest.mark.asyncio
    async def test_start_container(self, docker_tools, mock_docker, mock_container):
        """Test starting a container."""
        # Mock container states
        mock_container.show = AsyncMock(side_effect=[
            {"State": {"Status": "exited"}},  # Before action
            {"State": {"Status": "running"}},  # After action
        ])
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="test-container", action="start")
            response = await docker_tools.container_action(request)
        
        assert response.success is True
        assert response.action == "start"
        assert response.previous_status == "exited"
        assert response.new_status == "running"
        mock_container.start.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stop_container(self, docker_tools, mock_docker, mock_container):
        """Test stopping a container."""
        mock_container.show = AsyncMock(side_effect=[
            {"State": {"Status": "running"}},
            {"State": {"Status": "exited"}},
        ])
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="test-container", action="stop", timeout=30)
            response = await docker_tools.container_action(request)
        
        assert response.success is True
        assert response.action == "stop"
        assert response.previous_status == "running"
        assert response.new_status == "exited"
        mock_container.stop.assert_called_once_with(timeout=30)
    
    @pytest.mark.asyncio
    async def test_restart_container(self, docker_tools, mock_docker, mock_container):
        """Test restarting a container."""
        mock_container.show = AsyncMock(side_effect=[
            {"State": {"Status": "running"}},
            {"State": {"Status": "running"}},
        ])
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="test-container", action="restart")
            response = await docker_tools.container_action(request)
        
        assert response.success is True
        assert response.action == "restart"
        mock_container.restart.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pause_container(self, docker_tools, mock_docker, mock_container):
        """Test pausing a container."""
        mock_container.show = AsyncMock(side_effect=[
            {"State": {"Status": "running"}},
            {"State": {"Status": "paused"}},
        ])
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="test-container", action="pause")
            response = await docker_tools.container_action(request)
        
        assert response.success is True
        assert response.action == "pause"
        assert response.new_status == "paused"
        mock_container.pause.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_unpause_container(self, docker_tools, mock_docker, mock_container):
        """Test unpausing a container."""
        mock_container.show = AsyncMock(side_effect=[
            {"State": {"Status": "paused"}},
            {"State": {"Status": "running"}},
        ])
        mock_docker.containers.get = AsyncMock(return_value=mock_container)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="test-container", action="unpause")
            response = await docker_tools.container_action(request)
        
        assert response.success is True
        assert response.action == "unpause"
        assert response.new_status == "running"
        mock_container.unpause.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_invalid_action(self, docker_tools, mock_docker):
        """Test invalid action."""
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="test-container", action="invalid")
            with pytest.raises(ValueError, match="Invalid action"):
                await docker_tools.container_action(request)
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not DOCKER_AVAILABLE, reason="aiodocker not installed")
    async def test_action_container_not_found(self, docker_tools, mock_docker):
        """Test action on non-existent container."""
        import aiodocker.exceptions
        
        error = aiodocker.exceptions.DockerError(
            status=404,
            message="No such container"
        )
        mock_docker.containers.get = AsyncMock(side_effect=error)
        
        with patch.object(docker_tools, '_get_docker', return_value=mock_docker):
            request = DockerActionRequest(container="nonexistent", action="start")
            with pytest.raises(ValueError, match="Container not found"):
                await docker_tools.container_action(request)


class TestDockerConnection:
    """Tests for Docker connection management."""
    
    @pytest.mark.asyncio
    async def test_docker_not_available(self):
        """Test when aiodocker is not installed."""
        with patch('anyide.modules.docker.tools.DOCKER_AVAILABLE', False):
            tools = DockerTools()
            with pytest.raises(RuntimeError, match="Docker support not available"):
                await tools._get_docker()
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not DOCKER_AVAILABLE, reason="aiodocker not installed")
    async def test_docker_connection_error(self, docker_tools):
        """Test Docker connection failure."""
        with patch('anyide.modules.docker.tools.aiodocker.Docker') as mock_docker_class:
            mock_instance = MagicMock()
            mock_instance.version = AsyncMock(side_effect=Exception("Connection refused"))
            mock_docker_class.return_value = mock_instance
            
            with pytest.raises(RuntimeError, match="Failed to connect to Docker daemon"):
                await docker_tools._get_docker()
    
    @pytest.mark.asyncio
    async def test_close_connection(self, docker_tools, mock_docker):
        """Test closing Docker connection."""
        docker_tools._docker = mock_docker
        await docker_tools.close()
        
        mock_docker.close.assert_called_once()
        assert docker_tools._docker is None
