"""Tests for fs_search tool."""

import os
import pytest
from anyide.modules.fs.tools import FilesystemTools
from anyide.core.workspace import WorkspaceManager
from anyide.models import FsSearchRequest


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
    """Create test directory structure with searchable content."""
    # Create files with content
    (tmp_path / "readme.txt").write_text("This is a README file\nWith multiple lines")
    (tmp_path / "config.yaml").write_text("database:\n  host: localhost\n  port: 5432")
    (tmp_path / "test_file.py").write_text("def test_function():\n    return 'hello world'")
    
    # Create subdirectories
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# User Guide\nThis is the user guide")
    (tmp_path / "docs" / "api.md").write_text("# API Reference\nAPI documentation here")
    
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("import os\nprint('Hello World')")
    
    return tmp_path


@pytest.mark.asyncio
async def test_search_filename(fs_tools, test_directory):
    """Test searching by filename."""
    request = FsSearchRequest(query="test", search_type="filename")
    response = await fs_tools.search(request)
    
    assert response.total_matches >= 1
    paths = [r.path for r in response.results]
    assert any("test_file.py" in p for p in paths)


@pytest.mark.asyncio
async def test_search_content(fs_tools, test_directory):
    """Test searching file content."""
    request = FsSearchRequest(query="hello", search_type="content")
    response = await fs_tools.search(request)
    
    assert response.total_matches >= 1
    
    # Should find "hello world" in test_file.py
    matches = [r for r in response.results if "test_file.py" in r.path]
    assert len(matches) > 0
    assert matches[0].type == "content"
    assert matches[0].match_line is not None


@pytest.mark.asyncio
async def test_search_both(fs_tools, test_directory):
    """Test searching both filename and content."""
    request = FsSearchRequest(query="guide", search_type="both")
    response = await fs_tools.search(request)
    
    # Should find guide.md by filename and "user guide" in content
    assert response.total_matches >= 2


@pytest.mark.asyncio
async def test_search_regex(fs_tools, test_directory):
    """Test regex search."""
    request = FsSearchRequest(
        query=r"test_\w+\.py",
        search_type="filename",
        regex=True
    )
    response = await fs_tools.search(request)
    
    assert response.total_matches >= 1
    paths = [r.path for r in response.results]
    assert any("test_file.py" in p for p in paths)


@pytest.mark.asyncio
async def test_search_case_insensitive(fs_tools, test_directory):
    """Test case-insensitive search."""
    request = FsSearchRequest(query="HELLO", search_type="content")
    response = await fs_tools.search(request)
    
    # Should find "hello" (lowercase) in files
    assert response.total_matches >= 1


@pytest.mark.asyncio
async def test_search_max_results(fs_tools, test_directory):
    """Test max_results limit."""
    request = FsSearchRequest(
        query=".",  # Match everything
        search_type="filename",
        max_results=3
    )
    response = await fs_tools.search(request)
    
    assert response.total_matches <= 3


@pytest.mark.asyncio
async def test_search_with_preview(fs_tools, test_directory):
    """Test content preview in results."""
    request = FsSearchRequest(
        query="localhost",
        search_type="content",
        include_content_preview=True
    )
    response = await fs_tools.search(request)
    
    assert response.total_matches >= 1
    
    # Check that preview is included
    match = response.results[0]
    assert match.preview is not None
    assert "localhost" in match.preview.lower()


@pytest.mark.asyncio
async def test_search_without_preview(fs_tools, test_directory):
    """Test search without content preview."""
    request = FsSearchRequest(
        query="localhost",
        search_type="content",
        include_content_preview=False
    )
    response = await fs_tools.search(request)
    
    assert response.total_matches >= 1
    
    # Check that preview is not included
    match = response.results[0]
    assert match.preview is None


@pytest.mark.asyncio
async def test_search_subdirectory(fs_tools, test_directory):
    """Test searching in subdirectory."""
    request = FsSearchRequest(
        query="guide",
        path="docs",
        search_type="both"
    )
    response = await fs_tools.search(request)
    
    assert response.total_matches >= 1
    
    # Results are relative to the search path (docs), not the workspace root
    # This is correct behavior - when you search in docs/, results are relative to docs/
    for result in response.results:
        # The path should not start with docs/ since we're already in docs/
        assert not result.path.startswith("docs/")


@pytest.mark.asyncio
async def test_search_nonexistent_directory(fs_tools, test_directory):
    """Test searching in nonexistent directory."""
    request = FsSearchRequest(query="test", path="nonexistent")
    
    with pytest.raises(FileNotFoundError):
        await fs_tools.search(request)


@pytest.mark.asyncio
async def test_search_invalid_type(fs_tools, test_directory):
    """Test invalid search type."""
    request = FsSearchRequest(query="test", search_type="invalid")
    
    with pytest.raises(ValueError, match="Invalid search_type"):
        await fs_tools.search(request)


@pytest.mark.asyncio
async def test_search_invalid_regex(fs_tools, test_directory):
    """Test invalid regex pattern."""
    request = FsSearchRequest(
        query="[invalid",
        search_type="filename",
        regex=True
    )
    
    with pytest.raises(ValueError, match="Invalid regex"):
        await fs_tools.search(request)


@pytest.mark.asyncio
async def test_search_timing(fs_tools, test_directory):
    """Test that search returns timing information."""
    request = FsSearchRequest(query="test", search_type="filename")
    response = await fs_tools.search(request)
    
    assert response.search_time_ms >= 0
    assert isinstance(response.search_time_ms, int)


@pytest.mark.asyncio
async def test_search_skips_binary_files(fs_tools, test_directory):
    """Test that binary files are skipped in content search."""
    # Create a binary file
    (test_directory / "binary.bin").write_bytes(b"\x00\x01\x02\x03\x04")
    
    request = FsSearchRequest(query=".", search_type="content")
    response = await fs_tools.search(request)
    
    # Binary file should not appear in content search results
    paths = [r.path for r in response.results]
    assert not any("binary.bin" in p for p in paths)
