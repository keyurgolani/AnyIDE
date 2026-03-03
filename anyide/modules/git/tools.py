"""Git repository management tools."""

import os
import asyncio
import re
import tempfile
import stat
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

from anyide.core.workspace import WorkspaceManager
from anyide.logging_config import get_logger

logger = get_logger(__name__)


class GitTools:
    """Git repository management tools."""

    def __init__(self, workspace: WorkspaceManager):
        """Initialize git tools.

        Args:
            workspace: Workspace manager instance
        """
        self.workspace = workspace

    @asynccontextmanager
    async def _create_askpass_script(self, username: str, password: str):
        """Create an ephemeral GIT_ASKPASS script for authentication.

        The script outputs credentials when git requests them.
        It is automatically deleted after use.

        Args:
            username: Git username
            password: Git password/token

        Yields:
            Path to the askpass script
        """
        # Create a temporary script file
        fd, script_path = tempfile.mkstemp(suffix='.sh', prefix='git_askpass_')

        try:
            # Write the askpass script
            # Git calls this script with a prompt argument; we return the password
            script_content = f'''#!/bin/sh
# Ephemeral GIT_ASKPASS script - automatically deleted after use
if echo "$1" | grep -qi "username"; then
    echo '{username}'
else
    echo '{password}'
fi
'''
            with os.fdopen(fd, 'w') as f:
                f.write(script_content)

            # Make the script executable
            os.chmod(script_path, stat.S_IRUSR | stat.S_IXUSR)

            logger.debug("askpass_script_created", path=script_path)
            yield script_path

        finally:
            # Clean up the script file
            try:
                os.unlink(script_path)
                logger.debug("askpass_script_cleaned", path=script_path)
            except OSError as e:
                logger.warning("askpass_script_cleanup_failed", path=script_path, error=str(e))

    async def _run_git_command(
        self,
        args: list[str],
        repo_path: str,
        workspace_dir: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        timeout: int = 60,
    ) -> tuple[str, str, int]:
        """Run a git command in the specified repository.

        Args:
            args: Git command arguments (without 'git' prefix)
            repo_path: Repository path relative to workspace
            workspace_dir: Optional workspace directory override
            env: Optional environment variables
            timeout: Command timeout in seconds

        Returns:
            Tuple of (stdout, stderr, exit_code)

        Raises:
            SecurityError: If path is outside workspace
            FileNotFoundError: If repository doesn't exist
        """
        # Resolve repository path
        resolved_path = self.workspace.resolve_path(repo_path, workspace_dir)

        # Check if path exists
        if not os.path.exists(resolved_path):
            raise FileNotFoundError(f"Repository path does not exist: {repo_path}")

        # Check if it's a git repository
        git_dir = os.path.join(resolved_path, ".git")
        if not os.path.exists(git_dir) and args[0] not in ("init", "clone"):
            raise ValueError(f"Not a git repository: {repo_path}")

        # Build command
        cmd = ["git", "-C", resolved_path] + args

        # Prepare environment
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)

        logger.info("executing_git_command", command=" ".join(cmd), repo_path=resolved_path)

        try:
            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=exec_env,
            )

            # Wait for completion with timeout
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            logger.info(
                "git_command_completed",
                exit_code=exit_code,
                stdout_lines=len(stdout.splitlines()),
                stderr_lines=len(stderr.splitlines()),
            )

            return stdout, stderr, exit_code

        except asyncio.TimeoutError:
            logger.error("git_command_timeout", timeout=timeout)
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            raise TimeoutError(f"Git command timed out after {timeout} seconds")
        except Exception as e:
            logger.error("git_command_error", error=str(e))
            raise
    
    async def status(
        self,
        repo_path: str = ".",
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Get repository status.
        
        Args:
            repo_path: Repository path relative to workspace
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with status information
        """
        # Get status in porcelain format for easier parsing
        stdout, stderr, exit_code = await self._run_git_command(
            ["status", "--porcelain=v2", "--branch"],
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git status failed: {stderr}")
        
        # Parse status output
        branch = "unknown"
        ahead = 0
        behind = 0
        staged = []
        unstaged = []
        untracked = []
        
        for line in stdout.splitlines():
            if line.startswith("# branch.head"):
                branch = line.split()[-1]
            elif line.startswith("# branch.ab"):
                parts = line.split()
                ahead = int(parts[2].replace("+", ""))
                behind = int(parts[3].replace("-", ""))
            elif line.startswith("1 ") or line.startswith("2 "):
                # Changed file
                parts = line.split()
                xy = parts[1]
                path = parts[-1]
                
                if xy[0] != ".":
                    staged.append({"path": path, "status": xy[0]})
                if xy[1] != ".":
                    unstaged.append({"path": path, "status": xy[1]})
            elif line.startswith("? "):
                # Untracked file
                path = line[2:]
                untracked.append(path)
        
        clean = len(staged) == 0 and len(unstaged) == 0 and len(untracked) == 0
        
        return {
            "branch": branch,
            "staged": staged,
            "unstaged": unstaged,
            "untracked": untracked,
            "ahead": ahead,
            "behind": behind,
            "clean": clean,
        }
    
    async def log(
        self,
        repo_path: str = ".",
        max_count: int = 20,
        author: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        path: Optional[str] = None,
        format: str = "medium",
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """View commit history.
        
        Args:
            repo_path: Repository path relative to workspace
            max_count: Maximum number of commits to return
            author: Filter by author
            since: Show commits since date
            until: Show commits until date
            path: Filter by file path
            format: Output format (short, medium, full)
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with commit history
        """
        # Build git log command
        args = [
            "log",
            f"--max-count={max_count}",
            "--pretty=format:%H%n%h%n%an%n%ae%n%at%n%s%n---COMMIT-END---",
            "--numstat",
        ]
        
        if author:
            args.append(f"--author={author}")
        if since:
            args.append(f"--since={since}")
        if until:
            args.append(f"--until={until}")
        if path:
            args.extend(["--", path])
        
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git log failed: {stderr}")
        
        # Parse log output
        commits = []
        lines = stdout.splitlines()
        i = 0
        
        while i < len(lines):
            # Need at least 6 lines for a commit (hash, short_hash, author, email, timestamp, message)
            if i + 5 >= len(lines):
                break
            
            # Check if this looks like the start of a commit (40-char hex hash)
            if len(lines[i]) != 40:
                i += 1
                continue
            
            commit = {
                "hash": lines[i],
                "short_hash": lines[i + 1],
                "author": lines[i + 2],
                "email": lines[i + 3],
                "timestamp": int(lines[i + 4]),
                "date": datetime.fromtimestamp(int(lines[i + 4])).isoformat(),
                "message": lines[i + 5],
                "body": "",
                "files_changed": [],
            }
            
            i += 6
            
            # Parse until we hit the commit end marker
            while i < len(lines) and lines[i] != "---COMMIT-END---":
                line = lines[i]
                if "\t" in line:
                    # File change stats
                    parts = line.split("\t")
                    if len(parts) >= 3:
                        commit["files_changed"].append({
                            "path": parts[2],
                            "additions": int(parts[0]) if parts[0] != "-" else 0,
                            "deletions": int(parts[1]) if parts[1] != "-" else 0,
                        })
                i += 1
            
            commits.append(commit)
            i += 1  # Skip the ---COMMIT-END--- marker
        
        return {
            "commits": commits,
            "total_shown": len(commits),
        }
    
    async def diff(
        self,
        repo_path: str = ".",
        ref: Optional[str] = None,
        path: Optional[str] = None,
        staged: bool = False,
        stat_only: bool = False,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """View file differences.
        
        Args:
            repo_path: Repository path relative to workspace
            ref: Commit/branch to diff against
            path: Specific file to diff
            staged: Show staged changes
            stat_only: Show only statistics
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with diff information
        """
        # Build git diff command
        args = ["diff"]
        
        if staged:
            args.append("--cached")
        if stat_only:
            args.append("--stat")
        if ref:
            args.append(ref)
        if path:
            args.extend(["--", path])
        
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git diff failed: {stderr}")
        
        # Parse diff stats
        files_changed = 0
        insertions = 0
        deletions = 0
        
        if stat_only:
            # Parse stat output
            for line in stdout.splitlines():
                if " file" in line and " changed" in line:
                    match = re.search(r"(\d+) file", line)
                    if match:
                        files_changed = int(match.group(1))
                    match = re.search(r"(\d+) insertion", line)
                    if match:
                        insertions = int(match.group(1))
                    match = re.search(r"(\d+) deletion", line)
                    if match:
                        deletions = int(match.group(1))
        else:
            # Count from diff output
            for line in stdout.splitlines():
                if line.startswith("+++") or line.startswith("---"):
                    if line.startswith("+++ b/"):
                        files_changed += 1
                elif line.startswith("+") and not line.startswith("+++"):
                    insertions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
        
        return {
            "diff": stdout,
            "files_changed": files_changed,
            "insertions": insertions,
            "deletions": deletions,
        }
    
    async def commit(
        self,
        message: str,
        repo_path: str = ".",
        files: Optional[list[str]] = None,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Create a commit.
        
        Args:
            message: Commit message
            repo_path: Repository path relative to workspace
            files: Specific files to stage, or all if empty
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with commit information
        """
        if not message or not message.strip():
            raise ValueError("Commit message cannot be empty")
        
        # Stage files
        if files:
            for file in files:
                await self._run_git_command(
                    ["add", file],
                    repo_path,
                    workspace_dir,
                )
        else:
            await self._run_git_command(
                ["add", "-A"],
                repo_path,
                workspace_dir,
            )
        
        # Create commit
        stdout, stderr, exit_code = await self._run_git_command(
            ["commit", "-m", message],
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git commit failed: {stderr}")
        
        # Get commit hash
        hash_stdout, _, _ = await self._run_git_command(
            ["rev-parse", "HEAD"],
            repo_path,
            workspace_dir,
        )
        commit_hash = hash_stdout.strip()
        
        # Get list of committed files
        files_stdout, _, _ = await self._run_git_command(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit_hash],
            repo_path,
            workspace_dir,
        )
        files_committed = [f for f in files_stdout.splitlines() if f]
        
        return {
            "hash": commit_hash,
            "message": message,
            "files_committed": files_committed,
        }
    
    async def push(
        self,
        repo_path: str = ".",
        remote: str = "origin",
        branch: Optional[str] = None,
        force: bool = False,
        workspace_dir: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
    ) -> dict:
        """Push to remote.

        Args:
            repo_path: Repository path relative to workspace
            remote: Remote name
            branch: Branch name (current branch if not specified)
            force: Force push
            workspace_dir: Optional workspace directory override
            env: Optional environment variables (for credentials)
            auth_username: Git username for authentication
            auth_password: Git password/token for authentication

        Returns:
            Dictionary with push information
        """
        # Get current branch if not specified
        if not branch:
            stdout, _, _ = await self._run_git_command(
                ["branch", "--show-current"],
                repo_path,
                workspace_dir,
            )
            branch = stdout.strip()

        # Build push command
        args = ["push", remote, branch]
        if force:
            args.append("--force")

        # Prepare environment with optional auth
        exec_env = env.copy() if env else {}

        # Use GIT_ASKPASS for authentication if credentials provided
        if auth_username and auth_password:
            async with self._create_askpass_script(auth_username, auth_password) as askpass_path:
                exec_env["GIT_ASKPASS"] = askpass_path

                stdout, stderr, exit_code = await self._run_git_command(
                    args,
                    repo_path,
                    workspace_dir,
                    env=exec_env,
                )
        else:
            # Execute without askpass
            stdout, stderr, exit_code = await self._run_git_command(
                args,
                repo_path,
                workspace_dir,
                env=exec_env,
            )

        if exit_code != 0:
            raise RuntimeError(f"Git push failed: {stderr}")

        # Count commits pushed (rough estimate from output)
        commits_pushed = 0
        for line in (stdout + stderr).splitlines():
            if ".." in line:
                match = re.search(r"(\w+)\.\.(\w+)", line)
                if match:
                    commits_pushed = 1  # At least one commit

        return {
            "remote": remote,
            "branch": branch,
            "commits_pushed": commits_pushed,
            "output": stdout + stderr,
        }
    
    async def pull(
        self,
        repo_path: str = ".",
        remote: str = "origin",
        branch: Optional[str] = None,
        rebase: bool = False,
        workspace_dir: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
    ) -> dict:
        """Pull from remote.

        Args:
            repo_path: Repository path relative to workspace
            remote: Remote name
            branch: Branch name
            rebase: Use rebase instead of merge
            workspace_dir: Optional workspace directory override
            env: Optional environment variables (for credentials)
            auth_username: Git username for authentication
            auth_password: Git password/token for authentication

        Returns:
            Dictionary with pull information
        """
        # Build pull command
        args = ["pull"]
        if rebase:
            args.append("--rebase")
        args.append(remote)
        if branch:
            args.append(branch)

        # Prepare environment with optional auth
        exec_env = env.copy() if env else {}

        # Use GIT_ASKPASS for authentication if credentials provided
        if auth_username and auth_password:
            async with self._create_askpass_script(auth_username, auth_password) as askpass_path:
                exec_env["GIT_ASKPASS"] = askpass_path

                stdout, stderr, exit_code = await self._run_git_command(
                    args,
                    repo_path,
                    workspace_dir,
                    env=exec_env,
                )
        else:
            # Execute without askpass
            stdout, stderr, exit_code = await self._run_git_command(
                args,
                repo_path,
                workspace_dir,
                env=exec_env,
            )

        if exit_code != 0:
            raise RuntimeError(f"Git pull failed: {stderr}")

        # Parse output
        updated = "Already up to date" not in stdout
        commits_received = 0
        files_changed = []

        for line in (stdout + stderr).splitlines():
            if "file changed" in line or "files changed" in line:
                match = re.search(r"(\d+) file", line)
                if match:
                    commits_received = 1  # At least one commit
            if "|" in line and ("+" in line or "-" in line):
                parts = line.split("|")
                if len(parts) >= 1:
                    file_path = parts[0].strip()
                    if file_path:
                        files_changed.append(file_path)

        return {
            "updated": updated,
            "commits_received": commits_received,
            "files_changed": files_changed,
            "output": stdout + stderr,
        }
    
    async def checkout(
        self,
        target: str,
        repo_path: str = ".",
        create: bool = False,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Switch branches or restore files.
        
        Args:
            target: Branch name or commit hash
            repo_path: Repository path relative to workspace
            create: Create new branch
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with checkout information
        """
        # Get current branch
        stdout, _, _ = await self._run_git_command(
            ["branch", "--show-current"],
            repo_path,
            workspace_dir,
        )
        previous_branch = stdout.strip()
        
        # Build checkout command
        args = ["checkout"]
        if create:
            args.append("-b")
        args.append(target)
        
        # Execute checkout
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git checkout failed: {stderr}")
        
        return {
            "branch": target,
            "previous_branch": previous_branch,
            "output": stdout + stderr,
        }
    
    async def branch(
        self,
        name: str,
        repo_path: str = ".",
        action: str = "create",
        force: bool = False,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Create or delete branches.
        
        Args:
            name: Branch name
            repo_path: Repository path relative to workspace
            action: Action to perform (create or delete)
            force: Force operation
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with branch information
        """
        if action not in ("create", "delete"):
            raise ValueError(f"Invalid action: {action}. Must be 'create' or 'delete'")
        
        # Build branch command
        if action == "create":
            args = ["branch", name]
        else:
            args = ["branch", "-d" if not force else "-D", name]
        
        # Execute branch command
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git branch {action} failed: {stderr}")
        
        return {
            "branch": name,
            "action": action,
            "output": stdout + stderr,
        }
    
    async def list_branches(
        self,
        repo_path: str = ".",
        remote: bool = False,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """List branches.
        
        Args:
            repo_path: Repository path relative to workspace
            remote: Include remote branches
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with branch list
        """
        # Build branch command
        args = ["branch", "-v"]
        if remote:
            args.append("-a")
        
        # Execute branch command
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git branch list failed: {stderr}")
        
        # Parse branch list
        branches = []
        for line in stdout.splitlines():
            if not line.strip():
                continue
            
            is_current = line.startswith("*")
            line = line.lstrip("* ").strip()
            
            parts = line.split(None, 2)
            if len(parts) >= 2:
                name = parts[0]
                last_commit = parts[1]
                is_remote = name.startswith("remotes/")
                
                branches.append({
                    "name": name,
                    "current": is_current,
                    "remote": is_remote,
                    "last_commit": last_commit,
                })
        
        return {
            "branches": branches,
        }
    
    async def stash(
        self,
        repo_path: str = ".",
        action: str = "push",
        message: Optional[str] = None,
        index: Optional[int] = None,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Stash changes.
        
        Args:
            repo_path: Repository path relative to workspace
            action: Action to perform (push, pop, list, drop)
            message: Stash message (for push)
            index: Stash index (for pop/drop)
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with stash information
        """
        if action not in ("push", "pop", "list", "drop"):
            raise ValueError(f"Invalid action: {action}")
        
        # Build stash command
        args = ["stash", action]
        if action == "push" and message:
            args.extend(["-m", message])
        if action in ("pop", "drop") and index is not None:
            args.append(f"stash@{{{index}}}")
        
        # Execute stash command
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0 and action != "list":
            raise RuntimeError(f"Git stash {action} failed: {stderr}")
        
        # Parse stash list if action is list
        stashes = []
        if action == "list":
            for line in stdout.splitlines():
                match = re.match(r"stash@\{(\d+)\}: (.+)", line)
                if match:
                    stashes.append({
                        "index": int(match.group(1)),
                        "message": match.group(2),
                    })
        
        return {
            "action": action,
            "stashes": stashes if action == "list" else None,
            "output": stdout + stderr,
        }
    
    async def show(
        self,
        repo_path: str = ".",
        ref: str = "HEAD",
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Show commit details.
        
        Args:
            repo_path: Repository path relative to workspace
            ref: Commit reference
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with commit details
        """
        # Get commit info
        stdout, stderr, exit_code = await self._run_git_command(
            ["show", "--pretty=format:%H%n%an%n%ae%n%at%n%s%n%b", "--stat", ref],
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git show failed: {stderr}")
        
        # Parse output
        lines = stdout.splitlines()
        if len(lines) < 5:
            raise RuntimeError("Invalid git show output")
        
        commit_hash = lines[0]
        author = lines[1]
        email = lines[2]
        timestamp = int(lines[3])
        date = datetime.fromtimestamp(timestamp).isoformat()
        message = lines[4]
        
        # Find body and diff
        body_lines = []
        files_changed = []
        in_body = True
        
        for i in range(5, len(lines)):
            line = lines[i]
            if "|" in line and ("+" in line or "-" in line):
                in_body = False
                parts = line.split("|")
                if len(parts) >= 1:
                    file_path = parts[0].strip()
                    if file_path:
                        files_changed.append(file_path)
            elif in_body and line.strip():
                body_lines.append(line)
        
        body = "\n".join(body_lines)
        
        # Get full diff
        diff_stdout, _, _ = await self._run_git_command(
            ["show", ref],
            repo_path,
            workspace_dir,
        )
        
        return {
            "hash": commit_hash,
            "author": f"{author} <{email}>",
            "date": date,
            "message": message,
            "body": body,
            "diff": diff_stdout,
            "files_changed": files_changed,
        }
    
    async def remote(
        self,
        repo_path: str = ".",
        action: str = "list",
        name: Optional[str] = None,
        url: Optional[str] = None,
        workspace_dir: Optional[str] = None,
    ) -> dict:
        """Manage remotes.
        
        Args:
            repo_path: Repository path relative to workspace
            action: Action to perform (list, add, remove)
            name: Remote name
            url: Remote URL
            workspace_dir: Optional workspace directory override
            
        Returns:
            Dictionary with remote information
        """
        if action not in ("list", "add", "remove"):
            raise ValueError(f"Invalid action: {action}")
        
        # Build remote command
        args = ["remote"]
        if action == "list":
            args.append("-v")
        elif action == "add":
            if not name or not url:
                raise ValueError("Name and URL required for add action")
            args.extend(["add", name, url])
        elif action == "remove":
            if not name:
                raise ValueError("Name required for remove action")
            args.extend(["remove", name])
        
        # Execute remote command
        stdout, stderr, exit_code = await self._run_git_command(
            args,
            repo_path,
            workspace_dir,
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Git remote {action} failed: {stderr}")
        
        # Parse remote list
        remotes = []
        if action == "list":
            remote_dict = {}
            for line in stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    remote_name = parts[0]
                    remote_url = parts[1]
                    remote_type = parts[2].strip("()") if len(parts) >= 3 else "fetch"
                    
                    if remote_name not in remote_dict:
                        remote_dict[remote_name] = {"name": remote_name, "fetch_url": None, "push_url": None}
                    
                    if remote_type == "fetch":
                        remote_dict[remote_name]["fetch_url"] = remote_url
                    elif remote_type == "push":
                        remote_dict[remote_name]["push_url"] = remote_url
            
            remotes = list(remote_dict.values())
        
        return {
            "remotes": remotes,
            "action": action,
            "output": stdout + stderr if action != "list" else None,
        }
