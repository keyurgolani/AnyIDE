"""Docker tools module."""

from __future__ import annotations

from fastapi import FastAPI

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
from anyide.modules.base import ToolModule
from anyide.modules.docker.tools import DockerTools


_LIST_DESC = """List Docker containers on the host system.

This tool allows you to view all containers (running and stopped) managed by Docker.
You can filter by container name or status.

Use this tool when you need to:
- See what containers are running
- Check container status
- Find a specific container by name
- Monitor container health

The tool returns container ID, name, image, status, ports, and creation time.

Examples:
- List all containers: {"all": true}
- List only running containers: {"all": false}
- Filter by name: {"filter_name": "nginx"}
- Filter by status: {"filter_status": "running"}"""

_INSPECT_DESC = """Get detailed information about a specific Docker container.

This tool provides comprehensive details about a container including:
- Configuration (environment variables, command, entrypoint, labels)
- Network settings (IP address, ports, networks)
- Volume mounts
- Container state (running, paused, exit code, etc.)

Use this tool when you need to:
- Debug container configuration issues
- Check environment variables
- View port mappings
- Inspect volume mounts
- Get detailed container state

Provide either the container name or ID.

Example: {"container": "nginx"} or {"container": "a1b2c3d4"}"""

_LOGS_DESC = """Retrieve logs from a Docker container.

This tool fetches stdout and stderr output from a container. You can control:
- Number of lines to retrieve (tail)
- Time range (since timestamp)

Use this tool when you need to:
- Debug application issues
- Monitor container output
- Check error messages
- Investigate crashes

The logs are returned as a single string with newlines preserved.

Examples:
- Get last 100 lines: {"container": "nginx", "tail": 100}
- Get last 50 lines: {"container": "nginx", "tail": 50}
- Get logs since timestamp: {"container": "nginx", "since": "2024-01-01T00:00:00"}

Note: The 'follow' parameter is not recommended for API calls and defaults to false."""

_ACTION_DESC = """Perform control actions on a Docker container.

This tool allows you to manage container lifecycle. Available actions:
- start: Start a stopped container
- stop: Stop a running container (graceful shutdown)
- restart: Restart a container (stop + start)
- pause: Pause a running container (freeze processes)
- unpause: Resume a paused container

Use this tool when you need to:
- Start/stop services
- Restart containers after configuration changes
- Pause containers to save resources
- Recover from container issues

IMPORTANT: This tool requires human approval (HITL) by default for safety.
Container control actions can affect running services.

The tool returns the previous and new status of the container.

Examples:
- Start container: {"container": "nginx", "action": "start"}
- Stop container: {"container": "nginx", "action": "stop", "timeout": 30}
- Restart container: {"container": "nginx", "action": "restart"}
- Pause container: {"container": "nginx", "action": "pause"}"""


class _DockerDispatch:
    """Plan-dispatch wrapper exposing tool-name-aligned methods."""

    def __init__(self, module: "DockerModule"):
        self._module = module

    async def list(self, request: DockerListRequest) -> DockerListResponse:
        return await self._module.docker_tools.list_containers(request)

    async def inspect(self, request: DockerInspectRequest) -> DockerInspectResponse:
        return await self._module.docker_tools.inspect_container(request)

    async def logs(self, request: DockerLogsRequest) -> DockerLogsResponse:
        return await self._module.docker_tools.get_logs(request)

    async def action(self, request: DockerActionRequest) -> DockerActionResponse:
        return await self._module.docker_tools.container_action(request)


class DockerModule(ToolModule):
    MODULE_NAME = "docker"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Docker Tools"

    @property
    def description(self) -> str:
        return "Docker container management for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.docker_tools = DockerTools()
        self._dispatch = _DockerDispatch(self)
        self.context.register_dispatch_target("docker", self._dispatch)

    async def on_shutdown(self) -> None:
        await self.docker_tools.close()

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/docker/list",
            operation_id="docker_list",
            summary="List Docker Containers",
            description=_LIST_DESC,
            tags=["docker"],
            response_model=DockerListResponse,
        )
        async def docker_list_root(request: DockerListRequest) -> DockerListResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="list",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.list_containers(request),
                protocol="openapi",
            )

        @sub_app.post(
            "/list",
            operation_id="docker_list_sub",
            summary="List Docker Containers",
            description=_LIST_DESC,
            response_model=DockerListResponse,
            tags=["docker"],
        )
        async def docker_list_sub(request: DockerListRequest) -> DockerListResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="list",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.list_containers(request),
                protocol="openapi",
            )

        @app.post(
            "/api/tools/docker/inspect",
            operation_id="docker_inspect",
            summary="Inspect Docker Container",
            description=_INSPECT_DESC,
            tags=["docker"],
            response_model=DockerInspectResponse,
        )
        async def docker_inspect_root(request: DockerInspectRequest) -> DockerInspectResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="inspect",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.inspect_container(request),
                protocol="openapi",
            )

        @sub_app.post(
            "/inspect",
            operation_id="docker_inspect_sub",
            summary="Inspect Docker Container",
            description=_INSPECT_DESC,
            response_model=DockerInspectResponse,
            tags=["docker"],
        )
        async def docker_inspect_sub(request: DockerInspectRequest) -> DockerInspectResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="inspect",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.inspect_container(request),
                protocol="openapi",
            )

        @app.post(
            "/api/tools/docker/logs",
            operation_id="docker_logs",
            summary="Get Docker Container Logs",
            description=_LOGS_DESC,
            tags=["docker"],
            response_model=DockerLogsResponse,
        )
        async def docker_logs_root(request: DockerLogsRequest) -> DockerLogsResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="logs",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.get_logs(request),
                protocol="openapi",
            )

        @sub_app.post(
            "/logs",
            operation_id="docker_logs_sub",
            summary="Get Docker Container Logs",
            description=_LOGS_DESC,
            response_model=DockerLogsResponse,
            tags=["docker"],
        )
        async def docker_logs_sub(request: DockerLogsRequest) -> DockerLogsResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="logs",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.get_logs(request),
                protocol="openapi",
            )

        @app.post(
            "/api/tools/docker/action",
            operation_id="docker_action",
            summary="Control Docker Container",
            description=_ACTION_DESC,
            tags=["docker"],
            response_model=DockerActionResponse,
        )
        async def docker_action_root(request: DockerActionRequest) -> DockerActionResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="action",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.container_action(request),
                protocol="openapi",
                force_hitl=True,
                hitl_reason=(
                    f"Container action '{request.action}' on '{request.container}' requires approval"
                ),
            )

        @sub_app.post(
            "/action",
            operation_id="docker_action_sub",
            summary="Control Docker Container",
            description="""Perform control actions on a Docker container.

Available actions: start, stop, restart, pause, unpause.

IMPORTANT: This tool requires human approval (HITL) by default for safety.""",
            response_model=DockerActionResponse,
            tags=["docker"],
        )
        async def docker_action_sub(request: DockerActionRequest) -> DockerActionResponse:
            return await self.context.execute_tool(
                tool_category="docker",
                tool_name="action",
                params=request.model_dump(),
                tool_func=lambda: self.docker_tools.container_action(request),
                protocol="openapi",
                force_hitl=True,
                hitl_reason=(
                    f"Container action '{request.action}' on '{request.container}' requires approval"
                ),
            )
