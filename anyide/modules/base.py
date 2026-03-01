"""Module base contract for plug-and-play tool categories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import FastAPI


class ToolModule(ABC):
    """Base class for AnyIDE tool modules."""

    def __init__(self, context: "ModuleContext"):
        self.context = context

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique module identifier used in config and routes."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable module name."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Module description for OpenAPI/UI surfaces."""

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def dependencies(self) -> list[str]:
        """Other module names this module depends on."""
        return []

    @property
    def mcp_tags(self) -> list[str]:
        """OpenAPI tags that should be exposed through MCP for this module."""
        return [self.name]

    @abstractmethod
    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        """Register root and module sub-app endpoints."""

    def on_startup(self) -> None:
        """Optional synchronous startup hook."""
        return None

    async def on_shutdown(self) -> None:
        """Optional async shutdown hook."""
        return None

    def get_config_schema(self) -> Optional[dict]:
        """Optional module-specific config schema."""
        return None


# Imported lazily to avoid circular imports at runtime typing evaluation time.
from anyide.modules.context import ModuleContext  # noqa: E402  pylint: disable=wrong-import-position
