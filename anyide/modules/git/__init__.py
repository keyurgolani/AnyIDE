"""Git module package."""

from .module import GitModule

Module = GitModule
MODULE_CLASS = GitModule

__all__ = ["GitModule", "Module", "MODULE_CLASS"]
