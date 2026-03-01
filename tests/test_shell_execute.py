"""Tests for shell_execute tool."""

import os
import pytest
from anyide.modules.shell.tools import ShellTools
from anyide.core.workspace import WorkspaceManager, SecurityError
from anyide.models import ShellExecuteRequest


@pytest.fixture
def workspace_manager(tmp_path):
    """Create workspace manager with temp directory."""
    return WorkspaceManager(str(tmp_path))


@pytest.fixture
def shell_tools(workspace_manager):
    """Create shell tools instance."""
    return ShellTools(workspace_manager)


@pytest.mark.asyncio
async def test_execute_simple_command(shell_tools, tmp_path):
    """Test executing a simple command."""
    request = ShellExecuteRequest(command="echo hello")
    response = await shell_tools.execute(request)
    
    assert response.exit_code == 0
    assert "hello" in response.stdout
    assert response.stderr == ""
    assert response.duration_ms >= 0


@pytest.mark.asyncio
async def test_execute_with_working_directory(shell_tools, tmp_path):
    """Test executing command in specific directory."""
    # Create a subdirectory
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    
    request = ShellExecuteRequest(
        command="pwd",
        workspace_dir=str(subdir)
    )
    response = await shell_tools.execute(request)
    
    assert response.exit_code == 0
    assert "subdir" in response.stdout
    assert response.working_directory == str(subdir)


@pytest.mark.asyncio
async def test_execute_with_env_vars(shell_tools, tmp_path):
    """Test executing command with environment variables."""
    # Use sh -c to properly expand variables
    request = ShellExecuteRequest(
        command="sh -c 'echo $TEST_VAR'",
        env={"TEST_VAR": "test_value"}
    )
    response = await shell_tools.execute(request)
    
    assert response.exit_code == 0
    assert "test_value" in response.stdout


@pytest.mark.asyncio
async def test_execute_command_with_args(shell_tools, tmp_path):
    """Test executing command with arguments."""
    # Create a test file
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")
    
    request = ShellExecuteRequest(command=f"cat {test_file}")
    response = await shell_tools.execute(request)
    
    assert response.exit_code == 0
    assert "test content" in response.stdout


@pytest.mark.asyncio
async def test_execute_command_with_stderr(shell_tools, tmp_path):
    """Test command that produces stderr output."""
    request = ShellExecuteRequest(command="ls /nonexistent 2>&1 || echo error")
    response = await shell_tools.execute(request)
    
    # Command should complete (with error or echo)
    assert response.exit_code >= 0


@pytest.mark.asyncio
async def test_execute_command_timeout(shell_tools, tmp_path):
    """Test command timeout."""
    request = ShellExecuteRequest(
        command="sleep 10",
        timeout=1
    )
    
    with pytest.raises(TimeoutError, match="timed out"):
        await shell_tools.execute(request)


@pytest.mark.asyncio
async def test_execute_nonexistent_command(shell_tools, tmp_path):
    """Test executing nonexistent command."""
    request = ShellExecuteRequest(command="nonexistent_command_xyz")
    
    with pytest.raises(ValueError, match="Command not found"):
        await shell_tools.execute(request)


@pytest.mark.asyncio
async def test_execute_empty_command(shell_tools, tmp_path):
    """Test executing empty command."""
    request = ShellExecuteRequest(command="")
    
    with pytest.raises(ValueError, match="cannot be empty"):
        await shell_tools.execute(request)


@pytest.mark.asyncio
async def test_execute_invalid_working_directory(shell_tools, tmp_path):
    """Test executing with invalid working directory."""
    request = ShellExecuteRequest(
        command="echo test",
        workspace_dir=str(tmp_path / "nonexistent")
    )
    
    with pytest.raises((ValueError, SecurityError)):
        await shell_tools.execute(request)


@pytest.mark.asyncio
async def test_parse_command(shell_tools):
    """Test command parsing."""
    base, args = shell_tools._parse_command("ls -la /tmp")
    
    assert base == "ls"
    assert args == ["-la", "/tmp"]


@pytest.mark.asyncio
async def test_parse_command_with_quotes(shell_tools):
    """Test parsing command with quoted arguments."""
    base, args = shell_tools._parse_command('echo "hello world"')
    
    assert base == "echo"
    assert args == ["hello world"]


@pytest.mark.asyncio
async def test_check_command_safety_safe(shell_tools):
    """Test safety check for safe commands."""
    is_safe, reason = shell_tools._check_command_safety("ls -la")
    assert is_safe is True


@pytest.mark.asyncio
async def test_check_command_safety_dangerous_metachar(shell_tools):
    """Test safety check for dangerous metacharacters."""
    is_safe, reason = shell_tools._check_command_safety("ls; rm -rf /")
    assert is_safe is False
    assert "metacharacter" in reason.lower()


@pytest.mark.asyncio
async def test_check_command_safety_pipe(shell_tools):
    """Test safety check for pipe character."""
    is_safe, reason = shell_tools._check_command_safety("cat file | grep test")
    assert is_safe is False
    assert "metacharacter" in reason.lower()


@pytest.mark.asyncio
async def test_check_command_safety_redirect(shell_tools):
    """Test safety check for redirection."""
    is_safe, reason = shell_tools._check_command_safety("echo test > file.txt")
    assert is_safe is False
    assert "metacharacter" in reason.lower()


@pytest.mark.asyncio
async def test_check_command_safety_not_in_allowlist(shell_tools):
    """Test safety check for command not in allowlist."""
    is_safe, reason = shell_tools._check_command_safety("dangerous_command")
    assert is_safe is False
    assert "not in allowlist" in reason.lower()


@pytest.mark.asyncio
async def test_check_command_safety_allowlisted_commands(shell_tools):
    """Test that common commands are in allowlist."""
    safe_commands = [
        "ls -la",
        "cat file.txt",
        "echo hello",
        "pwd",
        "git status",
        "python script.py",
        "npm install",
        "docker ps",
    ]
    
    for cmd in safe_commands:
        is_safe, reason = shell_tools._check_command_safety(cmd)
        assert is_safe is True, f"Command '{cmd}' should be safe but got: {reason}"


@pytest.mark.asyncio
async def test_output_truncation(shell_tools, tmp_path):
    """Test that large outputs are truncated."""
    # Create a command that produces large output
    large_content = "x" * 150000  # 150KB
    test_file = tmp_path / "large.txt"
    test_file.write_text(large_content)
    
    request = ShellExecuteRequest(command=f"cat {test_file}")
    response = await shell_tools.execute(request)
    
    # Output should be truncated
    assert len(response.stdout) < 150000
    assert "truncated" in response.stdout.lower()


@pytest.mark.asyncio
async def test_execute_returns_command(shell_tools, tmp_path):
    """Test that response includes the executed command."""
    request = ShellExecuteRequest(command="echo test")
    response = await shell_tools.execute(request)
    
    assert response.command == "echo test"


@pytest.mark.asyncio
async def test_execute_duration_tracking(shell_tools, tmp_path):
    """Test that execution duration is tracked."""
    request = ShellExecuteRequest(command="echo test")
    response = await shell_tools.execute(request)
    
    assert response.duration_ms >= 0
    assert isinstance(response.duration_ms, int)
