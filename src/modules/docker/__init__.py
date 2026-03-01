"""Docker module package."""

from src.modules.docker.module import DockerModule

MODULE_CLASS = DockerModule

__all__ = ["DockerModule", "MODULE_CLASS"]
