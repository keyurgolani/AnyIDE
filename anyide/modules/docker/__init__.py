"""Docker module package."""

from .module import DockerModule

Module = DockerModule
MODULE_CLASS = DockerModule

__all__ = ["DockerModule", "Module", "MODULE_CLASS"]
