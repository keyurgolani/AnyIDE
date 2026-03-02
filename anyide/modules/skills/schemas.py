"""Pydantic schemas for skills module tools."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


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


class SkillsReadRequest(BaseModel):
    """Request model for skills_read."""

    name: str = Field(..., description="Installed skill name")
    section: Optional[str] = Field(
        None,
        description="Optional markdown section header to extract (e.g., 'Usage')",
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


class SkillsReadFileRequest(BaseModel):
    """Request model for skills_read_file."""

    name: str = Field(..., description="Installed skill name")
    file_path: str = Field(
        ...,
        description="Relative file path within the skill directory",
    )


class SkillsReadFileResponse(BaseModel):
    """Response model for skills_read_file."""

    content: str = Field(..., description="File content")
    path: str = Field(..., description="Resolved absolute file path")


class SkillsSearchRequest(BaseModel):
    """Request model for skills_search."""

    query: str = Field(..., min_length=1, description="Skills search query")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results")


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


class SkillsInstallRequest(BaseModel):
    """Request model for skills_install."""

    repo: str = Field(..., description="Repository path, e.g. vercel-labs/agent-skills")
    skill_name: Optional[str] = Field(
        None,
        description="Optional skill name to install from the repository",
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

