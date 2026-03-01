"""Filesystem tool implementations."""

import os
import re
import time
import fnmatch
from pathlib import Path
from datetime import datetime

from anyide.models import (
    FsReadRequest, FsReadResponse, 
    FsWriteRequest, FsWriteResponse,
    FsListRequest, FsListResponse, FsListEntry,
    FsSearchRequest, FsSearchResponse, FsSearchMatch
)
from anyide.core.workspace import WorkspaceManager, SecurityError
from anyide.logging_config import get_logger

logger = get_logger(__name__)


class FilesystemTools:
    """Filesystem tool implementations."""
    
    def __init__(self, workspace: WorkspaceManager):
        """Initialize filesystem tools.
        
        Args:
            workspace: Workspace manager instance
        """
        self.workspace = workspace
    
    async def read(self, request: FsReadRequest) -> FsReadResponse:
        """Read file contents.
        
        Args:
            request: Read request
            
        Returns:
            File contents and metadata
            
        Raises:
            SecurityError: If path escapes workspace
            FileNotFoundError: If file doesn't exist
            ValueError: If parameters are invalid
        """
        # Resolve path with security checks
        resolved_path = self.workspace.resolve_path(
            request.path,
            request.workspace_dir,
        )
        
        # Check if file exists
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(
                f"File not found: {request.path}. "
                f"Use fs_list to see available files."
            )
        
        # Check if it's a file (not a directory)
        if not os.path.isfile(resolved_path):
            raise ValueError(
                f"Path is not a file: {request.path}. "
                f"Use fs_list to list directory contents."
            )
        
        # Get file size
        size_bytes = os.path.getsize(resolved_path)
        
        # Read file contents
        try:
            with open(resolved_path, "r", encoding=request.encoding) as f:
                lines = f.readlines()
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Failed to decode file with encoding '{request.encoding}': {str(e)}. "
                f"Try a different encoding or check if this is a binary file."
            )
        
        line_count = len(lines)
        
        # Apply line range if specified
        if request.line_start is not None or request.line_end is not None:
            start = (request.line_start - 1) if request.line_start else 0
            end = request.line_end if request.line_end else line_count
            
            # Validate range
            if start < 0 or start >= line_count:
                raise ValueError(
                    f"line_start {request.line_start} is out of range. "
                    f"File has {line_count} lines."
                )
            if end < start:
                raise ValueError(
                    f"line_end {request.line_end} is before line_start {request.line_start}"
                )
            
            lines = lines[start:end]
        
        # Apply max_lines limit
        if request.max_lines is not None and len(lines) > request.max_lines:
            lines = lines[:request.max_lines]
        
        content = "".join(lines)
        
        logger.info(
            "file_read",
            path=resolved_path,
            size_bytes=size_bytes,
            lines_returned=len(lines),
            total_lines=line_count,
        )
        
        return FsReadResponse(
            content=content,
            path=resolved_path,
            size_bytes=size_bytes,
            line_count=line_count,
            encoding=request.encoding,
        )

    async def write(self, request: FsWriteRequest) -> FsWriteResponse:
        """Write content to a file.
        
        Args:
            request: Write request
            
        Returns:
            Write result with path and bytes written
            
        Raises:
            SecurityError: If path escapes workspace
            ValueError: If parameters are invalid
        """
        # Resolve path with security checks
        resolved_path = self.workspace.resolve_path(
            request.path,
            request.workspace_dir,
        )
        
        # Check if file exists
        file_exists = os.path.exists(resolved_path)
        
        # Validate mode
        if request.mode not in ("create", "overwrite", "append"):
            raise ValueError(
                f"Invalid mode '{request.mode}'. "
                f"Must be 'create', 'overwrite', or 'append'."
            )
        
        # Check mode constraints
        if request.mode == "create" and file_exists:
            raise ValueError(
                f"File already exists: {request.path}. "
                f"Use mode='overwrite' to replace or mode='append' to add content."
            )
        
        # Create parent directories if needed
        if request.create_dirs:
            parent_dir = os.path.dirname(resolved_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
                logger.info("created_directories", path=parent_dir)
        
        # Determine write mode
        if request.mode == "append":
            write_mode = "a"
        else:
            write_mode = "w"
        
        # Write content
        try:
            with open(resolved_path, write_mode, encoding=request.encoding) as f:
                f.write(request.content)
            
            bytes_written = len(request.content.encode(request.encoding))
            
            logger.info(
                "file_written",
                path=resolved_path,
                bytes_written=bytes_written,
                mode=request.mode,
                created=not file_exists,
            )
            
            return FsWriteResponse(
                path=resolved_path,
                bytes_written=bytes_written,
                created=not file_exists,
                mode=request.mode,
            )
        
        except Exception as e:
            logger.error("file_write_error", path=resolved_path, error=str(e), exc_info=True)
            raise ValueError(f"Failed to write file: {str(e)}")

    async def list(self, request: FsListRequest) -> FsListResponse:
        """List directory contents.
        
        Args:
            request: List request
            
        Returns:
            Directory listing with metadata
            
        Raises:
            SecurityError: If path escapes workspace
            FileNotFoundError: If directory doesn't exist
            ValueError: If parameters are invalid
        """
        # Resolve path with security checks
        resolved_path = self.workspace.resolve_path(
            request.path,
            request.workspace_dir,
        )
        
        # Check if directory exists
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(
                f"Directory not found: {request.path}"
            )
        
        # Check if it's a directory
        if not os.path.isdir(resolved_path):
            raise ValueError(
                f"Path is not a directory: {request.path}. "
                f"Use fs_read to read file contents."
            )
        
        entries = []
        
        def _list_directory(dir_path: str, current_depth: int = 0):
            """Recursively list directory contents."""
            if request.recursive and current_depth >= request.max_depth:
                return
            
            try:
                for entry_name in os.listdir(dir_path):
                    # Skip hidden files if not requested
                    if not request.include_hidden and entry_name.startswith('.'):
                        continue
                    
                    entry_path = os.path.join(dir_path, entry_name)
                    
                    # Apply pattern filter if specified
                    if request.pattern and not fnmatch.fnmatch(entry_name, request.pattern):
                        # For directories in recursive mode, still traverse them
                        if request.recursive and os.path.isdir(entry_path):
                            _list_directory(entry_path, current_depth + 1)
                        continue
                    
                    try:
                        stat = os.stat(entry_path)
                        is_dir = os.path.isdir(entry_path)
                        
                        # Get relative path from resolved_path
                        rel_path = os.path.relpath(entry_path, resolved_path)
                        
                        entries.append(FsListEntry(
                            name=rel_path if request.recursive else entry_name,
                            type="directory" if is_dir else "file",
                            size=0 if is_dir else stat.st_size,
                            modified=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            permissions=oct(stat.st_mode)[-3:],
                        ))
                        
                        # Recurse into subdirectories
                        if request.recursive and is_dir:
                            _list_directory(entry_path, current_depth + 1)
                    
                    except (OSError, PermissionError) as e:
                        logger.warning("list_entry_error", path=entry_path, error=str(e))
                        continue
            
            except (OSError, PermissionError) as e:
                logger.warning("list_directory_error", path=dir_path, error=str(e))
        
        # Start listing
        _list_directory(resolved_path)
        
        # Sort entries: directories first, then alphabetically
        entries.sort(key=lambda e: (e.type != "directory", e.name))
        
        logger.info(
            "directory_listed",
            path=resolved_path,
            total_entries=len(entries),
            recursive=request.recursive,
        )
        
        return FsListResponse(
            entries=entries,
            total_entries=len(entries),
            path=resolved_path,
        )
    
    async def search(self, request: FsSearchRequest) -> FsSearchResponse:
        """Search for files by name or content.
        
        Args:
            request: Search request
            
        Returns:
            Search results with matches
            
        Raises:
            SecurityError: If path escapes workspace
            ValueError: If parameters are invalid
        """
        start_time = time.time()
        
        # Resolve path with security checks
        resolved_path = self.workspace.resolve_path(
            request.path,
            request.workspace_dir,
        )
        
        # Check if directory exists
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(
                f"Directory not found: {request.path}"
            )
        
        # Validate search type
        if request.search_type not in ("filename", "content", "both"):
            raise ValueError(
                f"Invalid search_type '{request.search_type}'. "
                f"Must be 'filename', 'content', or 'both'."
            )
        
        # Compile regex pattern if needed
        if request.regex:
            try:
                pattern = re.compile(request.query, re.IGNORECASE)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {str(e)}")
        else:
            pattern = None
        
        results = []
        
        def _matches_query(text: str) -> bool:
            """Check if text matches the query."""
            if request.regex:
                return pattern.search(text) is not None
            else:
                return request.query.lower() in text.lower()
        
        def _search_directory(dir_path: str):
            """Recursively search directory."""
            if len(results) >= request.max_results:
                return
            
            try:
                for entry_name in os.listdir(dir_path):
                    if len(results) >= request.max_results:
                        break
                    
                    entry_path = os.path.join(dir_path, entry_name)
                    
                    # Get relative path
                    rel_path = os.path.relpath(entry_path, resolved_path)
                    
                    # Check filename match
                    if request.search_type in ("filename", "both"):
                        if _matches_query(entry_name):
                            results.append(FsSearchMatch(
                                path=rel_path,
                                type="filename",
                                match_line=None,
                                preview=None,
                            ))
                    
                    # Recurse into directories
                    if os.path.isdir(entry_path):
                        _search_directory(entry_path)
                    
                    # Search file content
                    elif request.search_type in ("content", "both"):
                        if os.path.isfile(entry_path):
                            try:
                                # Skip binary files
                                with open(entry_path, 'rb') as f:
                                    chunk = f.read(1024)
                                    if b'\x00' in chunk:
                                        continue
                                
                                # Search text content
                                with open(entry_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    for line_num, line in enumerate(f, 1):
                                        if len(results) >= request.max_results:
                                            break
                                        
                                        if _matches_query(line):
                                            preview = None
                                            if request.include_content_preview:
                                                # Get preview with context
                                                preview = line.strip()[:200]
                                            
                                            results.append(FsSearchMatch(
                                                path=rel_path,
                                                type="content",
                                                match_line=line_num,
                                                preview=preview,
                                            ))
                            
                            except (OSError, PermissionError, UnicodeDecodeError) as e:
                                logger.debug("search_file_error", path=entry_path, error=str(e))
                                continue
            
            except (OSError, PermissionError) as e:
                logger.warning("search_directory_error", path=dir_path, error=str(e))
        
        # Start search
        _search_directory(resolved_path)
        
        search_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(
            "search_completed",
            path=resolved_path,
            query=request.query,
            search_type=request.search_type,
            total_matches=len(results),
            search_time_ms=search_time_ms,
        )
        
        return FsSearchResponse(
            results=results,
            total_matches=len(results),
            search_time_ms=search_time_ms,
        )
