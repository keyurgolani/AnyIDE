"""Shell tools module."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.models import ShellExecuteRequest, ShellExecuteResponse
from anyide.modules.base import ToolModule
from anyide.core.workspace import SecurityError
from anyide.modules.shell.tools import ShellTools


_EXECUTE_DESC = """Execute a shell command in the workspace.

Use this tool when you need to:
- Run system commands
- Execute build scripts
- Run tests
- Interact with CLI tools
- Perform system operations

Required: command
Optional: workspace_dir, timeout (default: 60s), env (environment variables)

Security notes:
- Commands with dangerous metacharacters (;, |, &, >, <, etc.) require approval
- Commands not in the allowlist require approval
- Use {{secret:KEY}} syntax in env values for sensitive data
- Output is truncated at 100KB

Allowlisted commands: ls, cat, echo, pwd, git, python, node, npm, docker, curl, and more."""


class ShellModule(ToolModule):
    MODULE_NAME = "shell"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Shell Tools"

    @property
    def description(self) -> str:
        return "Shell command execution for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.shell_tools = ShellTools(context.workspace_manager)
        self.context.register_dispatch_target("shell", self.shell_tools)

    async def _execute(self, request: ShellExecuteRequest) -> ShellExecuteResponse:
        is_safe, reason = self.shell_tools._check_command_safety(request.command)

        decision, policy_reason = self.context.policy_engine.evaluate_shell_command(
            request.command,
            is_safe,
            reason,
        )

        if decision == "block":
            raise SecurityError(policy_reason or "Command execution blocked by policy")

        resolved = self.context.resolve_request_secrets(request)

        if decision == "hitl":
            return await self.context.execute_tool(
                "shell",
                "execute",
                request.model_dump(),
                lambda: self.shell_tools.execute(resolved),
                force_hitl=True,
                hitl_reason=policy_reason or reason,
            )

        return await self.context.execute_tool(
            "shell",
            "execute",
            request.model_dump(),
            lambda: self.shell_tools.execute(resolved),
        )

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/shell/execute",
            operation_id="shell_execute",
            summary="Execute Shell Command",
            description=_EXECUTE_DESC,
            response_model=ShellExecuteResponse,
            tags=["shell"],
        )
        async def shell_execute_root(request: ShellExecuteRequest) -> ShellExecuteResponse:
            return await self._execute(request)

        @sub_app.post(
            "/execute",
            operation_id="shell_execute",
            summary="Execute Shell Command",
            description=_EXECUTE_DESC,
            response_model=ShellExecuteResponse,
            tags=["shell"],
        )
        async def shell_execute_sub(request: ShellExecuteRequest) -> ShellExecuteResponse:
            return await self._execute(request)
