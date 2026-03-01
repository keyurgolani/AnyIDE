"""Docker container management tools."""

import asyncio
from typing import Optional
from datetime import datetime

try:
    import aiodocker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False

from anyide.models import (
    DockerListRequest,
    DockerListResponse,
    DockerInspectRequest,
    DockerInspectResponse,
    DockerLogsRequest,
    DockerLogsResponse,
    DockerActionRequest,
    DockerActionResponse,
)
from anyide.logging_config import get_logger

logger = get_logger(__name__)


class DockerTools:
    """Docker container management tools."""
    
    def __init__(self):
        """Initialize Docker tools."""
        if not DOCKER_AVAILABLE:
            logger.warning("aiodocker_not_available", message="Docker tools will not be functional")
        self._docker = None
    
    async def _get_docker(self):
        """Get or create Docker client.
        
        Returns:
            Docker client instance
            
        Raises:
            RuntimeError: If Docker is not available
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError(
                "Docker support not available. Install aiodocker: pip install aiodocker"
            )
        
        if self._docker is None:
            try:
                self._docker = aiodocker.Docker()
                # Test connection
                await self._docker.version()
            except Exception as e:
                raise RuntimeError(
                    f"Failed to connect to Docker daemon. "
                    f"Ensure Docker socket is mounted and accessible: {str(e)}"
                )
        
        return self._docker
    
    async def close(self):
        """Close Docker client connection."""
        if self._docker:
            await self._docker.close()
            self._docker = None
    
    def _format_container_info(self, container_data: dict) -> dict:
        """Format container information for response.
        
        Args:
            container_data: Raw container data from Docker API (from show())
            
        Returns:
            Formatted container info
        """
        # Extract basic info
        container_id = container_data.get("Id", "")[:12]  # Short ID
        name = container_data.get("Name", "").lstrip("/")
        
        # Get image from Config
        config = container_data.get("Config", {})
        image = config.get("Image", "unknown")
        
        # Get state
        state_info = container_data.get("State", {})
        state = state_info.get("Status", "unknown")
        
        # Build status string
        if state == "running":
            started_at = state_info.get("StartedAt", "")
            status = f"Up (started {started_at})"
        elif state == "exited":
            exit_code = state_info.get("ExitCode", 0)
            finished_at = state_info.get("FinishedAt", "")
            status = f"Exited ({exit_code}) at {finished_at}"
        else:
            status = state
        
        # Format ports
        network_settings = container_data.get("NetworkSettings", {})
        ports_data = network_settings.get("Ports", {})
        ports = []
        for container_port, host_bindings in ports_data.items():
            if host_bindings:
                for binding in host_bindings:
                    host_ip = binding.get("HostIp", "0.0.0.0")
                    host_port = binding.get("HostPort", "")
                    ports.append(f"{host_ip}:{host_port}->{container_port}")
            else:
                ports.append(container_port)
        
        # Format creation time
        created = container_data.get("Created", "")
        
        return {
            "id": container_id,
            "name": name,
            "image": image,
            "status": status,
            "state": state,
            "ports": ports,
            "created": created,
        }
    
    async def list_containers(self, request: DockerListRequest) -> DockerListResponse:
        """List Docker containers.
        
        Args:
            request: List request
            
        Returns:
            List of containers
            
        Raises:
            RuntimeError: If Docker is not available or connection fails
        """
        docker = await self._get_docker()
        
        # Build filters
        filters = {}
        if request.filter_status:
            filters["status"] = [request.filter_status]
        if request.filter_name:
            filters["name"] = [request.filter_name]
        
        try:
            # List containers
            containers_list = await docker.containers.list(
                all=request.all,
                filters=filters if filters else None,
            )
            
            # Get container info for each container
            containers = []
            for container in containers_list:
                info = await container.show()
                containers.append(self._format_container_info(info))
            
            logger.info(
                "docker_list_executed",
                count=len(containers),
                all=request.all,
                filters=filters,
            )
            
            return DockerListResponse(
                containers=containers,
                total_count=len(containers),
            )
        
        except Exception as e:
            logger.error("docker_list_error", error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to list containers: {str(e)}")
    
    async def inspect_container(self, request: DockerInspectRequest) -> DockerInspectResponse:
        """Inspect a Docker container.
        
        Args:
            request: Inspect request
            
        Returns:
            Container details
            
        Raises:
            RuntimeError: If Docker is not available or connection fails
            ValueError: If container not found
        """
        docker = await self._get_docker()
        
        try:
            # Get container
            container = await docker.containers.get(request.container)
            
            # Get detailed info
            info = await container.show()
            
            # Extract relevant information
            container_id = info["Id"][:12]
            name = info["Name"].lstrip("/")
            image = info["Config"]["Image"]
            status = info["State"]["Status"]
            
            # Format response
            response = DockerInspectResponse(
                id=container_id,
                name=name,
                image=image,
                status=status,
                config={
                    "hostname": info["Config"].get("Hostname", ""),
                    "user": info["Config"].get("User", ""),
                    "env": info["Config"].get("Env", []),
                    "cmd": info["Config"].get("Cmd", []),
                    "entrypoint": info["Config"].get("Entrypoint", []),
                    "working_dir": info["Config"].get("WorkingDir", ""),
                    "labels": info["Config"].get("Labels", {}),
                },
                network={
                    "networks": list(info.get("NetworkSettings", {}).get("Networks", {}).keys()),
                    "ip_address": info.get("NetworkSettings", {}).get("IPAddress", ""),
                    "gateway": info.get("NetworkSettings", {}).get("Gateway", ""),
                    "ports": info.get("NetworkSettings", {}).get("Ports", {}),
                },
                mounts=[
                    {
                        "type": m.get("Type", ""),
                        "source": m.get("Source", ""),
                        "destination": m.get("Destination", ""),
                        "mode": m.get("Mode", ""),
                        "rw": m.get("RW", False),
                    }
                    for m in info.get("Mounts", [])
                ],
                ports=info.get("NetworkSettings", {}).get("Ports", {}),
                created=info.get("Created", ""),
                state={
                    "status": info["State"].get("Status", ""),
                    "running": info["State"].get("Running", False),
                    "paused": info["State"].get("Paused", False),
                    "restarting": info["State"].get("Restarting", False),
                    "pid": info["State"].get("Pid", 0),
                    "exit_code": info["State"].get("ExitCode", 0),
                    "started_at": info["State"].get("StartedAt", ""),
                    "finished_at": info["State"].get("FinishedAt", ""),
                },
            )
            
            logger.info("docker_inspect_executed", container=request.container)
            
            return response
        
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                raise ValueError(f"Container not found: {request.container}")
            logger.error("docker_inspect_error", container=request.container, error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to inspect container: {str(e)}")
        except Exception as e:
            logger.error("docker_inspect_error", container=request.container, error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to inspect container: {str(e)}")
    
    async def get_logs(self, request: DockerLogsRequest) -> DockerLogsResponse:
        """Get Docker container logs.
        
        Args:
            request: Logs request
            
        Returns:
            Container logs
            
        Raises:
            RuntimeError: If Docker is not available or connection fails
            ValueError: If container not found
        """
        docker = await self._get_docker()
        
        try:
            # Get container
            container = await docker.containers.get(request.container)
            
            # Build log parameters
            log_params = {
                "stdout": True,
                "stderr": True,
                "tail": request.tail,
                "follow": False,  # Never follow in API calls
            }
            
            # Only add since if it's provided
            if request.since:
                log_params["since"] = request.since
            
            # Get logs
            logs_bytes = await container.log(**log_params)
            
            # Decode logs
            logs = "".join(logs_bytes).strip()
            
            # Count lines
            line_count = len(logs.split("\n")) if logs else 0
            
            logger.info(
                "docker_logs_executed",
                container=request.container,
                lines=line_count,
            )
            
            return DockerLogsResponse(
                logs=logs,
                container=request.container,
                line_count=line_count,
            )
        
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                raise ValueError(f"Container not found: {request.container}")
            logger.error("docker_logs_error", container=request.container, error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to get container logs: {str(e)}")
        except Exception as e:
            logger.error("docker_logs_error", container=request.container, error=str(e), exc_info=True)
            raise RuntimeError(f"Failed to get container logs: {str(e)}")
    
    async def container_action(self, request: DockerActionRequest) -> DockerActionResponse:
        """Perform an action on a Docker container.
        
        Args:
            request: Action request
            
        Returns:
            Action result
            
        Raises:
            RuntimeError: If Docker is not available or connection fails
            ValueError: If container not found or action invalid
        """
        docker = await self._get_docker()
        
        # Validate action
        valid_actions = ["start", "stop", "restart", "pause", "unpause"]
        if request.action not in valid_actions:
            raise ValueError(
                f"Invalid action: {request.action}. "
                f"Valid actions: {', '.join(valid_actions)}"
            )
        
        try:
            # Get container
            container = await docker.containers.get(request.container)
            
            # Get current status
            info = await container.show()
            previous_status = info["State"]["Status"]
            
            # Perform action
            if request.action == "start":
                await container.start()
            elif request.action == "stop":
                await container.stop(timeout=request.timeout)
            elif request.action == "restart":
                await container.restart(timeout=request.timeout)
            elif request.action == "pause":
                await container.pause()
            elif request.action == "unpause":
                await container.unpause()
            
            # Wait a moment for status to update
            await asyncio.sleep(0.5)
            
            # Get new status
            info = await container.show()
            new_status = info["State"]["Status"]
            
            logger.info(
                "docker_action_executed",
                container=request.container,
                action=request.action,
                previous_status=previous_status,
                new_status=new_status,
            )
            
            return DockerActionResponse(
                container=request.container,
                action=request.action,
                success=True,
                previous_status=previous_status,
                new_status=new_status,
                message=f"Successfully {request.action}ed container {request.container}",
            )
        
        except aiodocker.exceptions.DockerError as e:
            if e.status == 404:
                raise ValueError(f"Container not found: {request.container}")
            logger.error(
                "docker_action_error",
                container=request.container,
                action=request.action,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to {request.action} container: {str(e)}")
        except Exception as e:
            logger.error(
                "docker_action_error",
                container=request.container,
                action=request.action,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to {request.action} container: {str(e)}")
