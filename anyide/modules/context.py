"""Shared runtime context passed to tool modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ModuleContext:
    """Shared app services and helpers for module registration/execution."""

    config: Any
    db: Any
    workspace_manager: Any
    audit_logger: Any
    policy_engine: Any
    hitl_manager: Any
    secret_manager: Any
    logger: Any
    execute_tool: Callable[..., Any]
    resolve_request_secrets: Callable[[Any], Any]
    tool_dispatch: Callable[[str, str, dict], Any]
    tool_dispatch_targets: dict[str, Any] = field(default_factory=dict)
    enabled_modules: list[str] = field(default_factory=list)

    def register_dispatch_target(self, category: str, target: Any) -> None:
        """Register an object whose methods are invokable by plan tool dispatch."""
        self.tool_dispatch_targets[category] = target

    def has_module(self, module_name: str) -> bool:
        return module_name in self.enabled_modules
