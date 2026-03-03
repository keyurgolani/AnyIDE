"""Tests for filesystem tools."""

import tempfile
import pytest
from pathlib import Path

from anyide.core.workspace import WorkspaceManager, SecurityError
from anyide.modules.fs.tools import FilesystemTools
from anyide.models import FsReadRequest


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        
        # Create test files
        (workspace / "test.txt").write_text("Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n")
        (workspace / "unicode.txt").write_text("Hello 世界\n")
        (workspace / "empty.txt").write_text("")
        
        # Create subdirectory
        (workspace / "subdir").mkdir()
        (workspace / "subdir" / "nested.txt").write_text("Nested content\n")
        
        yield str(workspace)


@pytest.fixture
def fs_tools(temp_workspace):
    """Create filesystem tools for testing."""
    workspace_manager = WorkspaceManager(temp_workspace)
    return FilesystemTools(workspace_manager)


class TestFsRead:
    """Test fs_read tool."""
    
    async def test_read_simple_file(self, fs_tools):
        """Test reading a simple file."""
        request = FsReadRequest(path="test.txt")
        response = await fs_tools.read(request)
        
        assert response.content == "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\n"
        assert response.line_count == 5
        assert response.encoding == "utf-8"
        assert response.size_bytes > 0
    
    async def test_read_unicode_file(self, fs_tools):
        """Test reading file with Unicode content."""
        request = FsReadRequest(path="unicode.txt")
        response = await fs_tools.read(request)
        
        assert "世界" in response.content
        assert response.line_count == 1
    
    async def test_read_empty_file(self, fs_tools):
        """Test reading empty file."""
        request = FsReadRequest(path="empty.txt")
        response = await fs_tools.read(request)
        
        assert response.content == ""
        assert response.line_count == 0
    
    async def test_read_nested_file(self, fs_tools):
        """Test reading file in subdirectory."""
        request = FsReadRequest(path="subdir/nested.txt")
        response = await fs_tools.read(request)
        
        assert response.content == "Nested content\n"
        assert response.line_count == 1
    
    async def test_read_with_line_range(self, fs_tools):
        """Test reading specific line range."""
        request = FsReadRequest(path="test.txt", line_start=2, line_end=4)
        response = await fs_tools.read(request)
        
        assert response.content == "Line 2\nLine 3\nLine 4\n"
        assert response.line_count == 5  # Total lines in file
    
    async def test_read_with_max_lines(self, fs_tools):
        """Test reading with max_lines limit."""
        request = FsReadRequest(path="test.txt", max_lines=3)
        response = await fs_tools.read(request)
        
        assert response.content == "Line 1\nLine 2\nLine 3\n"
        assert response.line_count == 5
    
    async def test_read_nonexistent_file(self, fs_tools):
        """Test reading nonexistent file."""
        request = FsReadRequest(path="nonexistent.txt")
        
        with pytest.raises(FileNotFoundError, match="File not found"):
            await fs_tools.read(request)
    
    async def test_read_directory(self, fs_tools):
        """Test reading a directory (should fail)."""
        request = FsReadRequest(path="subdir")
        
        with pytest.raises(ValueError, match="not a file"):
            await fs_tools.read(request)
    
    async def test_read_path_escape_attempt(self, fs_tools):
        """Test reading with path escape attempt."""
        request = FsReadRequest(path="../../etc/passwd")
        
        with pytest.raises(SecurityError, match="escapes workspace boundary"):
            await fs_tools.read(request)
    
    async def test_read_invalid_line_range(self, fs_tools):
        """Test reading with invalid line range."""
        request = FsReadRequest(path="test.txt", line_start=10, line_end=20)
        
        with pytest.raises(ValueError, match="out of range"):
            await fs_tools.read(request)
    
    async def test_read_invalid_encoding(self, fs_tools, temp_workspace):
        """Test reading with invalid encoding."""
        # Create a binary file
        binary_file = Path(temp_workspace) / "binary.dat"
        binary_file.write_bytes(b"\x80\x81\x82\x83")
        
        request = FsReadRequest(path="binary.dat", encoding="utf-8")
        
        with pytest.raises(ValueError, match="Failed to decode"):
            await fs_tools.read(request)
