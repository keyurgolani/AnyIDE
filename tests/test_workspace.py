"""Tests for workspace path resolution."""

import os
import tempfile
import pytest
from pathlib import Path

from anyide.core.workspace import WorkspaceManager, SecurityError


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create some test structure
        workspace = Path(tmpdir)
        (workspace / "projects").mkdir()
        (workspace / "projects" / "test.txt").write_text("test content")
        (workspace / "configs").mkdir()
        (workspace / "configs" / "app.conf").write_text("config content")
        
        yield str(workspace)


@pytest.fixture
def workspace_manager(temp_workspace):
    """Create a workspace manager for testing."""
    return WorkspaceManager(temp_workspace)


class TestPathResolution:
    """Test path resolution with security checks."""
    
    def test_resolve_relative_path(self, workspace_manager, temp_workspace):
        """Test resolving a simple relative path."""
        resolved = workspace_manager.resolve_path("projects/test.txt")
        expected = os.path.join(temp_workspace, "projects", "test.txt")
        assert resolved == os.path.realpath(expected)
    
    def test_resolve_absolute_path_within_workspace(self, workspace_manager, temp_workspace):
        """Test resolving an absolute path within workspace."""
        abs_path = os.path.join(temp_workspace, "projects", "test.txt")
        resolved = workspace_manager.resolve_path(abs_path)
        assert resolved == os.path.realpath(abs_path)
    
    def test_resolve_path_with_dot_dot(self, workspace_manager, temp_workspace):
        """Test resolving path with .. that stays within workspace."""
        resolved = workspace_manager.resolve_path("projects/../configs/app.conf")
        expected = os.path.join(temp_workspace, "configs", "app.conf")
        assert resolved == os.path.realpath(expected)
    
    def test_block_path_escape_with_dot_dot(self, workspace_manager, temp_workspace):
        """Test blocking path that escapes workspace with ..."""
        with pytest.raises(SecurityError, match="escapes workspace boundary"):
            workspace_manager.resolve_path("../../etc/passwd")
    
    def test_block_absolute_path_outside_workspace(self, workspace_manager):
        """Test blocking absolute path outside workspace."""
        with pytest.raises(SecurityError, match="escapes workspace boundary"):
            workspace_manager.resolve_path("/etc/passwd")
    
    def test_block_null_byte_in_path(self, workspace_manager):
        """Test blocking path with null byte."""
        with pytest.raises(ValueError, match="null bytes"):
            workspace_manager.resolve_path("test\x00.txt")
    
    def test_resolve_path_with_symlink_within_workspace(self, workspace_manager, temp_workspace):
        """Test resolving symlink that points within workspace."""
        # Create a symlink
        target = os.path.join(temp_workspace, "projects", "test.txt")
        link = os.path.join(temp_workspace, "link.txt")
        os.symlink(target, link)
        
        resolved = workspace_manager.resolve_path("link.txt")
        # Should resolve to the target
        assert resolved == os.path.realpath(target)
    
    def test_block_symlink_escape(self, workspace_manager, temp_workspace):
        """Test blocking symlink that points outside workspace."""
        # Create a symlink pointing outside
        link = os.path.join(temp_workspace, "evil_link.txt")
        os.symlink("/etc/passwd", link)
        
        with pytest.raises(SecurityError, match="escapes workspace boundary"):
            workspace_manager.resolve_path("evil_link.txt")
    
    def test_workspace_override_within_base(self, workspace_manager, temp_workspace):
        """Test workspace override that's within base workspace."""
        projects_dir = os.path.join(temp_workspace, "projects")
        resolved = workspace_manager.resolve_path("test.txt", workspace_override=projects_dir)
        expected = os.path.join(projects_dir, "test.txt")
        assert resolved == os.path.realpath(expected)
    
    def test_block_workspace_override_outside_base(self, workspace_manager):
        """Test blocking workspace override outside base workspace."""
        with pytest.raises(SecurityError, match="outside base workspace"):
            workspace_manager.resolve_path("test.txt", workspace_override="/tmp")
    
    def test_resolve_current_directory(self, workspace_manager, temp_workspace):
        """Test resolving current directory (.)."""
        resolved = workspace_manager.resolve_path(".")
        assert resolved == os.path.realpath(temp_workspace)
    
    def test_resolve_parent_within_workspace(self, workspace_manager, temp_workspace):
        """Test resolving parent directory that's within workspace."""
        resolved = workspace_manager.resolve_path("projects/..")
        assert resolved == os.path.realpath(temp_workspace)
    
    def test_is_within_workspace(self, workspace_manager, temp_workspace):
        """Test checking if path is within workspace."""
        within_path = os.path.join(temp_workspace, "projects", "test.txt")
        assert workspace_manager.is_within_workspace(within_path)
        
        outside_path = "/etc/passwd"
        assert not workspace_manager.is_within_workspace(outside_path)
    
    def test_get_workspace_info(self, workspace_manager, temp_workspace):
        """Test getting workspace information."""
        info = workspace_manager.get_workspace_info()
        
        assert info["default_workspace"] == os.path.realpath(temp_workspace)
        assert "disk_usage" in info
        assert "total" in info["disk_usage"]
        assert "used" in info["disk_usage"]
        assert "free" in info["disk_usage"]


class TestEdgeCases:
    """Test edge cases in path resolution."""
    
    def test_empty_path(self, workspace_manager):
        """Test handling empty path."""
        # Empty path should resolve to workspace root
        resolved = workspace_manager.resolve_path("")
        assert resolved == workspace_manager.base_dir
    
    def test_path_with_trailing_slash(self, workspace_manager, temp_workspace):
        """Test path with trailing slash."""
        resolved = workspace_manager.resolve_path("projects/")
        expected = os.path.join(temp_workspace, "projects")
        assert resolved == os.path.realpath(expected)
    
    def test_path_with_multiple_slashes(self, workspace_manager, temp_workspace):
        """Test path with multiple consecutive slashes."""
        resolved = workspace_manager.resolve_path("projects//test.txt")
        expected = os.path.join(temp_workspace, "projects", "test.txt")
        assert resolved == os.path.realpath(expected)
    
    def test_unicode_path(self, workspace_manager, temp_workspace):
        """Test Unicode characters in path."""
        # Create a file with Unicode name
        unicode_file = Path(temp_workspace) / "测试.txt"
        unicode_file.write_text("test")
        
        resolved = workspace_manager.resolve_path("测试.txt")
        assert resolved == os.path.realpath(str(unicode_file))
