"""Pydantic schemas for skills module tools."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class SkillsRequestBase(BaseModel):
    """Base class for request schemas with strict payload validation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SkillsListItem(BaseModel):
    """Single installed skill entry."""

    name: str = Field(..., description="Skill name")
    path: str = Field(..., description="Absolute path to the installed skill directory")
    description: str = Field("", description="Skill description from SKILL.md frontmatter")
    size_bytes: int = Field(..., description="Size of SKILL.md in bytes")
    installed_at: str = Field(..., description="ISO timestamp inferred from directory modified time")


class SkillsListResponse(BaseModel):
    """Response model for skills_list."""

    skills: list[SkillsListItem] = Field(..., description="Installed skills")
    total: int = Field(..., description="Total installed skills count")


class SkillsReadRequest(SkillsRequestBase):
    """Request model for skills_read."""

    name: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("name", "skill_id", "skill_name"),
        description=(
            "Installed skill name from `skills_list`. "
            "Aliases accepted for compatibility: `skill_id`, `skill_name`."
        ),
        examples=["demo-local-skill"],
    )
    section: Optional[str] = Field(
        None,
        min_length=1,
        description="Optional markdown section header to extract (e.g., 'Usage')",
        examples=["Usage"],
    )

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"name": "demo-local-skill"},
                {"skill_id": "demo-local-skill", "section": "Usage"},
            ]
        },
    )


class SkillsReadResponse(BaseModel):
    """Response model for skills_read."""

    name: str = Field(..., description="Skill name")
    content: str = Field(..., description="Full SKILL.md content or extracted section")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Parsed frontmatter metadata",
    )
    has_scripts: bool = Field(..., description="Whether scripts/ directory exists")
    has_references: bool = Field(..., description="Whether references/ directory exists")
    scripts: list[str] = Field(default_factory=list, description="Files under scripts/")
    references: list[str] = Field(
        default_factory=list,
        description="Files under references/",
    )


class SkillsReadFileRequest(SkillsRequestBase):
    """Request model for skills_read_file."""

    name: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("name", "skill_id", "skill_name"),
        description=(
            "Installed skill name from `skills_list`. "
            "Aliases accepted for compatibility: `skill_id`, `skill_name`."
        ),
        examples=["demo-local-skill"],
    )
    file_path: str = Field(
        ...,
        min_length=1,
        description="Relative file path within the skill directory",
        examples=["references/example.txt", "scripts/install.sh"],
    )

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"name": "demo-local-skill", "file_path": "references/example.txt"},
                {"skill_name": "demo-local-skill", "file_path": "scripts/install.sh"},
            ]
        },
    )


class SkillsReadFileResponse(BaseModel):
    """Response model for skills_read_file."""

    content: str = Field(..., description="File content")
    path: str = Field(..., description="Resolved absolute file path")


class SkillsSearchRequest(SkillsRequestBase):
    """Request model for skills_search."""

    query: str = Field(
        ...,
        min_length=1,
        description="Skills search query",
        examples=["vitest", "react testing", "fastapi templates"],
    )
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results")

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={"examples": [{"query": "vitest", "max_results": 5}]},
    )


class SkillsSearchResult(BaseModel):
    """Single search result from skills registry."""

    name: str = Field(..., description="Skill name")
    repo: str = Field(..., description="Repository owner/name")
    description: str = Field("", description="Skill description")
    installs: int = Field(0, description="Install count")


class SkillsSearchResponse(BaseModel):
    """Response model for skills_search."""

    query: str = Field(..., description="Query executed")
    results: list[SkillsSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Number of returned results")


class SkillsInstallRequest(SkillsRequestBase):
    """Request model for skills_install."""

    repo: str = Field(
        ...,
        min_length=3,
        description="Repository path, e.g. vercel-labs/agent-skills",
        examples=["vercel-labs/agent-skills"],
    )
    skill_name: Optional[str] = Field(
        None,
        min_length=1,
        validation_alias=AliasChoices("skill_name", "skill_id"),
        description="Optional skill name to install from the repository",
        examples=["vitest"],
    )

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"repo": "vercel-labs/agent-skills", "skill_name": "vitest"},
                {"repo": "vercel-labs/agent-skills", "skill_id": "vitest"},
            ]
        },
    )


class SkillsInstallResponse(BaseModel):
    """Response model for skills_install."""

    installed: bool = Field(..., description="Whether installation succeeded")
    skill_name: str = Field(..., description="Installed skill name")
    path: str = Field(..., description="Installed skill directory path")
    skill_md_preview: str = Field(
        ...,
        description="Preview of SKILL.md (first 500 characters)",
    )
