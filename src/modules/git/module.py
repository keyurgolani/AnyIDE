"""Git tools module."""

from __future__ import annotations

from fastapi import FastAPI

from src.models import (
    GitStatusRequest,
    GitStatusResponse,
    GitLogRequest,
    GitLogResponse,
    GitDiffRequest,
    GitDiffResponse,
    GitCommitRequest,
    GitCommitResponse,
    GitPushRequest,
    GitPushResponse,
    GitPullRequest,
    GitPullResponse,
    GitCheckoutRequest,
    GitCheckoutResponse,
    GitBranchRequest,
    GitBranchResponse,
    GitListBranchesRequest,
    GitListBranchesResponse,
    GitStashRequest,
    GitStashResponse,
    GitShowRequest,
    GitShowResponse,
    GitRemoteRequest,
    GitRemoteResponse,
)
from src.modules.base import ToolModule
from src.tools.git_tools import GitTools


_STATUS_DESC = """Get the current status of a git repository.

Shows:
- Current branch
- Staged files
- Unstaged changes
- Untracked files
- Commits ahead/behind remote

Use this tool to check the state of a repository before making changes."""

_LOG_DESC = """View the commit history of a git repository.

Supports filtering by:
- Author
- Date range (since/until)
- File path
- Maximum number of commits

Use this tool to review recent changes or find specific commits."""

_DIFF_DESC = """View file differences in a git repository.

Can show:
- Unstaged changes (default)
- Staged changes (--cached)
- Diff against specific commit/branch
- Statistics only (files changed, insertions, deletions)

Use this tool to review changes before committing."""

_COMMIT_DESC = """Create a git commit with the specified message.

This operation:
- Stages specified files (or all changes if none specified)
- Creates a commit with the provided message
- Returns the commit hash and list of files committed

IMPORTANT: This operation requires approval by default as it modifies repository history.

Use this tool after reviewing changes with git_diff."""

_PUSH_DESC = """Push commits to a remote repository.

This operation:
- Pushes commits to the specified remote and branch
- Can force push if needed (use with caution)
- Returns number of commits pushed

IMPORTANT: This operation requires approval by default as it modifies remote repository.

Use {{secret:KEY}} syntax for git credentials in environment variables.

Example with credentials:
Set GIT_ASKPASS environment variable to use stored credentials."""

_PULL_DESC = """Pull commits from a remote repository.

This operation:
- Fetches and merges (or rebases) commits from remote
- Returns list of files changed
- Can use rebase instead of merge

Use {{secret:KEY}} syntax for git credentials in environment variables."""

_CHECKOUT_DESC = """Switch to a different branch or commit.

This operation:
- Switches to the specified branch or commit
- Can create a new branch if requested
- Returns previous and current branch

IMPORTANT: This operation requires approval by default as it modifies working tree.

Use this tool to switch between branches or restore files."""

_BRANCH_DESC = """Create or delete a git branch.

This operation:
- Creates a new branch from current HEAD
- Or deletes an existing branch
- Can force delete unmerged branches

IMPORTANT: Branch deletion requires approval by default.

Use git_list_branches to see available branches."""

_LIST_BRANCHES_DESC = """List all branches in a git repository.

Shows:
- Branch names
- Current branch indicator
- Remote branches (if requested)
- Last commit on each branch

Use this tool to see available branches before checkout."""

_STASH_DESC = """Manage git stash (temporary storage for changes).

Supported actions:
- push: Save current changes to stash
- pop: Apply and remove most recent stash
- list: Show all stashes
- drop: Remove a specific stash

Use this tool to temporarily save work in progress."""

_SHOW_DESC = """Show detailed information about a specific commit.

Returns:
- Commit hash and metadata
- Author and date
- Commit message and body
- Full diff of changes
- List of files changed

Use this tool to inspect a specific commit."""

_REMOTE_DESC = """Manage git remote repositories.

Supported actions:
- list: Show all configured remotes
- add: Add a new remote
- remove: Remove an existing remote

Use this tool to configure remote repositories."""


class GitModule(ToolModule):
    MODULE_NAME = "git"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Git Tools"

    @property
    def description(self) -> str:
        return "Git repository management for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.git_tools = GitTools(context.workspace_manager)
        self.context.register_dispatch_target("git", self.git_tools)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/git/status",
            operation_id="git_status",
            summary="Get Git Repository Status",
            description=_STATUS_DESC,
            response_model=GitStatusResponse,
            tags=["git"],
        )
        async def git_status_root(request: GitStatusRequest) -> GitStatusResponse:
            return await self.context.execute_tool(
                "git",
                "status",
                request.model_dump(),
                lambda: self.git_tools.status(
                    repo_path=request.repo_path,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @sub_app.post(
            "/status",
            operation_id="git_status",
            summary="Get Git Repository Status",
            description=_STATUS_DESC,
            response_model=GitStatusResponse,
            tags=["git"],
        )
        async def git_status_sub(request: GitStatusRequest) -> GitStatusResponse:
            return await self.context.execute_tool(
                "git",
                "status",
                request.model_dump(),
                lambda: self.git_tools.status(
                    repo_path=request.repo_path,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @app.post(
            "/api/tools/git/log",
            operation_id="git_log",
            summary="View Git Commit History",
            description=_LOG_DESC,
            response_model=GitLogResponse,
            tags=["git"],
        )
        async def git_log_root(request: GitLogRequest) -> GitLogResponse:
            return await self.context.execute_tool(
                "git",
                "log",
                request.model_dump(),
                lambda: self.git_tools.log(
                    repo_path=request.repo_path,
                    max_count=request.max_count,
                    author=request.author,
                    since=request.since,
                    until=request.until,
                    path=request.path,
                    format=request.format,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @sub_app.post(
            "/log",
            operation_id="git_log",
            summary="View Git Commit History",
            description=_LOG_DESC,
            response_model=GitLogResponse,
            tags=["git"],
        )
        async def git_log_sub(request: GitLogRequest) -> GitLogResponse:
            return await self.context.execute_tool(
                "git",
                "log",
                request.model_dump(),
                lambda: self.git_tools.log(
                    repo_path=request.repo_path,
                    max_count=request.max_count,
                    author=request.author,
                    since=request.since,
                    until=request.until,
                    path=request.path,
                    format=request.format,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @app.post(
            "/api/tools/git/diff",
            operation_id="git_diff",
            summary="View Git File Differences",
            description=_DIFF_DESC,
            response_model=GitDiffResponse,
            tags=["git"],
        )
        async def git_diff_root(request: GitDiffRequest) -> GitDiffResponse:
            return await self.context.execute_tool(
                "git",
                "diff",
                request.model_dump(),
                lambda: self.git_tools.diff(
                    repo_path=request.repo_path,
                    ref=request.ref,
                    path=request.path,
                    staged=request.staged,
                    stat_only=request.stat_only,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @sub_app.post(
            "/diff",
            operation_id="git_diff",
            summary="View Git File Differences",
            description=_DIFF_DESC,
            response_model=GitDiffResponse,
            tags=["git"],
        )
        async def git_diff_sub(request: GitDiffRequest) -> GitDiffResponse:
            return await self.context.execute_tool(
                "git",
                "diff",
                request.model_dump(),
                lambda: self.git_tools.diff(
                    repo_path=request.repo_path,
                    ref=request.ref,
                    path=request.path,
                    staged=request.staged,
                    stat_only=request.stat_only,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @app.post(
            "/api/tools/git/commit",
            operation_id="git_commit",
            summary="Create Git Commit",
            description=_COMMIT_DESC,
            response_model=GitCommitResponse,
            tags=["git"],
        )
        async def git_commit_root(request: GitCommitRequest) -> GitCommitResponse:
            return await self.context.execute_tool(
                "git",
                "commit",
                request.model_dump(),
                lambda: self.git_tools.commit(
                    message=request.message,
                    repo_path=request.repo_path,
                    files=request.files,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=True,
                hitl_reason="Git commit requires approval",
            )

        @sub_app.post(
            "/commit",
            operation_id="git_commit",
            summary="Create Git Commit",
            description=_COMMIT_DESC,
            response_model=GitCommitResponse,
            tags=["git"],
        )
        async def git_commit_sub(request: GitCommitRequest) -> GitCommitResponse:
            return await self.context.execute_tool(
                "git",
                "commit",
                request.model_dump(),
                lambda: self.git_tools.commit(
                    message=request.message,
                    repo_path=request.repo_path,
                    files=request.files,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=True,
                hitl_reason="Git commit requires approval",
            )

        @app.post(
            "/api/tools/git/push",
            operation_id="git_push",
            summary="Push to Git Remote",
            description=_PUSH_DESC,
            response_model=GitPushResponse,
            tags=["git"],
        )
        async def git_push_root(request: GitPushRequest) -> GitPushResponse:
            resolved = self.context.resolve_request_secrets(request)
            return await self.context.execute_tool(
                "git",
                "push",
                request.model_dump(),
                lambda: self.git_tools.push(
                    repo_path=resolved.repo_path,
                    remote=resolved.remote,
                    branch=resolved.branch,
                    force=resolved.force,
                    workspace_dir=resolved.workspace_dir,
                    auth_username=resolved.auth_username,
                    auth_password=resolved.auth_password,
                    auth_env=resolved.auth_env,
                ),
                force_hitl=True,
                hitl_reason="Git push requires approval",
            )

        @sub_app.post(
            "/push",
            operation_id="git_push",
            summary="Push to Git Remote",
            description=_PUSH_DESC,
            response_model=GitPushResponse,
            tags=["git"],
        )
        async def git_push_sub(request: GitPushRequest) -> GitPushResponse:
            resolved = self.context.resolve_request_secrets(request)
            return await self.context.execute_tool(
                "git",
                "push",
                request.model_dump(),
                lambda: self.git_tools.push(
                    repo_path=resolved.repo_path,
                    remote=resolved.remote,
                    branch=resolved.branch,
                    force=resolved.force,
                    workspace_dir=resolved.workspace_dir,
                    auth_username=resolved.auth_username,
                    auth_password=resolved.auth_password,
                    auth_env=resolved.auth_env,
                ),
                force_hitl=True,
                hitl_reason="Git push requires approval",
            )

        @app.post(
            "/api/tools/git/pull",
            operation_id="git_pull",
            summary="Pull from Git Remote",
            description=_PULL_DESC,
            response_model=GitPullResponse,
            tags=["git"],
        )
        async def git_pull_root(request: GitPullRequest) -> GitPullResponse:
            resolved = self.context.resolve_request_secrets(request)
            return await self.context.execute_tool(
                "git",
                "pull",
                request.model_dump(),
                lambda: self.git_tools.pull(
                    repo_path=resolved.repo_path,
                    remote=resolved.remote,
                    branch=resolved.branch,
                    rebase=resolved.rebase,
                    workspace_dir=resolved.workspace_dir,
                    auth_username=resolved.auth_username,
                    auth_password=resolved.auth_password,
                    auth_env=resolved.auth_env,
                ),
                force_hitl=True,
                hitl_reason="Git pull requires approval (can modify local files)",
            )

        @sub_app.post(
            "/pull",
            operation_id="git_pull",
            summary="Pull from Git Remote",
            description=_PULL_DESC,
            response_model=GitPullResponse,
            tags=["git"],
        )
        async def git_pull_sub(request: GitPullRequest) -> GitPullResponse:
            resolved = self.context.resolve_request_secrets(request)
            return await self.context.execute_tool(
                "git",
                "pull",
                request.model_dump(),
                lambda: self.git_tools.pull(
                    repo_path=resolved.repo_path,
                    remote=resolved.remote,
                    branch=resolved.branch,
                    rebase=resolved.rebase,
                    workspace_dir=resolved.workspace_dir,
                    auth_username=resolved.auth_username,
                    auth_password=resolved.auth_password,
                    auth_env=resolved.auth_env,
                ),
                force_hitl=True,
                hitl_reason="Git pull requires approval (can modify local files)",
            )

        @app.post(
            "/api/tools/git/checkout",
            operation_id="git_checkout",
            summary="Git Checkout Branch or Commit",
            description=_CHECKOUT_DESC,
            response_model=GitCheckoutResponse,
            tags=["git"],
        )
        async def git_checkout_root(request: GitCheckoutRequest) -> GitCheckoutResponse:
            return await self.context.execute_tool(
                "git",
                "checkout",
                request.model_dump(),
                lambda: self.git_tools.checkout(
                    target=request.target,
                    repo_path=request.repo_path,
                    create=request.create,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=True,
                hitl_reason="Git checkout requires approval",
            )

        @sub_app.post(
            "/checkout",
            operation_id="git_checkout",
            summary="Git Checkout Branch or Commit",
            description=_CHECKOUT_DESC,
            response_model=GitCheckoutResponse,
            tags=["git"],
        )
        async def git_checkout_sub(request: GitCheckoutRequest) -> GitCheckoutResponse:
            return await self.context.execute_tool(
                "git",
                "checkout",
                request.model_dump(),
                lambda: self.git_tools.checkout(
                    target=request.target,
                    repo_path=request.repo_path,
                    create=request.create,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=True,
                hitl_reason="Git checkout requires approval",
            )

        @app.post(
            "/api/tools/git/branch",
            operation_id="git_branch",
            summary="Create or Delete Git Branch",
            description=_BRANCH_DESC,
            response_model=GitBranchResponse,
            tags=["git"],
        )
        async def git_branch_root(request: GitBranchRequest) -> GitBranchResponse:
            force_hitl = request.action == "delete"
            return await self.context.execute_tool(
                "git",
                "branch",
                request.model_dump(),
                lambda: self.git_tools.branch(
                    name=request.name,
                    repo_path=request.repo_path,
                    action=request.action,
                    force=request.force,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=force_hitl,
                hitl_reason="Git branch deletion requires approval" if force_hitl else None,
            )

        @sub_app.post(
            "/branch",
            operation_id="git_branch",
            summary="Create or Delete Git Branch",
            description=_BRANCH_DESC,
            response_model=GitBranchResponse,
            tags=["git"],
        )
        async def git_branch_sub(request: GitBranchRequest) -> GitBranchResponse:
            force_hitl = request.action == "delete"
            return await self.context.execute_tool(
                "git",
                "branch",
                request.model_dump(),
                lambda: self.git_tools.branch(
                    name=request.name,
                    repo_path=request.repo_path,
                    action=request.action,
                    force=request.force,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=force_hitl,
                hitl_reason="Git branch deletion requires approval" if force_hitl else None,
            )

        @app.post(
            "/api/tools/git/list_branches",
            operation_id="git_list_branches",
            summary="List Git Branches",
            description=_LIST_BRANCHES_DESC,
            response_model=GitListBranchesResponse,
            tags=["git"],
        )
        async def git_list_branches_root(
            request: GitListBranchesRequest,
        ) -> GitListBranchesResponse:
            return await self.context.execute_tool(
                "git",
                "list_branches",
                request.model_dump(),
                lambda: self.git_tools.list_branches(
                    repo_path=request.repo_path,
                    remote=request.remote,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @sub_app.post(
            "/list_branches",
            operation_id="git_list_branches",
            summary="List Git Branches",
            description=_LIST_BRANCHES_DESC,
            response_model=GitListBranchesResponse,
            tags=["git"],
        )
        async def git_list_branches_sub(
            request: GitListBranchesRequest,
        ) -> GitListBranchesResponse:
            return await self.context.execute_tool(
                "git",
                "list_branches",
                request.model_dump(),
                lambda: self.git_tools.list_branches(
                    repo_path=request.repo_path,
                    remote=request.remote,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @app.post(
            "/api/tools/git/stash",
            operation_id="git_stash",
            summary="Git Stash Operations",
            description=_STASH_DESC,
            response_model=GitStashResponse,
            tags=["git"],
        )
        async def git_stash_root(request: GitStashRequest) -> GitStashResponse:
            destructive_actions = {"pop", "drop"}
            force_hitl = request.action in destructive_actions
            hitl_reason = (
                f"Git stash {request.action} requires approval (modifies stash stack)"
                if force_hitl
                else None
            )
            return await self.context.execute_tool(
                "git",
                "stash",
                request.model_dump(),
                lambda: self.git_tools.stash(
                    repo_path=request.repo_path,
                    action=request.action,
                    message=request.message,
                    index=request.index,
                    workspace_dir=request.workspace_dir,
                ),
                force_hitl=force_hitl,
                hitl_reason=hitl_reason,
            )

        @sub_app.post(
            "/stash",
            operation_id="git_stash",
            summary="Git Stash Operations",
            description=_STASH_DESC,
            response_model=GitStashResponse,
            tags=["git"],
        )
        async def git_stash_sub(request: GitStashRequest) -> GitStashResponse:
            return await self.context.execute_tool(
                "git",
                "stash",
                request.model_dump(),
                lambda: self.git_tools.stash(
                    repo_path=request.repo_path,
                    action=request.action,
                    message=request.message,
                    index=request.index,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @app.post(
            "/api/tools/git/show",
            operation_id="git_show",
            summary="Show Git Commit Details",
            description=_SHOW_DESC,
            response_model=GitShowResponse,
            tags=["git"],
        )
        async def git_show_root(request: GitShowRequest) -> GitShowResponse:
            return await self.context.execute_tool(
                "git",
                "show",
                request.model_dump(),
                lambda: self.git_tools.show(
                    repo_path=request.repo_path,
                    ref=request.ref,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @sub_app.post(
            "/show",
            operation_id="git_show",
            summary="Show Git Commit Details",
            description=_SHOW_DESC,
            response_model=GitShowResponse,
            tags=["git"],
        )
        async def git_show_sub(request: GitShowRequest) -> GitShowResponse:
            return await self.context.execute_tool(
                "git",
                "show",
                request.model_dump(),
                lambda: self.git_tools.show(
                    repo_path=request.repo_path,
                    ref=request.ref,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @app.post(
            "/api/tools/git/remote",
            operation_id="git_remote",
            summary="Manage Git Remotes",
            description=_REMOTE_DESC,
            response_model=GitRemoteResponse,
            tags=["git"],
        )
        async def git_remote_root(request: GitRemoteRequest) -> GitRemoteResponse:
            return await self.context.execute_tool(
                "git",
                "remote",
                request.model_dump(),
                lambda: self.git_tools.remote(
                    repo_path=request.repo_path,
                    action=request.action,
                    name=request.name,
                    url=request.url,
                    workspace_dir=request.workspace_dir,
                ),
            )

        @sub_app.post(
            "/remote",
            operation_id="git_remote",
            summary="Manage Git Remotes",
            description=_REMOTE_DESC,
            response_model=GitRemoteResponse,
            tags=["git"],
        )
        async def git_remote_sub(request: GitRemoteRequest) -> GitRemoteResponse:
            return await self.context.execute_tool(
                "git",
                "remote",
                request.model_dump(),
                lambda: self.git_tools.remote(
                    repo_path=request.repo_path,
                    action=request.action,
                    name=request.name,
                    url=request.url,
                    workspace_dir=request.workspace_dir,
                ),
            )
