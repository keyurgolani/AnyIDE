"""Module registry for discovery, selection, dependency resolution, and loading."""

from __future__ import annotations

import importlib
import os
import pkgutil
from pathlib import Path
from typing import Type

from fastapi import FastAPI

from anyide.modules.base import ToolModule
from anyide.modules.context import ModuleContext


class ModuleResolutionError(ValueError):
    """Raised when module selection/dependency resolution fails."""


class ModuleRegistry:
    """Discovers, validates, and loads AnyIDE tool modules."""

    def __init__(self, context: ModuleContext):
        self.context = context
        self._modules: dict[str, ToolModule] = {}
        self._load_order: list[str] = []
        self._mcp_tags: list[str] = []

    @property
    def modules(self) -> dict[str, ToolModule]:
        return dict(self._modules)

    @property
    def load_order(self) -> list[str]:
        return list(self._load_order)

    @property
    def mcp_tags(self) -> list[str]:
        return list(self._mcp_tags)

    def discover_modules(self) -> dict[str, Type[ToolModule]]:
        """Scan anyide.modules.* packages for ToolModule subclasses."""
        discovered: dict[str, Type[ToolModule]] = {}
        modules_dir = Path(__file__).resolve().parent

        for item in pkgutil.iter_modules([str(modules_dir)]):
            if not item.ispkg:
                continue
            if item.name.startswith("_"):
                continue

            package_name = f"anyide.modules.{item.name}"
            package = importlib.import_module(package_name)
            # Prefer the roadmap-prescribed `Module` export; keep
            # `MODULE_CLASS` fallback for backward compatibility.
            module_cls = getattr(package, "Module", None)
            if module_cls is None:
                module_cls = getattr(package, "MODULE_CLASS", None)
            if module_cls is None or not isinstance(module_cls, type):
                continue
            if not issubclass(module_cls, ToolModule):
                continue

            module_name = getattr(module_cls, "MODULE_NAME", None)
            if isinstance(module_name, str) and module_name:
                discovered[module_name] = module_cls
                continue

            # Fallback for modules that only expose runtime name property.
            instance = module_cls(self.context)
            discovered[instance.name] = module_cls

        return discovered

    def _parse_anyide_modules_env(self, available_names: list[str]) -> list[str] | None:
        raw = os.getenv("ANYIDE_MODULES")
        if raw is None:
            return None

        tokens = [token.strip() for token in raw.split(",") if token.strip()]
        if not tokens:
            return list(available_names)

        selected: list[str] = []

        def add_name(name: str) -> None:
            if name in available_names and name not in selected:
                selected.append(name)

        def remove_name(name: str) -> None:
            if name in selected:
                selected.remove(name)

        unknown: list[str] = []
        for token in tokens:
            if token == "all":
                selected = list(available_names)
                continue
            if token.startswith("-"):
                name = token[1:]
                if name not in available_names:
                    unknown.append(name)
                remove_name(name)
                continue
            if token not in available_names:
                unknown.append(token)
                continue
            add_name(token)

        if unknown:
            raise ModuleResolutionError(
                f"Unknown module(s) in ANYIDE_MODULES: {sorted(set(unknown))}. "
                f"Available modules: {available_names}"
            )

        return selected

    def parse_module_selection(self, available_names: list[str]) -> list[str]:
        """Parse enabled module list from env/config/defaults."""
        env_selected = self._parse_anyide_modules_env(available_names)
        if env_selected is not None:
            selected = env_selected
        else:
            enabled_cfg = list(getattr(self.context.config.modules, "enabled", []) or [])
            disabled_cfg = set(getattr(self.context.config.modules, "disabled", []) or [])

            unknown_cfg = [
                name
                for name in [*enabled_cfg, *disabled_cfg]
                if name and name not in available_names
            ]
            if unknown_cfg:
                raise ModuleResolutionError(
                    f"Unknown module(s) in config.modules: {sorted(set(unknown_cfg))}. "
                    f"Available modules: {available_names}"
                )

            if not enabled_cfg:
                selected = list(available_names)
            else:
                selected = [name for name in enabled_cfg if name in available_names]

            selected = [name for name in selected if name not in disabled_cfg]

        unknown = [name for name in selected if name not in available_names]
        if unknown:
            raise ModuleResolutionError(
                f"Unknown module(s) in selection: {sorted(set(unknown))}. "
                f"Available modules: {available_names}"
            )

        # Keep deterministic ordering based on discovery order.
        ordered = [name for name in available_names if name in selected]
        return ordered

    def resolve_load_order(
        self,
        selected: list[str],
        available: dict[str, Type[ToolModule]],
    ) -> list[str]:
        """Topologically sort modules by dependencies with validation."""
        temp: set[str] = set()
        perm: set[str] = set()
        order: list[str] = []

        def visit(name: str, stack: list[str]) -> None:
            if name in perm:
                return
            if name in temp:
                cycle_path = " -> ".join(stack + [name])
                raise ModuleResolutionError(f"Circular module dependency detected: {cycle_path}")

            if name not in selected:
                raise ModuleResolutionError(
                    f"Module '{stack[-1] if stack else name}' depends on '{name}', "
                    "but it is not enabled"
                )

            temp.add(name)
            module = available[name](self.context)
            for dep in module.dependencies:
                if dep not in available:
                    raise ModuleResolutionError(
                        f"Module '{name}' depends on unknown module '{dep}'"
                    )
                visit(dep, stack + [name])
            temp.remove(name)
            perm.add(name)
            if name not in order:
                order.append(name)

        for module_name in selected:
            visit(module_name, [])

        return order

    def load_modules(self, app: FastAPI) -> None:
        """Load selected modules, register routes, and mount sub-apps."""
        available = self.discover_modules()
        available_names = sorted(available.keys())

        selected = self.parse_module_selection(available_names)

        missing = [name for name in selected if name not in available]
        if missing:
            raise ModuleResolutionError(
                f"Module(s) not found: {missing}. Available: {available_names}"
            )

        self._load_order = self.resolve_load_order(selected, available)

        loaded_tags: list[str] = []
        for module_name in self._load_order:
            module_cls = available[module_name]
            module = module_cls(self.context)

            sub_app = FastAPI(
                title=f"AnyIDE — {module.display_name}",
                description=module.description,
                version=module.version,
            )

            module.register_tools(app, sub_app)
            app.mount(f"/tools/{module.name}", sub_app)
            module.on_startup()

            self._modules[module_name] = module
            for tag in module.mcp_tags:
                if tag not in loaded_tags:
                    loaded_tags.append(tag)

        self._mcp_tags = loaded_tags
        self.context.enabled_modules = list(self._load_order)

    async def shutdown_modules(self) -> None:
        """Run shutdown hooks in reverse load order."""
        for module_name in reversed(self._load_order):
            module = self._modules.get(module_name)
            if module is None:
                continue
            await module.on_shutdown()
