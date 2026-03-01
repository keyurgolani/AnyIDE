"""Workspace tool implementations."""

from typing import Callable, Optional

from anyide.models import WorkspaceInfoResponse
from anyide.core.workspace import WorkspaceManager
from anyide.logging_config import get_logger

logger = get_logger(__name__)


class WorkspaceTools:
    """Workspace tool implementations."""

    def __init__(
        self,
        workspace: WorkspaceManager,
        secret_manager=None,
        tool_categories_provider: Optional[Callable[[], list[str]]] = None,
    ):
        """Initialize workspace tools.

        Args:
            workspace: Workspace manager instance
            secret_manager: Optional SecretManager for reporting secret count
            tool_categories_provider: Optional callback that returns currently
                enabled tool categories.
        """
        self.workspace = workspace
        self.secret_manager = secret_manager
        self.tool_categories_provider = tool_categories_provider

    async def info(self) -> WorkspaceInfoResponse:
        """Get workspace information.

        Returns:
            Workspace configuration and status
        """
        workspace_info = self.workspace.get_workspace_info()

        secret_count = 0
        if self.secret_manager is not None:
            secret_count = self.secret_manager.count()

        logger.info("workspace_info_retrieved", secret_count=secret_count)

        tool_categories = [
            "fs",
            "workspace",
            "shell",
            "git",
            "docker",
            "http",
            "memory",
            "plan",
        ]
        if self.tool_categories_provider is not None:
            dynamic_categories = self.tool_categories_provider()
            if dynamic_categories:
                tool_categories = dynamic_categories

        return WorkspaceInfoResponse(
            default_workspace=workspace_info["default_workspace"],
            available_directories=[workspace_info["default_workspace"]],
            disk_usage=workspace_info["disk_usage"],
            tool_categories=tool_categories,
            secret_count=secret_count,
        )
