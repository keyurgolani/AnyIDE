"""Shell command execution tools."""

import os
import asyncio
import shlex
import time
from typing import Optional

from anyide.models import ShellExecuteRequest, ShellExecuteResponse
from anyide.core.workspace import WorkspaceManager, SecurityError
from anyide.logging_config import get_logger

logger = get_logger(__name__)


# Command allowlist - these commands can be executed without HITL if no dangerous flags
ALLOWED_COMMANDS = {
    "ls", "cat", "echo", "pwd", "whoami", "date", "which", "head", "tail",
    "grep", "find", "wc", "sort", "uniq", "diff", "tree", "file", "stat",
    "git", "python", "python3", "node", "npm", "pip", "pip3", "docker",
    "curl", "wget", "jq", "sed", "awk", "cut", "tr", "basename", "dirname",
}

# Dangerous shell metacharacters that require HITL
DANGEROUS_METACHARACTERS = {
    ';', '|', '&', '>', '<', '`', '$', '(', ')', '{', '}', '[', ']',
    '*', '?', '~', '!', '^', '\n', '\r',
}


class ShellTools:
    """Shell command execution tools."""
    
    def __init__(self, workspace: WorkspaceManager):
        """Initialize shell tools.
        
        Args:
            workspace: Workspace manager instance
        """
        self.workspace = workspace
    
    def _parse_command(self, command: str) -> tuple[str, list[str]]:
        """Parse command into base command and arguments.
        
        Args:
            command: Shell command string
            
        Returns:
            Tuple of (base_command, args_list)
            
        Raises:
            ValueError: If command is invalid
        """
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")
        
        # Parse command using shlex
        try:
            parts = shlex.split(command)
        except ValueError as e:
            raise ValueError(f"Invalid command syntax: {str(e)}")
        
        if not parts:
            raise ValueError("Command cannot be empty")
        
        base_command = parts[0]
        args = parts[1:] if len(parts) > 1 else []
        
        return base_command, args
    
    def _check_command_safety(self, command: str) -> tuple[bool, str]:
        """Check if command is safe to execute without HITL.
        
        Args:
            command: Shell command string
            
        Returns:
            Tuple of (is_safe, reason)
        """
        # Check for dangerous metacharacters
        for char in DANGEROUS_METACHARACTERS:
            if char in command:
                return False, f"Contains dangerous metacharacter: '{char}'"
        
        # Parse command
        try:
            base_command, args = self._parse_command(command)
        except ValueError as e:
            return False, str(e)
        
        # Check if base command is in allowlist
        if base_command not in ALLOWED_COMMANDS:
            return False, f"Command '{base_command}' not in allowlist"
        
        # Additional checks for specific commands
        if base_command == "rm":
            if "-rf" in command or "-fr" in command:
                return False, "Recursive force delete requires approval"
        
        if base_command in ("curl", "wget"):
            # Check for dangerous flags
            dangerous_flags = ["-o", "--output", "-O", ">"]
            for flag in dangerous_flags:
                if flag in args:
                    return False, f"Output redirection with {flag} requires approval"
        
        return True, "Command is safe"
    
    async def execute(self, request: ShellExecuteRequest) -> ShellExecuteResponse:
        """Execute a shell command.
        
        Args:
            request: Execute request
            
        Returns:
            Command execution result
            
        Raises:
            SecurityError: If command is blocked
            ValueError: If parameters are invalid
            TimeoutError: If command times out
        """
        start_time = time.time()
        
        # Determine working directory
        if request.workspace_dir:
            working_dir = self.workspace.resolve_path(".", request.workspace_dir)
        else:
            working_dir = self.workspace.base_dir
        
        # Validate working directory exists
        if not os.path.exists(working_dir):
            raise ValueError(f"Working directory does not exist: {working_dir}")
        
        if not os.path.isdir(working_dir):
            raise ValueError(f"Working directory is not a directory: {working_dir}")
        
        # Parse command
        base_command, args = self._parse_command(request.command)
        
        # Prepare environment
        env = os.environ.copy()
        if request.env:
            env.update(request.env)
        
        # Execute command
        try:
            process = await asyncio.create_subprocess_exec(
                base_command,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                env=env,
            )
            
            # Wait for completion with timeout
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=request.timeout,
                )
            except asyncio.TimeoutError:
                # Kill the process
                process.kill()
                await process.wait()
                raise TimeoutError(
                    f"Command timed out after {request.timeout} seconds. "
                    f"Consider increasing the timeout parameter."
                )
            
            # Decode output
            stdout = stdout_bytes.decode('utf-8', errors='replace')
            stderr = stderr_bytes.decode('utf-8', errors='replace')
            exit_code = process.returncode
            
            # Truncate large outputs
            max_output_size = 100000  # 100KB
            if len(stdout) > max_output_size:
                stdout = stdout[:max_output_size] + f"\n\n[Output truncated: {len(stdout)} bytes total]"
            if len(stderr) > max_output_size:
                stderr = stderr[:max_output_size] + f"\n\n[Output truncated: {len(stderr)} bytes total]"
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                "shell_executed",
                command=request.command,
                exit_code=exit_code,
                duration_ms=duration_ms,
                working_dir=working_dir,
            )
            
            return ShellExecuteResponse(
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration_ms,
                command=request.command,
                working_directory=working_dir,
            )
        
        except TimeoutError:
            # Re-raise TimeoutError without wrapping
            raise
        except FileNotFoundError:
            raise ValueError(
                f"Command not found: '{base_command}'. "
                f"Make sure the command is installed and available in PATH."
            )
        except PermissionError:
            raise SecurityError(
                f"Permission denied executing command: '{base_command}'"
            )
        except Exception as e:
            logger.error("shell_execution_error", command=request.command, error=str(e), exc_info=True)
            raise ValueError(f"Failed to execute command: {str(e)}")
