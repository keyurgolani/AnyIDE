"""Pydantic schemas for subagent module tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SubagentRequestBase(BaseModel):
    """Base request schema with strict input validation."""

    model_config = ConfigDict(extra="forbid")


class SubagentTypeInfo(BaseModel):
    """Configured subagent type metadata."""

    type_id: str = Field(..., description="Subagent type identifier")
    display_name: str = Field(..., description="Human-readable subagent name")
    description: str = Field("", description="Subagent description")
    llm_endpoint: str = Field(..., description="Configured LLM endpoint id")
    model: Optional[str] = Field(
        None,
        description="Configured model override (or null if endpoint default is used)",
    )


class SubagentListResponse(BaseModel):
    """Response model for subagent_list."""

    types: list[SubagentTypeInfo] = Field(..., description="Configured subagent types")
    total: int = Field(..., description="Total configured type count")


class SubagentRunRequest(SubagentRequestBase):
    """Request model for subagent_run."""

    type: str = Field(..., min_length=1, description="Subagent type id")
    input: str = Field(..., min_length=1, description="Primary input for the subagent")
    context: Optional[str] = Field(None, description="Optional additional context")
    override_model: Optional[str] = Field(
        None,
        min_length=1,
        description="Optional model override if allowed by subagent config",
    )
    override_temperature: Optional[float] = Field(
        None,
        ge=0,
        le=2,
        description="Optional temperature override if allowed by subagent config",
    )


class SubagentRunResponse(BaseModel):
    """Response model for subagent_run."""

    type: str = Field(..., description="Subagent type id executed")
    model_used: str = Field(..., description="Model used for this execution")
    endpoint_used: str = Field(..., description="LLM endpoint id used")
    response: str = Field(..., description="Subagent response body")
    usage: dict[str, int] = Field(
        default_factory=lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
        description="Normalized token usage metadata",
    )
    latency_ms: int = Field(..., description="End-to-end LLM latency in milliseconds")
    response_format: Optional[str] = Field(
        None,
        description="Configured response format mode (for example 'json')",
    )
