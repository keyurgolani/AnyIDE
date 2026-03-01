"""Tests for fs_list tool."""

import os
import pytest
from anyide.modules.fs.tools import FilesystemTools
from anyide.core.workspace import WorkspaceManager
from anyide.models import FsListRequest


@pytest.fixture
def workspace_manager(tmp_path):
    """Create workspace manager with temp directory."""
    return WorkspaceManager(str(tmp_path))


@pytest.fixture
def fs_tools(workspace_manager):
    """Create filesystem tools instance."""
    return FilesystemTools(workspace_manager)


@pytest.fixture
def test_directory(tmp_path):
    """Create test directory structure."""
    # Create files
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.py").write_text("print('hello')")
    (tmp_path / ".hidden").write_text("hidden content")
    
    # Create subdirectories
    (tmp_path / "subdir1").mkdir()
    (tmp_path / "subdir1" / "nested.txt").write_text("nested content")
    (tmp_path / "subdir2").mkdir()
    (tmp_path / "subdir2" / "deep").mkdir()
    (tmp_path / "subdir2" / "deep" / "file.txt").write_text("deep file")
    
    return tmp_path


@pytest.mark.asyncio
async def test_list_basic(fs_tools, test_directory):
    """Test basic directory listing."""
    request = FsListRequest(path=".")
    response = await fs_tools.list(request)
    
    assert response.total_entries >= 4  # At least 4 visible entries
    assert response.path == str(test_directory)
    
    # Check entries
    names = [e.name for e in response.entries]
    assert "file1.txt" in names
    assert "file2.py" in names
    assert "subdir1" in names
    assert "subdir2" in names
    assert ".hidden" not in names  # Hidden files excluded by default


@pytest.mark.asyncio
async def test_list_with_hidden(fs_tools, test_directory):
    """Test listing with hidden files."""
    request = FsListRequest(path=".", include_hidden=True)
    response = await fs_tools.list(request)
    
    names = [e.name for e in response.entries]
    assert ".hidden" in names


@pytest.mark.asyncio
async def test_list_recursive(fs_tools, test_directory):
    """Test recursive directory listing."""
    request = FsListRequest(path=".", recursive=True, max_depth=3)
    response = await fs_tools.list(request)
    
    names = [e.name for e in response.entries]
    assert "file1.txt" in names
    assert "subdir1/nested.txt" in names or "subdir1\\nested.txt" in names
    assert any("deep" in name and "file.txt" in name for name in names)


@pytest.mark.asyncio
async def test_list_with_pattern(fs_tools, test_directory):
    """Test listing with glob pattern."""
    request = FsListRequest(path=".", pattern="*.txt")
    response = await fs_tools.list(request)
    
    names = [e.name for e in response.entries]
    assert "file1.txt" in names
    assert "file2.py" not in names


@pytest.mark.asyncio
async def test_list_subdirectory(fs_tools, test_directory):
    """Test listing a subdirectory."""
    request = FsListRequest(path="subdir1")
    response = await fs_tools.list(request)
    
    assert response.total_entries == 1
    names = [e.name for e in response.entries]
    assert "nested.txt" in names


@pytest.mark.asyncio
async def test_list_nonexistent(fs_tools, test_directory):
    """Test listing nonexistent directory."""
    request = FsListRequest(path="nonexistent")
    
    with pytest.raises(FileNotFoundError):
        await fs_tools.list(request)


@pytest.mark.asyncio
async def test_list_file_not_directory(fs_tools, test_directory):
    """Test listing a file instead of directory."""
    request = FsListRequest(path="file1.txt")
    
    with pytest.raises(ValueError, match="not a directory"):
        await fs_tools.list(request)


@pytest.mark.asyncio
async def test_list_entry_metadata(fs_tools, test_directory):
    """Test that entries have correct metadata."""
    request = FsListRequest(path=".")
    response = await fs_tools.list(request)
    
    # Find file1.txt entry
    file_entry = next(e for e in response.entries if e.name == "file1.txt")
    
    assert file_entry.type == "file"
    assert file_entry.size > 0
    assert file_entry.modified  # Has timestamp
    assert file_entry.permissions  # Has permissions
    
    # Find subdir1 entry
    dir_entry = next(e for e in response.entries if e.name == "subdir1")
    
    assert dir_entry.type == "directory"
    assert dir_entry.size == 0  # Directories have size 0


@pytest.mark.asyncio
async def test_list_sorted(fs_tools, test_directory):
    """Test that entries are sorted (directories first, then alphabetically)."""
    request = FsListRequest(path=".")
    response = await fs_tools.list(request)
    
    # Directories should come before files
    types = [e.type for e in response.entries]
    
    # Find first file index
    first_file_idx = next((i for i, t in enumerate(types) if t == "file"), len(types))
    
    # All directories should be before first file
    for i in range(first_file_idx):
        assert types[i] == "directory"
