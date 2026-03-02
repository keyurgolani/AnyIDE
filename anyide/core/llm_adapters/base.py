"""Shared adapter interfaces and error model for provider SDK wrappers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field


@dataclass
class LLMAdapterError(Exception):
    """Normalized provider error raised by adapter implementations."""

    error_type: str
    message: str
    provider: str
    retryable: bool = False
    status_code: Optional[int] = None
    raw_error: Any = None

    def __str__(self) -> str:  # pragma: no cover - trivial representation
        return self.message


class LLMAdapter(ABC):
    """Adapter interface implemented by provider-specific SDK wrappers."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        **kwargs,
    ) -> "LLMAdapterResponse":
        """Execute a completion and return normalized response payload."""


class LLMAdapterResponse(BaseModel):
    """Normalized response shape returned from adapter implementations."""

    content: str
    model: str
    finish_reason: Optional[str] = None
    usage: dict[str, int] = Field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }
    )
    raw: Any = None
