"""Pydantic schemas for language module tools."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class LangSymbolRef(BaseModel):
    """Flat symbol reference entry."""

    name: str
    kind: str
    start_line: int
    end_line: int


class LangSymbol(BaseModel):
    """Structural symbol entry for skeleton/read responses."""

    name: str
    kind: Literal["function", "class", "method", "variable", "import", "type"]
    signature: str = ""
    start_line: int
    end_line: int
    children: list[LangSymbolRef] = Field(default_factory=list)


class LangReadFileRequest(BaseModel):
    """Request for lang_read_file."""

    path: str
    workspace_dir: Optional[str] = None
    window: Optional[str] = None
    format: Literal["raw", "numbered", "skeleton"] = "numbered"


class LangReadFileResponse(BaseModel):
    """Response for lang_read_file."""

    path: str
    language: str
    total_lines: int
    content: str
    window_applied: Optional[str] = None
    symbols_in_view: list[LangSymbolRef] = Field(default_factory=list)


class LangSkeletonRequest(BaseModel):
    """Request for lang_skeleton."""

    paths: list[str]
    workspace_dir: Optional[str] = None
    depth: Literal["signatures", "full"] = "signatures"
    include_line_numbers: bool = True

    @field_validator("paths")
    @classmethod
    def _paths_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("paths must contain at least one path or glob pattern")
        return value


class LangSkeletonFile(BaseModel):
    """Skeleton output for one file."""

    path: str
    language: str
    symbols: list[LangSymbol] = Field(default_factory=list)


class LangSkeletonResponse(BaseModel):
    """Response for lang_skeleton."""

    files: list[LangSkeletonFile] = Field(default_factory=list)


class LangDiffValidation(BaseModel):
    """Syntax validation payload for lang_diff."""

    syntax_valid: bool
    errors: list[str] = Field(default_factory=list)


class LangDiffHunk(BaseModel):
    """Function-anchored hunk details."""

    anchor: str
    anchor_signature: str
    anchor_file_line: int
    old_content: str
    new_content: str
    context_before: str = ""
    context_after: str = ""


class LangDiffRequest(BaseModel):
    """Request for lang_diff."""

    path: str
    new_content: str
    format: Literal["unified", "structural", "function_anchored"] = "function_anchored"
    workspace_dir: Optional[str] = None


class LangDiffResponse(BaseModel):
    """Response for lang_diff."""

    hunks: list[LangDiffHunk] = Field(default_factory=list)
    summary: str
    validation: LangDiffValidation


class LangApplyPatchHunk(BaseModel):
    """Patch hunk for lang_apply_patch."""

    anchor: str
    old_content: str
    new_content: str


class LangApplyPatchRequest(BaseModel):
    """Request for lang_apply_patch."""

    path: str
    hunks: list[LangApplyPatchHunk]
    workspace_dir: Optional[str] = None
    run_validation: bool = Field(True, alias="validate", serialization_alias="validate")
    create_backup: bool = True

    @field_validator("hunks")
    @classmethod
    def _hunks_not_empty(cls, value: list[LangApplyPatchHunk]) -> list[LangApplyPatchHunk]:
        if not value:
            raise ValueError("hunks must contain at least one patch operation")
        return value


class LangLintIssue(BaseModel):
    """Lint issue entry."""

    line: int
    message: str
    severity: str
    col: Optional[int] = None
    rule: Optional[str] = None
    fix_available: bool = False


class LangTypeIssue(BaseModel):
    """Type diagnostic issue entry."""

    line: int
    message: str
    severity: str = "error"
    col: Optional[int] = None


class LangPatchValidation(BaseModel):
    """Validation payload for lang_apply_patch."""

    syntax_valid: bool
    lint_errors: list[LangLintIssue] = Field(default_factory=list)
    type_errors: list[LangTypeIssue] = Field(default_factory=list)


class LangPatchFailedHunk(BaseModel):
    """Failed patch operation detail."""

    anchor: str
    reason: str


class LangApplyPatchResponse(BaseModel):
    """Response for lang_apply_patch."""

    path: str
    applied_hunks: int
    failed_hunks: list[LangPatchFailedHunk] = Field(default_factory=list)
    backup_path: Optional[str] = None
    validation: LangPatchValidation


class LangParseError(BaseModel):
    """Parser error entry."""

    line: int
    col: int
    message: str


class LangCreateFileRequest(BaseModel):
    """Request for lang_create_file."""

    path: str
    content: str
    workspace_dir: Optional[str] = None
    run_validation: bool = Field(True, alias="validate", serialization_alias="validate")


class LangCreateFileValidation(BaseModel):
    """Validation payload for lang_create_file."""

    syntax_valid: bool
    parse_errors: list[LangParseError] = Field(default_factory=list)
    lint_errors: list[LangLintIssue] = Field(default_factory=list)


class LangCreateFileResponse(BaseModel):
    """Response for lang_create_file."""

    path: str
    language: str
    validation: LangCreateFileValidation
    symbols_created: list[LangSymbolRef] = Field(default_factory=list)


class LangIndexRequest(BaseModel):
    """Request for lang_index."""

    workspace_dir: Optional[str] = None
    languages: Optional[list[str]] = None
    force_reindex: bool = False


class LangIndexResponse(BaseModel):
    """Response for lang_index."""

    files_indexed: int
    symbols_indexed: int
    languages_detected: list[str] = Field(default_factory=list)
    index_time_ms: int
    index_size_bytes: int


class LangSearchSymbolsRequest(BaseModel):
    """Request for lang_search_symbols."""

    query: str
    kind: Optional[str] = None
    language: Optional[str] = None
    workspace_dir: Optional[str] = None
    max_results: int = Field(20, ge=1, le=200)


class LangSearchSymbolResult(BaseModel):
    """One symbol search hit."""

    name: str
    kind: str
    file: str
    start_line: int
    end_line: int
    signature: str
    language: str


class LangSearchSymbolsResponse(BaseModel):
    """Response for lang_search_symbols."""

    results: list[LangSearchSymbolResult] = Field(default_factory=list)


class LangReferenceGraphRequest(BaseModel):
    """Request for lang_reference_graph."""

    path: str
    scope: Literal["file", "workspace"] = "file"
    workspace_dir: Optional[str] = None
    target_symbol: Optional[str] = None


class LangReferenceNode(BaseModel):
    """Reference graph node."""

    id: str
    name: str
    kind: str
    file: str
    start_line: int
    end_line: int


class LangReferenceCallSite(BaseModel):
    """Reference graph call site."""

    file: str
    line: int


class LangReferenceEdge(BaseModel):
    """Reference graph edge."""

    source: str
    target: str
    call_sites: list[LangReferenceCallSite] = Field(default_factory=list)


class LangReferenceGraphResponse(BaseModel):
    """Response for lang_reference_graph."""

    nodes: list[LangReferenceNode] = Field(default_factory=list)
    edges: list[LangReferenceEdge] = Field(default_factory=list)


class LangValidateRequest(BaseModel):
    """Request for lang_validate."""

    path: str
    workspace_dir: Optional[str] = None
    checks: list[Literal["syntax", "lint", "type"]] = Field(
        default_factory=lambda: ["syntax", "lint"]
    )

    @field_validator("checks")
    @classmethod
    def _checks_not_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("checks must include at least one validation type")
        return value


class LangValidateSyntax(BaseModel):
    """Syntax validation block."""

    valid: bool
    errors: list[LangParseError] = Field(default_factory=list)


class LangValidateLint(BaseModel):
    """Lint validation block."""

    tool: Optional[str] = None
    errors: list[LangLintIssue] = Field(default_factory=list)


class LangValidateTypeCheck(BaseModel):
    """Type-check validation block."""

    tool: Optional[str] = None
    errors: list[LangTypeIssue] = Field(default_factory=list)


class LangValidateResponse(BaseModel):
    """Response for lang_validate."""

    path: str
    language: str
    syntax: LangValidateSyntax
    lint: LangValidateLint
    type_check: LangValidateTypeCheck
