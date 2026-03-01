"""Shell module package."""

from .module import ShellModule

Module = ShellModule
MODULE_CLASS = ShellModule

__all__ = ["ShellModule", "Module", "MODULE_CLASS"]
