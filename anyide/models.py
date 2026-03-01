"""Pydantic models for tool requests and responses."""

from typing import List, Optional
from pydantic import BaseModel, Field


# Filesystem tool models

class FsReadRequest(BaseModel):
    """Request model for fs_read tool."""
    path: str = Field(..., description="File path relative to workspace")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")
    encoding: str = Field("utf-8", description="File encoding")
    max_lines: Optional[int] = Field(None, description="Limit returned lines (for large files)")
    line_start: Optional[int] = Field(None, description="Start reading from this line (1-indexed)")
    line_end: Optional[int] = Field(None, description="Stop reading at this line (1-indexed)")


class FsReadResponse(BaseModel):
    """Response model for fs_read tool."""
    content: str = Field(..., description="File contents")
    path: str = Field(..., description="Resolved absolute path")
    size_bytes: int = Field(..., description="File size in bytes")
    line_count: int = Field(..., description="Total number of lines")
    encoding: str = Field(..., description="File encoding used")


class FsWriteRequest(BaseModel):
    """Request model for fs_write tool."""
    path: str = Field(..., description="File path relative to workspace")
    content: str = Field(..., description="Content to write")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")
    mode: str = Field("create", description="Write mode: 'create', 'overwrite', or 'append'")
    create_dirs: bool = Field(True, description="Create parent directories if they don't exist")
    encoding: str = Field("utf-8", description="File encoding")


class FsWriteResponse(BaseModel):
    """Response model for fs_write tool."""
    path: str = Field(..., description="Resolved absolute path")
    bytes_written: int = Field(..., description="Number of bytes written")
    created: bool = Field(..., description="Whether file was newly created")
    mode: str = Field(..., description="Write mode used")


# Workspace tool models

class WorkspaceInfoResponse(BaseModel):
    """Response model for workspace_info tool."""
    default_workspace: str = Field(..., description="Default workspace directory")
    available_directories: list[str] = Field(..., description="Available workspace directories")
    disk_usage: dict = Field(..., description="Disk usage information")
    tool_categories: list[str] = Field(..., description="Available tool categories")
    secret_count: int = Field(0, description="Number of configured secrets")


# Filesystem list models

class FsListRequest(BaseModel):
    """Request model for fs_list tool."""
    path: str = Field(".", description="Directory path relative to workspace")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")
    recursive: bool = Field(False, description="List subdirectories recursively")
    max_depth: int = Field(3, description="Maximum depth for recursive listing")
    include_hidden: bool = Field(False, description="Include hidden files (starting with .)")
    pattern: Optional[str] = Field(None, description="Glob pattern filter (e.g., '*.py', 'test_*.txt')")


class FsListEntry(BaseModel):
    """Single entry in directory listing."""
    name: str = Field(..., description="File or directory name")
    type: str = Field(..., description="Entry type: 'file' or 'directory'")
    size: int = Field(..., description="Size in bytes (0 for directories)")
    modified: str = Field(..., description="Last modified timestamp")
    permissions: str = Field(..., description="Unix permissions string")


class FsListResponse(BaseModel):
    """Response model for fs_list tool."""
    entries: list[FsListEntry] = Field(..., description="Directory entries")
    total_entries: int = Field(..., description="Total number of entries")
    path: str = Field(..., description="Resolved directory path")


# Filesystem search models

class FsSearchRequest(BaseModel):
    """Request model for fs_search tool."""
    query: str = Field(..., description="Search pattern")
    path: str = Field(".", description="Directory to search in")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")
    search_type: str = Field("filename", description="Search type: 'filename', 'content', or 'both'")
    regex: bool = Field(False, description="Treat query as regex pattern")
    max_results: int = Field(50, description="Maximum number of results to return")
    include_content_preview: bool = Field(True, description="Include content preview for matches")


class FsSearchMatch(BaseModel):
    """Single search result."""
    path: str = Field(..., description="File path")
    type: str = Field(..., description="Match type: 'filename' or 'content'")
    match_line: Optional[int] = Field(None, description="Line number for content matches")
    preview: Optional[str] = Field(None, description="Content preview around match")


class FsSearchResponse(BaseModel):
    """Response model for fs_search tool."""
    results: list[FsSearchMatch] = Field(..., description="Search results")
    total_matches: int = Field(..., description="Total number of matches found")
    search_time_ms: int = Field(..., description="Search duration in milliseconds")


# Shell execution models

class ShellExecuteRequest(BaseModel):
    """Request model for shell_execute tool."""
    command: str = Field(..., description="Shell command to execute")
    workspace_dir: Optional[str] = Field(None, description="Working directory for command execution")
    timeout: int = Field(60, description="Timeout in seconds")
    env: Optional[dict[str, str]] = Field(None, description="Additional environment variables (use {{secret:KEY}} for sensitive values)")


class ShellExecuteResponse(BaseModel):
    """Response model for shell_execute tool."""
    stdout: str = Field(..., description="Standard output")
    stderr: str = Field(..., description="Standard error")
    exit_code: int = Field(..., description="Exit code")
    duration_ms: int = Field(..., description="Execution duration in milliseconds")
    command: str = Field(..., description="The command as executed")
    working_directory: str = Field(..., description="Working directory used")


# Git tool models

class GitStatusRequest(BaseModel):
    """Request model for git_status tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitStatusResponse(BaseModel):
    """Response model for git_status tool."""
    branch: str = Field(..., description="Current branch name")
    staged: list[dict] = Field(..., description="Staged files with status")
    unstaged: list[dict] = Field(..., description="Unstaged files with status")
    untracked: list[str] = Field(..., description="Untracked files")
    ahead: int = Field(..., description="Commits ahead of remote")
    behind: int = Field(..., description="Commits behind remote")
    clean: bool = Field(..., description="Whether working tree is clean")


class GitLogRequest(BaseModel):
    """Request model for git_log tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    max_count: int = Field(20, description="Maximum number of commits to return")
    author: Optional[str] = Field(None, description="Filter by author")
    since: Optional[str] = Field(None, description="Show commits since date")
    until: Optional[str] = Field(None, description="Show commits until date")
    path: Optional[str] = Field(None, description="Filter by file path")
    format: str = Field("medium", description="Output format: short, medium, or full")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitLogResponse(BaseModel):
    """Response model for git_log tool."""
    commits: list[dict] = Field(..., description="List of commits")
    total_shown: int = Field(..., description="Total number of commits shown")


class GitDiffRequest(BaseModel):
    """Request model for git_diff tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    ref: Optional[str] = Field(None, description="Commit/branch to diff against")
    path: Optional[str] = Field(None, description="Specific file to diff")
    staged: bool = Field(False, description="Show staged changes")
    stat_only: bool = Field(False, description="Show only statistics")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitDiffResponse(BaseModel):
    """Response model for git_diff tool."""
    diff: str = Field(..., description="Unified diff output")
    files_changed: int = Field(..., description="Number of files changed")
    insertions: int = Field(..., description="Number of insertions")
    deletions: int = Field(..., description="Number of deletions")


class GitCommitRequest(BaseModel):
    """Request model for git_commit tool."""
    message: str = Field(..., description="Commit message")
    repo_path: str = Field(".", description="Repository path relative to workspace")
    files: Optional[list[str]] = Field(None, description="Specific files to stage, or all if empty")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitCommitResponse(BaseModel):
    """Response model for git_commit tool."""
    hash: str = Field(..., description="Commit hash")
    message: str = Field(..., description="Commit message")
    files_committed: list[str] = Field(..., description="Files included in commit")


class GitPushRequest(BaseModel):
    """Request model for git_push tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    remote: str = Field("origin", description="Remote name")
    branch: Optional[str] = Field(None, description="Branch name (current branch if not specified)")
    force: bool = Field(False, description="Force push")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")
    # Credential fields for authenticated push (support {{secret:KEY}} templates)
    auth_username: Optional[str] = Field(None, description="Git username for authentication (use {{secret:KEY}} for secrets)")
    auth_password: Optional[str] = Field(None, description="Git password/token for authentication (use {{secret:KEY}} for secrets)")
    auth_env: Optional[dict[str, str]] = Field(None, description="Additional environment variables for git (use {{secret:KEY}} for sensitive values)")


class GitPushResponse(BaseModel):
    """Response model for git_push tool."""
    remote: str = Field(..., description="Remote name")
    branch: str = Field(..., description="Branch name")
    commits_pushed: int = Field(..., description="Number of commits pushed")
    output: str = Field(..., description="Git command output")


class GitPullRequest(BaseModel):
    """Request model for git_pull tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    remote: str = Field("origin", description="Remote name")
    branch: Optional[str] = Field(None, description="Branch name")
    rebase: bool = Field(False, description="Use rebase instead of merge")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")
    # Credential fields for authenticated pull (support {{secret:KEY}} templates)
    auth_username: Optional[str] = Field(None, description="Git username for authentication (use {{secret:KEY}} for secrets)")
    auth_password: Optional[str] = Field(None, description="Git password/token for authentication (use {{secret:KEY}} for secrets)")
    auth_env: Optional[dict[str, str]] = Field(None, description="Additional environment variables for git (use {{secret:KEY}} for sensitive values)")


class GitPullResponse(BaseModel):
    """Response model for git_pull tool."""
    updated: bool = Field(..., description="Whether repository was updated")
    commits_received: int = Field(..., description="Number of commits received")
    files_changed: list[str] = Field(..., description="Files that were changed")
    output: str = Field(..., description="Git command output")


class GitCheckoutRequest(BaseModel):
    """Request model for git_checkout tool."""
    target: str = Field(..., description="Branch name or commit hash")
    repo_path: str = Field(".", description="Repository path relative to workspace")
    create: bool = Field(False, description="Create new branch")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitCheckoutResponse(BaseModel):
    """Response model for git_checkout tool."""
    branch: str = Field(..., description="Current branch after checkout")
    previous_branch: str = Field(..., description="Previous branch")
    output: str = Field(..., description="Git command output")


class GitBranchRequest(BaseModel):
    """Request model for git_branch tool."""
    name: str = Field(..., description="Branch name")
    repo_path: str = Field(".", description="Repository path relative to workspace")
    action: str = Field("create", description="Action: create or delete")
    force: bool = Field(False, description="Force operation")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitBranchResponse(BaseModel):
    """Response model for git_branch tool."""
    branch: str = Field(..., description="Branch name")
    action: str = Field(..., description="Action performed")
    output: str = Field(..., description="Git command output")


class GitListBranchesRequest(BaseModel):
    """Request model for git_list_branches tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    remote: bool = Field(False, description="Include remote branches")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitListBranchesResponse(BaseModel):
    """Response model for git_list_branches tool."""
    branches: list[dict] = Field(..., description="List of branches")


class GitStashRequest(BaseModel):
    """Request model for git_stash tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    action: str = Field("push", description="Action: push, pop, list, or drop")
    message: Optional[str] = Field(None, description="Stash message (for push)")
    index: Optional[int] = Field(None, description="Stash index (for pop/drop)")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitStashResponse(BaseModel):
    """Response model for git_stash tool."""
    action: str = Field(..., description="Action performed")
    stashes: Optional[list[dict]] = Field(None, description="List of stashes (for list action)")
    output: str = Field(..., description="Git command output")


class GitShowRequest(BaseModel):
    """Request model for git_show tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    ref: str = Field("HEAD", description="Commit reference")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitShowResponse(BaseModel):
    """Response model for git_show tool."""
    hash: str = Field(..., description="Commit hash")
    author: str = Field(..., description="Commit author")
    date: str = Field(..., description="Commit date")
    message: str = Field(..., description="Commit message")
    body: str = Field(..., description="Commit body")
    diff: str = Field(..., description="Commit diff")
    files_changed: list[str] = Field(..., description="Files changed in commit")


class GitRemoteRequest(BaseModel):
    """Request model for git_remote tool."""
    repo_path: str = Field(".", description="Repository path relative to workspace")
    action: str = Field("list", description="Action: list, add, or remove")
    name: Optional[str] = Field(None, description="Remote name")
    url: Optional[str] = Field(None, description="Remote URL")
    workspace_dir: Optional[str] = Field(None, description="Override workspace directory")


class GitRemoteResponse(BaseModel):
    """Response model for git_remote tool."""
    remotes: list[dict] = Field(..., description="List of remotes")
    action: str = Field(..., description="Action performed")
    output: Optional[str] = Field(None, description="Git command output")


# Docker tool models

class DockerListRequest(BaseModel):
    """Request model for docker_list tool."""
    all: bool = Field(True, description="Include stopped containers")
    filter_name: Optional[str] = Field(None, description="Filter by container name (partial match)")
    filter_status: Optional[str] = Field(None, description="Filter by status (running, exited, paused, etc.)")


class DockerListResponse(BaseModel):
    """Response model for docker_list tool."""
    containers: list[dict] = Field(..., description="List of containers with id, name, image, status, ports, created")
    total_count: int = Field(..., description="Total number of containers found")


class DockerInspectRequest(BaseModel):
    """Request model for docker_inspect tool."""
    container: str = Field(..., description="Container name or ID")


class DockerInspectResponse(BaseModel):
    """Response model for docker_inspect tool."""
    id: str = Field(..., description="Container ID")
    name: str = Field(..., description="Container name")
    image: str = Field(..., description="Image name")
    status: str = Field(..., description="Container status")
    config: dict = Field(..., description="Container configuration")
    network: dict = Field(..., description="Network settings")
    mounts: list = Field(..., description="Volume mounts")
    ports: dict = Field(..., description="Port mappings")
    created: str = Field(..., description="Creation timestamp")
    state: dict = Field(..., description="Container state details")


class DockerLogsRequest(BaseModel):
    """Request model for docker_logs tool."""
    container: str = Field(..., description="Container name or ID")
    tail: int = Field(100, description="Number of lines from the end of logs")
    since: Optional[str] = Field(None, description="Show logs since timestamp (e.g., '2024-01-01T00:00:00')")
    follow: bool = Field(False, description="Follow log output (not recommended for API calls)")


class DockerLogsResponse(BaseModel):
    """Response model for docker_logs tool."""
    logs: str = Field(..., description="Container logs")
    container: str = Field(..., description="Container name or ID")
    line_count: int = Field(..., description="Number of log lines returned")


class DockerActionRequest(BaseModel):
    """Request model for docker_action tool."""
    container: str = Field(..., description="Container name or ID")
    action: str = Field(..., description="Action to perform: start, stop, restart, pause, unpause")
    timeout: int = Field(30, description="Timeout in seconds for the action")


class DockerActionResponse(BaseModel):
    """Response model for docker_action tool."""
    container: str = Field(..., description="Container name or ID")
    action: str = Field(..., description="Action performed")
    success: bool = Field(..., description="Whether the action succeeded")
    previous_status: str = Field(..., description="Status before action")
    new_status: str = Field(..., description="Status after action")
    message: str = Field(..., description="Result message")


# Workspace secrets models

class WorkspaceSecretsListResponse(BaseModel):
    """Response model for workspace_secrets_list tool."""
    keys: list[str] = Field(..., description="List of configured secret key names (values not exposed)")
    count: int = Field(..., description="Total number of configured secrets")
    secrets_file: str = Field(..., description="Path to the secrets file")


# HTTP request models

class HttpRequestRequest(BaseModel):
    """Request model for http_request tool."""
    url: str = Field(..., description="URL to request")
    method: str = Field("GET", description="HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD")
    headers: Optional[dict[str, str]] = Field(None, description="Request headers (use {{secret:KEY}} for sensitive values)")
    body: Optional[str] = Field(None, description="Request body (for POST/PUT/PATCH)")
    json_body: Optional[dict] = Field(None, description="JSON request body (for POST/PUT/PATCH, mutually exclusive with body)")
    timeout: int = Field(30, description="Request timeout in seconds")
    follow_redirects: bool = Field(True, description="Follow HTTP redirects")


class HttpRequestResponse(BaseModel):
    """Response model for http_request tool."""
    status_code: int = Field(..., description="HTTP status code")
    headers: dict[str, str] = Field(..., description="Response headers")
    body: str = Field(..., description="Response body as text")
    url: str = Field(..., description="Final URL after redirects")
    duration_ms: int = Field(..., description="Request duration in milliseconds")
    content_type: Optional[str] = Field(None, description="Response content type")


# Memory tool models

class MemoryStoreRelation(BaseModel):
    """A relation to create when storing a new node."""
    target_id: str = Field(..., description="Target node ID")
    relation: str = Field(..., description="Relation type (e.g. 'related_to', 'parent_of')")
    weight: float = Field(1.0, description="Relation strength (0.0–1.0+)")


class MemoryStoreRequest(BaseModel):
    """Request model for memory_store tool."""
    content: str = Field(..., description="The atomic piece of knowledge to store")
    name: Optional[str] = Field(None, description="Short name/title (defaults to first 60 chars of content)")
    entity_type: str = Field("concept", description="Node type: concept, fact, task, person, event, note")
    tags: Optional[list[str]] = Field(None, description="Tags for categorization and filtering")
    metadata: Optional[dict] = Field(None, description="Arbitrary key-value metadata")
    source: Optional[str] = Field(None, description="Origin of this knowledge (tool name, context, etc.)")
    relations: Optional[list[MemoryStoreRelation]] = Field(None, description="Edges to create to existing nodes")


class MemoryStoreResponse(BaseModel):
    """Response model for memory_store tool."""
    id: str = Field(..., description="New node ID (UUID)")
    name: str = Field(..., description="Node name used")
    created_at: str = Field(..., description="Creation timestamp (ISO 8601)")
    relations_created: int = Field(..., description="Number of edges created")


class MemoryNode(BaseModel):
    """A memory knowledge node."""
    id: str = Field(..., description="Node ID")
    name: str = Field(..., description="Node name/title")
    content: str = Field(..., description="Node content")
    entity_type: str = Field(..., description="Node type")
    tags: list[str] = Field(..., description="Tags")
    metadata: dict = Field(..., description="Metadata")
    source: Optional[str] = Field(None, description="Origin source")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class MemoryRelation(BaseModel):
    """A relationship edge from/to a memory node."""
    edge_id: str = Field(..., description="Edge ID")
    direction: str = Field(..., description="'outgoing' or 'incoming'")
    relation: str = Field(..., description="Relation type")
    weight: float = Field(..., description="Relation weight")
    neighbor: dict = Field(..., description="Connected node summary {id, name, entity_type, content_preview}")


class MemoryGetRequest(BaseModel):
    """Request model for memory_get tool."""
    id: str = Field(..., description="Node ID to retrieve")
    include_relations: bool = Field(True, description="Include connected edges and neighbor summaries")
    depth: int = Field(1, description="Hops of relationships to include (currently only 1 is supported)")


class MemoryGetResponse(BaseModel):
    """Response model for memory_get tool."""
    node: MemoryNode = Field(..., description="The retrieved node")
    relations: list[MemoryRelation] = Field(..., description="Edges connected to this node")


class MemorySearchRequest(BaseModel):
    """Request model for memory_search tool."""
    query: str = Field(..., description="Search text for full-text search")
    entity_type: Optional[str] = Field(None, description="Filter by entity type")
    tags: Optional[list[str]] = Field(None, description="Filter by tags (any match)")
    max_results: int = Field(10, description="Maximum number of results")
    search_mode: str = Field("hybrid", description="Search mode: 'fulltext', 'tags', or 'hybrid'")
    include_relations: bool = Field(False, description="Include edges in results")
    temporal_filter: Optional[str] = Field(None, description="ISO date — only return nodes created on or before this date")


class MemorySearchResult(BaseModel):
    """A single search result."""
    node: MemoryNode = Field(..., description="The matching node")
    relevance_score: float = Field(..., description="Relevance score (higher = more relevant)")
    matched_field: str = Field(..., description="Field that matched: 'content', 'tags', etc.")


class MemorySearchResponse(BaseModel):
    """Response model for memory_search tool."""
    results: list[MemorySearchResult] = Field(..., description="Ranked search results")
    total_matches: int = Field(..., description="Total number of matches found")
    search_time_ms: int = Field(..., description="Search duration in milliseconds")


class MemoryUpdateRequest(BaseModel):
    """Request model for memory_update tool."""
    id: str = Field(..., description="Node ID to update")
    content: Optional[str] = Field(None, description="New content (replaces existing)")
    name: Optional[str] = Field(None, description="New name")
    tags: Optional[list[str]] = Field(None, description="New tags (replaces existing)")
    metadata: Optional[dict] = Field(None, description="Metadata to merge into existing")


class MemoryUpdateResponse(BaseModel):
    """Response model for memory_update tool."""
    node: dict = Field(..., description="Updated node summary {id, name, updated_at}")
    previous_content: str = Field(..., description="Content before the update (for audit/undo)")


class MemoryDeleteRequest(BaseModel):
    """Request model for memory_delete tool."""
    id: str = Field(..., description="Node ID to delete")
    cascade: bool = Field(False, description="Also delete orphaned child nodes (nodes whose only parent was this one)")


class MemoryDeleteResponse(BaseModel):
    """Response model for memory_delete tool."""
    deleted_node: dict = Field(..., description="Deleted node summary {id, name}")
    deleted_edges: int = Field(..., description="Number of edges deleted")
    orphaned_children: list[dict] = Field(..., description="Child nodes that lost their only parent (not deleted unless cascade=true)")


class MemoryLinkRequest(BaseModel):
    """Request model for memory_link tool."""
    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    relation: str = Field(..., description="Relation type: related_to, depends_on, parent_of, contradicts, supersedes, derived_from")
    weight: float = Field(1.0, description="Relationship strength (0.0–1.0+)")
    bidirectional: bool = Field(False, description="Also create the reverse edge")
    metadata: Optional[dict] = Field(None, description="Edge metadata")
    valid_from: Optional[str] = Field(None, description="ISO 8601 date when this relationship became true")
    valid_until: Optional[str] = Field(None, description="ISO 8601 date when this relationship ended (null = current)")


class MemoryLinkResponse(BaseModel):
    """Response model for memory_link tool."""
    edge: dict = Field(..., description="Edge details {id, source_id, target_id, relation}")
    created: bool = Field(..., description="True if new edge, False if existing edge was updated")


class MemoryChildrenRequest(BaseModel):
    """Request model for memory_children tool."""
    id: str = Field(..., description="Parent node ID")


class MemoryAncestorsRequest(BaseModel):
    """Request model for memory_ancestors tool."""
    id: str = Field(..., description="Node ID to find ancestors of")
    max_depth: int = Field(10, description="Maximum traversal depth")


class MemoryRelatedRequest(BaseModel):
    """Request model for memory_related tool."""
    id: str = Field(..., description="Node ID to find related nodes for")
    relation: Optional[str] = Field(None, description="Filter by specific relation type (empty = all types)")


class MemorySubtreeRequest(BaseModel):
    """Request model for memory_subtree tool."""
    id: str = Field(..., description="Root node ID")
    max_depth: int = Field(10, description="Maximum traversal depth")


class MemoryNodesResponse(BaseModel):
    """Response model for graph traversal tools (children, ancestors, roots, related, subtree)."""
    nodes: list[MemoryNode] = Field(..., description="Matching nodes")
    total: int = Field(..., description="Total number of nodes returned")


class MemoryStatsResponse(BaseModel):
    """Response model for memory_stats tool."""
    total_nodes: int = Field(..., description="Total nodes in the knowledge graph")
    total_edges: int = Field(..., description="Total edges (relationships) in the graph")
    nodes_by_type: dict = Field(..., description="Node count broken down by entity_type")
    edges_by_relation: dict = Field(..., description="Edge count broken down by relation type")
    most_connected_nodes: list[dict] = Field(..., description="Top 10 most connected nodes by edge count")
    orphaned_nodes: int = Field(..., description="Nodes with no edges at all")
    created_last_24h: int = Field(..., description="Nodes created in the last 24 hours")
    tags_frequency: dict = Field(..., description="Tag usage frequency (top 50)")


# ---------------------------------------------------------------------------
# Plan execution models
# ---------------------------------------------------------------------------

class PlanTaskDef(BaseModel):
    """Definition of a single task within a plan."""
    id: str = Field(..., description="Unique task ID within the plan (used for depends_on references)")
    name: str = Field(..., description="Human-readable task name")
    tool_category: str = Field(..., description="Tool category (fs, shell, git, http, memory, etc.)")
    tool_name: str = Field(..., description="Tool name within the category")
    params: dict = Field(default_factory=dict, description="Tool parameters; may contain {{task:ID.field}} references")
    depends_on: List[str] = Field(default_factory=list, description="List of task IDs this task depends on")
    on_failure: Optional[str] = Field(None, description="Per-task failure policy override (stop|skip_dependents|continue); None uses plan default")
    require_hitl: bool = Field(False, description="If true, requires human approval before task execution")


class PlanCreateRequest(BaseModel):
    """Request to create a new plan."""
    name: str = Field(..., description="Human-readable plan name")
    tasks: List[PlanTaskDef] = Field(..., description="List of tasks forming the DAG")
    on_failure: str = Field("stop", description="Plan-level failure policy (stop|skip_dependents|continue)")
    metadata: dict = Field(default_factory=dict, description="Optional plan metadata")


class PlanCreateResponse(BaseModel):
    """Response from plan creation."""
    plan_id: str = Field(..., description="Unique plan ID (use this in plan_execute, plan_status, and plan_cancel)")
    name: str = Field(..., description="Plan name")
    task_count: int = Field(..., description="Number of tasks in the plan")
    execution_levels: int = Field(..., description="Number of parallel execution levels")
    execution_order: List[List[str]] = Field(..., description="Task IDs grouped by execution level")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class PlanTaskStatus(BaseModel):
    """Runtime status of a single plan task."""
    id: str
    name: str
    tool_category: str
    tool_name: str
    status: str = Field(..., description="Task status (pending|running|completed|failed|skipped)")
    output: Optional[dict] = Field(None, description="Task output as returned by the tool")
    error: Optional[str] = Field(None, description="Error message if task failed")
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    execution_level: int = Field(0, description="0-indexed parallel execution level")


class PlanStatusRequest(BaseModel):
    """Request to get plan status."""
    plan_id: str = Field(..., description="Plan reference. Prefer the plan_id returned by plan_create; unique plan names are also accepted.")


class PlanStatusResponse(BaseModel):
    """Current status of a plan and all its tasks."""
    plan_id: str
    name: str
    status: str = Field(..., description="Plan status (pending|running|completed|failed|cancelled)")
    on_failure: str
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    tasks: List[PlanTaskStatus]
    tasks_total: int
    tasks_completed: int
    tasks_failed: int
    tasks_skipped: int
    tasks_running: int


class PlanExecuteRequest(BaseModel):
    """Request to execute a plan."""
    plan_id: str = Field(..., description="Plan reference. Prefer the plan_id returned by plan_create; unique plan names are also accepted.")
    timeout: int = Field(3600, description="Maximum execution time in seconds (default 1 hour)")


class PlanExecuteResponse(BaseModel):
    """Response from plan execution."""
    plan_id: str = Field(..., description="Canonical plan ID that was executed")
    status: str = Field(..., description="Final plan status (completed|failed|cancelled)")
    tasks_completed: int
    tasks_failed: int
    tasks_skipped: int
    duration_ms: int


class PlanListItem(BaseModel):
    """Summary of a single plan for list responses."""
    plan_id: str
    name: str
    status: str
    on_failure: str
    task_count: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class PlanListResponse(BaseModel):
    """Response listing all plans."""
    plans: List[PlanListItem]
    total: int


class PlanCancelRequest(BaseModel):
    """Request to cancel a plan."""
    plan_id: str = Field(..., description="Plan reference. Prefer the plan_id returned by plan_create; unique plan names are also accepted.")


class PlanCancelResponse(BaseModel):
    """Response from plan cancellation."""
    plan_id: str
    cancelled_tasks: int
    status: str


# Error response model

class ErrorResponse(BaseModel):
    """Error response model."""
    error: bool = True
    error_type: str = Field(..., description="Error type identifier")
    message: str = Field(..., description="Human-readable error message")
    suggestion: Optional[str] = Field(None, description="Suggestion for recovery")
    suggestion_tool: Optional[str] = Field(None, description="Suggested tool to use instead")
