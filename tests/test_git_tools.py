"""Tests for git tools."""

import os
import pytest
import tempfile
import shutil
from pathlib import Path

from anyide.modules.git.tools import GitTools
from anyide.core.workspace import WorkspaceManager


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def workspace_manager(temp_workspace):
    """Create a workspace manager with temp directory."""
    return WorkspaceManager(temp_workspace)


@pytest.fixture
def git_tools(workspace_manager):
    """Create git tools instance."""
    return GitTools(workspace_manager)


@pytest.fixture
async def git_repo(temp_workspace):
    """Create a test git repository."""
    repo_path = os.path.join(temp_workspace, "test_repo")
    os.makedirs(repo_path)
    
    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
    
    # Create initial commit
    test_file = os.path.join(repo_path, "README.md")
    with open(test_file, "w") as f:
        f.write("# Test Repository\n")
    
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)
    
    return "test_repo"


@pytest.mark.asyncio
async def test_git_status_clean(git_tools, git_repo):
    """Test git status on clean repository."""
    result = await git_tools.status(repo_path=git_repo)
    
    assert result["clean"] is True
    assert len(result["staged"]) == 0
    assert len(result["unstaged"]) == 0
    assert len(result["untracked"]) == 0
    assert "branch" in result


@pytest.mark.asyncio
async def test_git_status_with_changes(git_tools, git_repo, temp_workspace):
    """Test git status with uncommitted changes."""
    # Create a new file
    repo_path = os.path.join(temp_workspace, git_repo)
    new_file = os.path.join(repo_path, "new_file.txt")
    with open(new_file, "w") as f:
        f.write("New content\n")
    
    result = await git_tools.status(repo_path=git_repo)
    
    assert result["clean"] is False
    assert len(result["untracked"]) == 1
    assert "new_file.txt" in result["untracked"]


@pytest.mark.asyncio
async def test_git_status_with_staged_changes(git_tools, git_repo, temp_workspace):
    """Test git status with staged changes."""
    # Create and stage a new file
    repo_path = os.path.join(temp_workspace, git_repo)
    new_file = os.path.join(repo_path, "staged_file.txt")
    with open(new_file, "w") as f:
        f.write("Staged content\n")
    
    import subprocess
    subprocess.run(["git", "add", "staged_file.txt"], cwd=repo_path, check=True)
    
    result = await git_tools.status(repo_path=git_repo)
    
    assert result["clean"] is False
    assert len(result["staged"]) == 1


@pytest.mark.asyncio
async def test_git_log(git_tools, git_repo):
    """Test git log."""
    result = await git_tools.log(repo_path=git_repo, max_count=10)
    
    assert "commits" in result
    assert len(result["commits"]) >= 1
    assert result["total_shown"] >= 1
    
    # Check first commit structure
    commit = result["commits"][0]
    assert "hash" in commit
    assert "short_hash" in commit
    assert "author" in commit
    assert "message" in commit
    assert "date" in commit


@pytest.mark.asyncio
async def test_git_log_with_filters(git_tools, git_repo):
    """Test git log with filters."""
    result = await git_tools.log(
        repo_path=git_repo,
        max_count=5,
        author="Test User",
    )
    
    assert "commits" in result
    assert len(result["commits"]) >= 1


@pytest.mark.asyncio
async def test_git_diff_no_changes(git_tools, git_repo):
    """Test git diff with no changes."""
    result = await git_tools.diff(repo_path=git_repo)
    
    assert "diff" in result
    assert result["files_changed"] == 0
    assert result["insertions"] == 0
    assert result["deletions"] == 0


@pytest.mark.asyncio
async def test_git_diff_with_changes(git_tools, git_repo, temp_workspace):
    """Test git diff with changes."""
    # Modify a file
    repo_path = os.path.join(temp_workspace, git_repo)
    readme_file = os.path.join(repo_path, "README.md")
    with open(readme_file, "a") as f:
        f.write("\nNew line added\n")
    
    result = await git_tools.diff(repo_path=git_repo)
    
    assert "diff" in result
    assert result["files_changed"] >= 1
    assert result["insertions"] >= 1


@pytest.mark.asyncio
async def test_git_commit(git_tools, git_repo, temp_workspace):
    """Test git commit."""
    # Create a new file
    repo_path = os.path.join(temp_workspace, git_repo)
    new_file = os.path.join(repo_path, "commit_test.txt")
    with open(new_file, "w") as f:
        f.write("Test commit\n")
    
    result = await git_tools.commit(
        message="Test commit message",
        repo_path=git_repo,
    )
    
    assert "hash" in result
    assert result["message"] == "Test commit message"
    assert "files_committed" in result
    assert len(result["files_committed"]) >= 1


@pytest.mark.asyncio
async def test_git_commit_specific_files(git_tools, git_repo, temp_workspace):
    """Test git commit with specific files."""
    # Create multiple files
    repo_path = os.path.join(temp_workspace, git_repo)
    file1 = os.path.join(repo_path, "file1.txt")
    file2 = os.path.join(repo_path, "file2.txt")
    
    with open(file1, "w") as f:
        f.write("File 1\n")
    with open(file2, "w") as f:
        f.write("File 2\n")
    
    # Commit only file1
    result = await git_tools.commit(
        message="Commit file1 only",
        repo_path=git_repo,
        files=["file1.txt"],
    )
    
    assert "hash" in result
    assert "file1.txt" in result["files_committed"]


@pytest.mark.asyncio
async def test_git_list_branches(git_tools, git_repo):
    """Test git list branches."""
    result = await git_tools.list_branches(repo_path=git_repo)
    
    assert "branches" in result
    assert len(result["branches"]) >= 1
    
    # Check branch structure
    branch = result["branches"][0]
    assert "name" in branch
    assert "current" in branch


@pytest.mark.asyncio
async def test_git_branch_create(git_tools, git_repo):
    """Test git branch creation."""
    result = await git_tools.branch(
        name="test-branch",
        repo_path=git_repo,
        action="create",
    )
    
    assert result["branch"] == "test-branch"
    assert result["action"] == "create"
    
    # Verify branch was created
    branches = await git_tools.list_branches(repo_path=git_repo)
    branch_names = [b["name"] for b in branches["branches"]]
    assert "test-branch" in branch_names


@pytest.mark.asyncio
async def test_git_branch_delete(git_tools, git_repo):
    """Test git branch deletion."""
    # Create a branch first
    await git_tools.branch(
        name="delete-me",
        repo_path=git_repo,
        action="create",
    )
    
    # Delete it
    result = await git_tools.branch(
        name="delete-me",
        repo_path=git_repo,
        action="delete",
    )
    
    assert result["branch"] == "delete-me"
    assert result["action"] == "delete"


@pytest.mark.asyncio
async def test_git_checkout(git_tools, git_repo):
    """Test git checkout."""
    # Create a new branch
    await git_tools.branch(
        name="checkout-test",
        repo_path=git_repo,
        action="create",
    )
    
    # Checkout the branch
    result = await git_tools.checkout(
        target="checkout-test",
        repo_path=git_repo,
    )
    
    assert result["branch"] == "checkout-test"
    assert "previous_branch" in result


@pytest.mark.asyncio
async def test_git_checkout_create(git_tools, git_repo):
    """Test git checkout with branch creation."""
    result = await git_tools.checkout(
        target="new-branch",
        repo_path=git_repo,
        create=True,
    )
    
    assert result["branch"] == "new-branch"
    
    # Verify branch was created
    branches = await git_tools.list_branches(repo_path=git_repo)
    branch_names = [b["name"] for b in branches["branches"]]
    assert "new-branch" in branch_names


@pytest.mark.asyncio
async def test_git_stash_push(git_tools, git_repo, temp_workspace):
    """Test git stash push."""
    # Create changes
    repo_path = os.path.join(temp_workspace, git_repo)
    new_file = os.path.join(repo_path, "stash_test.txt")
    with open(new_file, "w") as f:
        f.write("Stash this\n")
    
    result = await git_tools.stash(
        repo_path=git_repo,
        action="push",
        message="Test stash",
    )
    
    assert result["action"] == "push"


@pytest.mark.asyncio
async def test_git_stash_list(git_tools, git_repo, temp_workspace):
    """Test git stash list."""
    # Create and stash changes
    repo_path = os.path.join(temp_workspace, git_repo)
    new_file = os.path.join(repo_path, "stash_list_test.txt")
    with open(new_file, "w") as f:
        f.write("Stash this\n")
    
    await git_tools.stash(
        repo_path=git_repo,
        action="push",
        message="Test stash for list",
    )
    
    result = await git_tools.stash(
        repo_path=git_repo,
        action="list",
    )
    
    assert result["action"] == "list"
    assert result["stashes"] is not None


@pytest.mark.asyncio
async def test_git_show(git_tools, git_repo):
    """Test git show."""
    result = await git_tools.show(
        repo_path=git_repo,
        ref="HEAD",
    )
    
    assert "hash" in result
    assert "author" in result
    assert "date" in result
    assert "message" in result
    assert "diff" in result


@pytest.mark.asyncio
async def test_git_remote_list(git_tools, git_repo):
    """Test git remote list."""
    result = await git_tools.remote(
        repo_path=git_repo,
        action="list",
    )
    
    assert "remotes" in result
    assert result["action"] == "list"


@pytest.mark.asyncio
async def test_git_remote_add(git_tools, git_repo):
    """Test git remote add."""
    result = await git_tools.remote(
        repo_path=git_repo,
        action="add",
        name="test-remote",
        url="https://github.com/test/repo.git",
    )
    
    assert result["action"] == "add"
    
    # Verify remote was added
    remotes = await git_tools.remote(repo_path=git_repo, action="list")
    remote_names = [r["name"] for r in remotes["remotes"]]
    assert "test-remote" in remote_names


@pytest.mark.asyncio
async def test_git_remote_remove(git_tools, git_repo):
    """Test git remote remove."""
    # Add a remote first
    await git_tools.remote(
        repo_path=git_repo,
        action="add",
        name="remove-me",
        url="https://github.com/test/repo.git",
    )
    
    # Remove it
    result = await git_tools.remote(
        repo_path=git_repo,
        action="remove",
        name="remove-me",
    )
    
    assert result["action"] == "remove"


@pytest.mark.asyncio
async def test_git_status_not_a_repo(git_tools, temp_workspace):
    """Test git status on non-repository."""
    # Create a directory that's not a git repo
    non_repo = os.path.join(temp_workspace, "not_a_repo")
    os.makedirs(non_repo)
    
    with pytest.raises(ValueError, match="Not a git repository"):
        await git_tools.status(repo_path="not_a_repo")


@pytest.mark.asyncio
async def test_git_commit_empty_message(git_tools, git_repo):
    """Test git commit with empty message."""
    with pytest.raises(ValueError, match="Commit message cannot be empty"):
        await git_tools.commit(
            message="",
            repo_path=git_repo,
        )


@pytest.mark.asyncio
async def test_git_branch_invalid_action(git_tools, git_repo):
    """Test git branch with invalid action."""
    with pytest.raises(ValueError, match="Invalid action"):
        await git_tools.branch(
            name="test",
            repo_path=git_repo,
            action="invalid",
        )


@pytest.mark.asyncio
async def test_git_stash_invalid_action(git_tools, git_repo):
    """Test git stash with invalid action."""
    with pytest.raises(ValueError, match="Invalid action"):
        await git_tools.stash(
            repo_path=git_repo,
            action="invalid",
        )


@pytest.mark.asyncio
async def test_git_remote_invalid_action(git_tools, git_repo):
    """Test git remote with invalid action."""
    with pytest.raises(ValueError, match="Invalid action"):
        await git_tools.remote(
            repo_path=git_repo,
            action="invalid",
        )


@pytest.mark.asyncio
async def test_git_diff_stat_only(git_tools, git_repo, temp_workspace):
    """Test git diff with stat_only flag."""
    # Modify a file
    repo_path = os.path.join(temp_workspace, git_repo)
    readme_file = os.path.join(repo_path, "README.md")
    with open(readme_file, "a") as f:
        f.write("\nStat test line\n")
    
    result = await git_tools.diff(repo_path=git_repo, stat_only=True)
    
    assert "diff" in result
    assert result["files_changed"] >= 1


@pytest.mark.asyncio
async def test_git_log_with_path_filter(git_tools, git_repo, temp_workspace):
    """Test git log with path filter."""
    result = await git_tools.log(
        repo_path=git_repo,
        path="README.md",
    )

    assert "commits" in result
    assert len(result["commits"]) >= 1


# ============================================================================
# GIT_ASKPASS Authentication Tests (P2-0.6)
# ============================================================================

import tempfile
import os


class TestGitAskpass:
    """Test GIT_ASKPASS credential helper functionality."""

    @pytest.mark.asyncio
    async def test_askpass_script_created_and_cleaned_up(self, git_tools):
        """Test that the askpass script is created and properly cleaned up."""
        username = "test_user"
        password = "test_token"

        # Track the script path
        script_path = None

        async with git_tools._create_askpass_script(username, password) as path:
            script_path = path
            # Verify script exists and is executable
            assert os.path.exists(script_path)
            assert os.access(script_path, os.X_OK)

            # Verify script content
            with open(script_path, 'r') as f:
                content = f.read()
                assert username in content
                assert password in content
                assert "#!/bin/sh" in content

        # Verify script is cleaned up
        assert not os.path.exists(script_path), "Askpass script should be deleted after use"

    @pytest.mark.asyncio
    async def test_askpass_script_outputs_username(self, git_tools):
        """Test that askpass script outputs username when prompted."""
        import subprocess

        username = "test_user"
        password = "test_token"

        async with git_tools._create_askpass_script(username, password) as script_path:
            # Simulate git asking for username
            result = subprocess.run(
                ["sh", script_path, "Username for 'https://github.com':"],
                capture_output=True,
                text=True
            )
            assert result.stdout.strip() == username

    @pytest.mark.asyncio
    async def test_askpass_script_outputs_password(self, git_tools):
        """Test that askpass script outputs password when prompted."""
        import subprocess

        username = "test_user"
        password = "ghp_test_token_secret"

        async with git_tools._create_askpass_script(username, password) as script_path:
            # Simulate git asking for password
            result = subprocess.run(
                ["sh", script_path, "Password for 'https://github.com':"],
                capture_output=True,
                text=True
            )
            assert result.stdout.strip() == password

    @pytest.mark.asyncio
    async def test_askpass_cleanup_on_exception(self, git_tools):
        """Test that askpass script is cleaned up even if an exception occurs."""
        username = "test_user"
        password = "test_token"

        script_path = None
        try:
            async with git_tools._create_askpass_script(username, password) as path:
                script_path = path
                raise RuntimeError("Simulated error during git operation")
        except RuntimeError:
            pass

        # Verify script is still cleaned up despite the exception
        assert not os.path.exists(script_path), "Askpass script should be deleted even on exception"

    @pytest.mark.asyncio
    async def test_push_with_auth_credentials(self, git_tools, git_repo):
        """Test that push accepts auth credentials (doesn't actually push without remote)."""
        # This test verifies the parameter passing works
        # We can't test actual push without a real remote
        import inspect
        sig = inspect.signature(git_tools.push)
        params = sig.parameters

        assert "auth_username" in params
        assert "auth_password" in params
        assert params["auth_username"].default is None
        assert params["auth_password"].default is None

    @pytest.mark.asyncio
    async def test_pull_with_auth_credentials(self, git_tools, git_repo):
        """Test that pull accepts auth credentials."""
        import inspect
        sig = inspect.signature(git_tools.pull)
        params = sig.parameters

        assert "auth_username" in params
        assert "auth_password" in params
        assert params["auth_username"].default is None
        assert params["auth_password"].default is None
