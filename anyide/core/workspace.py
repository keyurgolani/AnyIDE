"""Workspace and path resolution with security checks."""

import os
from pathlib import Path
from typing import Optional

from anyide.logging_config import get_logger

logger = get_logger(__name__)


class SecurityError(Exception):
    """Raised when a security check fails."""
    pass


class WorkspaceManager:
    """Manages workspace boundaries and path resolution."""
    
    def __init__(self, base_dir: str):
        """Initialize workspace manager.
        
        Args:
            base_dir: The base workspace directory (must exist)
        """
        self.base_dir = os.path.realpath(base_dir)
        
        # Ensure base directory exists
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            logger.info("created_workspace_dir", path=self.base_dir)
        
        logger.info("workspace_initialized", base_dir=self.base_dir)
    
    def resolve_path(
        self,
        user_path: str,
        workspace_override: Optional[str] = None,
    ) -> str:
        """Resolve a user-provided path with security checks.
        
        This is the CRITICAL security function. It must handle:
        - Relative paths with .. traversal
        - Absolute paths that escape workspace
        - Symlinks that resolve outside workspace
        - Unicode normalization attacks
        - Null bytes in paths
        
        Args:
            user_path: Path provided by user/LLM
            workspace_override: Optional workspace directory override
            
        Returns:
            Resolved absolute path within workspace
            
        Raises:
            SecurityError: If path escapes workspace boundary
            ValueError: If path is invalid
        """
        # Check for null bytes
        if "\x00" in user_path:
            raise ValueError("Path contains null bytes")
        
        # Determine effective workspace
        if workspace_override:
            effective_workspace = os.path.realpath(workspace_override)
            # Workspace override must be within base workspace
            if not effective_workspace.startswith(self.base_dir):
                raise SecurityError(
                    f"Workspace override '{workspace_override}' is outside base workspace"
                )
        else:
            effective_workspace = self.base_dir
        
        # Resolve the path
        if os.path.isabs(user_path):
            # Absolute path - resolve it
            resolved = os.path.realpath(user_path)
        else:
            # Relative path - join with workspace and resolve
            resolved = os.path.realpath(
                os.path.join(effective_workspace, user_path)
            )
        
        # CRITICAL: Security check - must be within workspace boundaries
        # Use realpath to resolve symlinks, then check prefix
        if not resolved.startswith(effective_workspace + os.sep) and resolved != effective_workspace:
            raise SecurityError(
                f"Path '{user_path}' resolves to '{resolved}' which escapes workspace boundary '{effective_workspace}'"
            )
        
        logger.debug(
            "path_resolved",
            user_path=user_path,
            resolved=resolved,
            workspace=effective_workspace,
        )
        
        return resolved
    
    def is_within_workspace(self, path: str) -> bool:
        """Check if a path is within the workspace.
        
        Args:
            path: Path to check
            
        Returns:
            True if path is within workspace
        """
        try:
            resolved = os.path.realpath(path)
            return resolved.startswith(self.base_dir + os.sep) or resolved == self.base_dir
        except Exception:
            return False
    
    def get_workspace_info(self) -> dict:
        """Get workspace information.
        
        Returns:
            Dictionary with workspace info
        """
        try:
            stat = os.statvfs(self.base_dir)
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            used = total - free
            
            disk_usage = {
                "total": total,
                "used": used,
                "free": free,
            }
        except Exception as e:
            logger.warning("failed_to_get_disk_usage", error=str(e))
            disk_usage = {"total": 0, "used": 0, "free": 0}
        
        return {
            "default_workspace": self.base_dir,
            "disk_usage": disk_usage,
        }
