"""Tests for fs_write tool."""

import pytest
import os
import tempfile
import shutil

from anyide.core.workspace import WorkspaceManager, SecurityError
from anyide.modules.fs.tools import FilesystemTools
from anyide.models import FsWriteRequest


@pytest.fixture
def workspace_dir():
    """Create temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def workspace_manager(workspace_dir):
    """Create workspace manager."""
    return WorkspaceManager(workspace_dir)


@pytest.fixture
def fs_tools(workspace_manager):
    """Create filesystem tools."""
    return FilesystemTools(workspace_manager)


@pytest.mark.asyncio
async def test_write_new_file(fs_tools, workspace_dir):
    """Test writing a new file."""
    request = FsWriteRequest(
        path="test.txt",
        content="Hello, World!",
        mode="create",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    assert response.bytes_written == len("Hello, World!")
    assert response.mode == "create"
    assert os.path.exists(os.path.join(workspace_dir, "test.txt"))
    
    # Verify content
    with open(os.path.join(workspace_dir, "test.txt"), "r") as f:
        assert f.read() == "Hello, World!"


@pytest.mark.asyncio
async def test_write_create_mode_existing_file(fs_tools, workspace_dir):
    """Test that create mode fails if file exists."""
    # Create file first
    test_file = os.path.join(workspace_dir, "existing.txt")
    with open(test_file, "w") as f:
        f.write("existing content")
    
    request = FsWriteRequest(
        path="existing.txt",
        content="new content",
        mode="create",
    )
    
    with pytest.raises(ValueError, match="already exists"):
        await fs_tools.write(request)


@pytest.mark.asyncio
async def test_write_overwrite_mode(fs_tools, workspace_dir):
    """Test overwriting an existing file."""
    # Create file first
    test_file = os.path.join(workspace_dir, "existing.txt")
    with open(test_file, "w") as f:
        f.write("old content")
    
    request = FsWriteRequest(
        path="existing.txt",
        content="new content",
        mode="overwrite",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is False
    assert response.mode == "overwrite"
    
    # Verify content was replaced
    with open(test_file, "r") as f:
        assert f.read() == "new content"


@pytest.mark.asyncio
async def test_write_append_mode(fs_tools, workspace_dir):
    """Test appending to an existing file."""
    # Create file first
    test_file = os.path.join(workspace_dir, "existing.txt")
    with open(test_file, "w") as f:
        f.write("line 1\n")
    
    request = FsWriteRequest(
        path="existing.txt",
        content="line 2\n",
        mode="append",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is False
    assert response.mode == "append"
    
    # Verify content was appended
    with open(test_file, "r") as f:
        content = f.read()
        assert content == "line 1\nline 2\n"


@pytest.mark.asyncio
async def test_write_create_directories(fs_tools, workspace_dir):
    """Test creating parent directories."""
    request = FsWriteRequest(
        path="subdir/nested/test.txt",
        content="nested content",
        mode="create",
        create_dirs=True,
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    assert os.path.exists(os.path.join(workspace_dir, "subdir", "nested", "test.txt"))
    
    # Verify content
    with open(os.path.join(workspace_dir, "subdir", "nested", "test.txt"), "r") as f:
        assert f.read() == "nested content"


@pytest.mark.asyncio
async def test_write_no_create_directories(fs_tools, workspace_dir):
    """Test that writing fails if parent directories don't exist and create_dirs=False."""
    request = FsWriteRequest(
        path="nonexistent/test.txt",
        content="content",
        mode="create",
        create_dirs=False,
    )
    
    with pytest.raises(ValueError, match="Failed to write file"):
        await fs_tools.write(request)


@pytest.mark.asyncio
async def test_write_invalid_mode(fs_tools):
    """Test that invalid mode raises error."""
    request = FsWriteRequest(
        path="test.txt",
        content="content",
        mode="invalid",
    )
    
    with pytest.raises(ValueError, match="Invalid mode"):
        await fs_tools.write(request)


@pytest.mark.asyncio
async def test_write_path_escape(fs_tools, workspace_dir):
    """Test that path traversal is prevented."""
    request = FsWriteRequest(
        path="../outside.txt",
        content="malicious content",
        mode="create",
    )
    
    with pytest.raises(SecurityError, match="escapes workspace"):
        await fs_tools.write(request)


@pytest.mark.asyncio
async def test_write_absolute_path_within_workspace(fs_tools, workspace_dir):
    """Test writing with absolute path within workspace."""
    abs_path = os.path.join(workspace_dir, "absolute.txt")
    
    request = FsWriteRequest(
        path=abs_path,
        content="absolute path content",
        mode="create",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    assert os.path.exists(abs_path)


@pytest.mark.asyncio
async def test_write_absolute_path_outside_workspace(fs_tools, workspace_dir):
    """Test that absolute path outside workspace is blocked."""
    outside_path = "/tmp/outside.txt"
    
    request = FsWriteRequest(
        path=outside_path,
        content="malicious content",
        mode="create",
    )
    
    with pytest.raises(SecurityError, match="escapes workspace"):
        await fs_tools.write(request)


@pytest.mark.asyncio
async def test_write_with_encoding(fs_tools, workspace_dir):
    """Test writing with different encoding."""
    request = FsWriteRequest(
        path="utf16.txt",
        content="Hello, 世界!",
        mode="create",
        encoding="utf-16",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    
    # Verify content with correct encoding
    with open(os.path.join(workspace_dir, "utf16.txt"), "r", encoding="utf-16") as f:
        assert f.read() == "Hello, 世界!"


@pytest.mark.asyncio
async def test_write_empty_content(fs_tools, workspace_dir):
    """Test writing empty content."""
    request = FsWriteRequest(
        path="empty.txt",
        content="",
        mode="create",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    assert response.bytes_written == 0
    assert os.path.exists(os.path.join(workspace_dir, "empty.txt"))
    
    # Verify file is empty
    with open(os.path.join(workspace_dir, "empty.txt"), "r") as f:
        assert f.read() == ""


@pytest.mark.asyncio
async def test_write_large_content(fs_tools, workspace_dir):
    """Test writing large content."""
    large_content = "x" * 1000000  # 1MB
    
    request = FsWriteRequest(
        path="large.txt",
        content=large_content,
        mode="create",
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    assert response.bytes_written == len(large_content)
    
    # Verify content
    with open(os.path.join(workspace_dir, "large.txt"), "r") as f:
        assert f.read() == large_content


@pytest.mark.asyncio
async def test_write_workspace_override_within_base(fs_tools, workspace_dir):
    """Test writing with workspace override within base workspace."""
    # Create subdirectory within workspace
    alt_workspace = os.path.join(workspace_dir, "subworkspace")
    os.makedirs(alt_workspace)
    
    request = FsWriteRequest(
        path="test.txt",
        content="override content",
        mode="create",
        workspace_dir=alt_workspace,
    )
    
    response = await fs_tools.write(request)
    
    assert response.created is True
    assert os.path.exists(os.path.join(alt_workspace, "test.txt"))
    
    # Verify content
    with open(os.path.join(alt_workspace, "test.txt"), "r") as f:
        assert f.read() == "override content"


@pytest.mark.asyncio
async def test_write_workspace_override_outside_blocked(fs_tools, workspace_dir):
    """Test that workspace override outside base workspace is blocked."""
    # Create alternate workspace outside base
    alt_workspace = tempfile.mkdtemp()
    
    try:
        request = FsWriteRequest(
            path="test.txt",
            content="malicious content",
            mode="create",
            workspace_dir=alt_workspace,
        )
        
        with pytest.raises(SecurityError, match="outside base workspace"):
            await fs_tools.write(request)
    
    finally:
        shutil.rmtree(alt_workspace)
