# AnyIDE Tool Catalog

Auto-generated documentation for all available tools.

**Generated from:** OpenAPI spec

**Version:** 0.1.0

---

## DOCKER Tools

### action

**Endpoint:** `POST /api/tools/docker/action`


**Summary:** Control Docker Container


**Description:**

Perform control actions on a Docker container.

This tool allows you to manage container lifecycle. Available actions:
- start: Start a stopped container
- stop: Stop a running container (graceful shutdown)
- restart: Restart a container (stop + start)
- pause: Pause a running container (freeze processes)
- unpause: Resume a paused container

Use this tool when you need to:
- Start/stop services
- Restart containers after configuration changes
- Pause containers to save resources
- Recover from container issues

IMPORTANT: This tool requires human approval (HITL) by default for safety.
Container control actions can affect running services.

The tool returns the previous and new status of the container.

Examples:
- Start container: {"container": "nginx", "action": "start"}
- Stop container: {"container": "nginx", "action": "stop", "timeout": 30}
- Restart container: {"container": "nginx", "action": "restart"}
- Pause container: {"container": "nginx", "action": "pause"}


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### inspect

**Endpoint:** `POST /api/tools/docker/inspect`


**Summary:** Inspect Docker Container


**Description:**

Get detailed information about a specific Docker container.

This tool provides comprehensive details about a container including:
- Configuration (environment variables, command, entrypoint, labels)
- Network settings (IP address, ports, networks)
- Volume mounts
- Container state (running, paused, exit code, etc.)

Use this tool when you need to:
- Debug container configuration issues
- Check environment variables
- View port mappings
- Inspect volume mounts
- Get detailed container state

Provide either the container name or ID.

Example: {"container": "nginx"} or {"container": "a1b2c3d4"}


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### list

**Endpoint:** `POST /api/tools/docker/list`


**Summary:** List Docker Containers


**Description:**

List Docker containers on the host system.

This tool allows you to view all containers (running and stopped) managed by Docker.
You can filter by container name or status.

Use this tool when you need to:
- See what containers are running
- Check container status
- Find a specific container by name
- Monitor container health

The tool returns container ID, name, image, status, ports, and creation time.

Examples:
- List all containers: {"all": true}
- List only running containers: {"all": false}
- Filter by name: {"filter_name": "nginx"}
- Filter by status: {"filter_status": "running"}


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### logs

**Endpoint:** `POST /api/tools/docker/logs`


**Summary:** Get Docker Container Logs


**Description:**

Retrieve logs from a Docker container.

This tool fetches stdout and stderr output from a container. You can control:
- Number of lines to retrieve (tail)
- Time range (since timestamp)

Use this tool when you need to:
- Debug application issues
- Monitor container output
- Check error messages
- Investigate crashes

The logs are returned as a single string with newlines preserved.

Examples:
- Get last 100 lines: {"container": "nginx", "tail": 100}
- Get last 50 lines: {"container": "nginx", "tail": 50}
- Get logs since timestamp: {"container": "nginx", "since": "2024-01-01T00:00:00"}

Note: The 'follow' parameter is not recommended for API calls and defaults to false.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## FS Tools

### list

**Endpoint:** `POST /api/tools/fs/list`


**Summary:** List Directory


**Description:**

List contents of a directory.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided.

Use this tool when you need to:
- Browse directory contents
- Find files in a directory
- Explore project structure
- Check if files exist

Optional: path (default: '.'), workspace_dir, recursive, max_depth, include_hidden, pattern

Supports glob patterns like '*.py', 'test_*.txt' for filtering.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### read

**Endpoint:** `POST /api/tools/fs/read`


**Summary:** Read File


**Description:**

Read the contents of a file at the specified path.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided. Returns the file contents
as text.

Use this tool when you need to:
- Examine file contents before making changes
- Read configuration files
- Inspect source code
- Check log files

Required: path (relative to workspace directory)
Optional: encoding, max_lines (for large files), line_start/line_end (for specific sections)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### search

**Endpoint:** `POST /api/tools/fs/search`


**Summary:** Search Files


**Description:**

Search for files by name or content.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided.

Use this tool when you need to:
- Find files by name
- Search file contents
- Locate specific code or text
- Discover files matching patterns

Required: query
Optional: path (default: '.'), workspace_dir, search_type ('filename', 'content', 'both'),
         regex, max_results, include_content_preview

Supports both simple text search and regex patterns.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### write

**Endpoint:** `POST /api/tools/fs/write`


**Summary:** Write File


**Description:**

Write content to a file at the specified path.

The path is relative to the workspace directory unless an absolute
path within the workspace is provided.

Use this tool when you need to:
- Create new files
- Update existing files
- Append content to files
- Save generated content

Required: path, content
Optional: mode ('create', 'overwrite', 'append'), workspace_dir, create_dirs, encoding

Note: Writing to configuration files (*.conf, *.env, *.yaml, *.yml) requires approval.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## GIT Tools

### branch

**Endpoint:** `POST /api/tools/git/branch`


**Summary:** Create or Delete Git Branch


**Description:**

Create or delete a git branch.

This operation:
- Creates a new branch from current HEAD
- Or deletes an existing branch
- Can force delete unmerged branches

IMPORTANT: Branch deletion requires approval by default.

Use git_list_branches to see available branches.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### checkout

**Endpoint:** `POST /api/tools/git/checkout`


**Summary:** Git Checkout Branch or Commit


**Description:**

Switch to a different branch or commit.

This operation:
- Switches to the specified branch or commit
- Can create a new branch if requested
- Returns previous and current branch

IMPORTANT: This operation requires approval by default as it modifies working tree.

Use this tool to switch between branches or restore files.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### commit

**Endpoint:** `POST /api/tools/git/commit`


**Summary:** Create Git Commit


**Description:**

Create a git commit with the specified message.

This operation:
- Stages specified files (or all changes if none specified)
- Creates a commit with the provided message
- Returns the commit hash and list of files committed

IMPORTANT: This operation requires approval by default as it modifies repository history.

Use this tool after reviewing changes with git_diff.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### diff

**Endpoint:** `POST /api/tools/git/diff`


**Summary:** View Git File Differences


**Description:**

View file differences in a git repository.

Can show:
- Unstaged changes (default)
- Staged changes (--cached)
- Diff against specific commit/branch
- Statistics only (files changed, insertions, deletions)

Use this tool to review changes before committing.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### list_branches

**Endpoint:** `POST /api/tools/git/list_branches`


**Summary:** List Git Branches


**Description:**

List all branches in a git repository.

Shows:
- Branch names
- Current branch indicator
- Remote branches (if requested)
- Last commit on each branch

Use this tool to see available branches before checkout.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### log

**Endpoint:** `POST /api/tools/git/log`


**Summary:** View Git Commit History


**Description:**

View the commit history of a git repository.

Supports filtering by:
- Author
- Date range (since/until)
- File path
- Maximum number of commits

Use this tool to review recent changes or find specific commits.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### pull

**Endpoint:** `POST /api/tools/git/pull`


**Summary:** Pull from Git Remote


**Description:**

Pull commits from a remote repository.

This operation:
- Fetches and merges (or rebases) commits from remote
- Returns list of files changed
- Can use rebase instead of merge

Use {{secret:KEY}} syntax for git credentials in environment variables.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### push

**Endpoint:** `POST /api/tools/git/push`


**Summary:** Push to Git Remote


**Description:**

Push commits to a remote repository.

This operation:
- Pushes commits to the specified remote and branch
- Can force push if needed (use with caution)
- Returns number of commits pushed

IMPORTANT: This operation requires approval by default as it modifies remote repository.

Use {{secret:KEY}} syntax for git credentials in environment variables.

Example with credentials:
Set GIT_ASKPASS environment variable to use stored credentials.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### remote

**Endpoint:** `POST /api/tools/git/remote`


**Summary:** Manage Git Remotes


**Description:**

Manage git remote repositories.

Supported actions:
- list: Show all configured remotes
- add: Add a new remote
- remove: Remove an existing remote

Use this tool to configure remote repositories.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### show

**Endpoint:** `POST /api/tools/git/show`


**Summary:** Show Git Commit Details


**Description:**

Show detailed information about a specific commit.

Returns:
- Commit hash and metadata
- Author and date
- Commit message and body
- Full diff of changes
- List of files changed

Use this tool to inspect a specific commit.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### stash

**Endpoint:** `POST /api/tools/git/stash`


**Summary:** Git Stash Operations


**Description:**

Manage git stash (temporary storage for changes).

Supported actions:
- push: Save current changes to stash
- pop: Apply and remove most recent stash
- list: Show all stashes
- drop: Remove a specific stash

Use this tool to temporarily save work in progress.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### status

**Endpoint:** `POST /api/tools/git/status`


**Summary:** Get Git Repository Status


**Description:**

Get the current status of a git repository.

Shows:
- Current branch
- Staged files
- Unstaged changes
- Untracked files
- Commits ahead/behind remote

Use this tool to check the state of a repository before making changes.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## HTTP Tools

### request

**Endpoint:** `POST /api/tools/http/request`


**Summary:** Make HTTP Request


**Description:**

Make an HTTP request to an external URL.

Supported methods: GET, POST, PUT, PATCH, DELETE, HEAD

Use {{secret:KEY}} syntax in headers or body values to inject secrets
without exposing them in the request parameters or audit logs.

Security protections:
- Private/reserved IP addresses are blocked (SSRF protection)
- Cloud metadata endpoints (169.254.169.254, etc.) are blocked
- Domain allowlist/blocklist enforced from configuration
- Response body is truncated at the configured size limit

Required: url
Optional: method (default: GET), headers, body, json_body, timeout (max 120s), follow_redirects


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## LANGUAGE Tools

### apply_patch

**Endpoint:** `POST /api/tools/language/apply_patch`


**Summary:** Apply Function-Anchored Patch


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### create_file

**Endpoint:** `POST /api/tools/language/create_file`


**Summary:** Create Code File with Validation


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### diff

**Endpoint:** `POST /api/tools/language/diff`


**Summary:** Create Language-Aware Diff


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### index

**Endpoint:** `POST /api/tools/language/index`


**Summary:** Index Workspace Symbols


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### read_file

**Endpoint:** `POST /api/tools/language/read_file`


**Summary:** Read File with Structure Awareness


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### reference_graph

**Endpoint:** `POST /api/tools/language/reference_graph`


**Summary:** Build Function Reference Graph


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### search_symbols

**Endpoint:** `POST /api/tools/language/search_symbols`


**Summary:** Search Indexed Symbols


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### skeleton

**Endpoint:** `POST /api/tools/language/skeleton`


**Summary:** Get File Skeleton


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### validate

**Endpoint:** `POST /api/tools/language/validate`


**Summary:** Validate Syntax and Linting


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## MEMORY Tools

### ancestors

**Endpoint:** `POST /api/tools/memory/ancestors`


**Summary:** Get Ancestor Nodes


**Description:**

Traverse parent_of edges upward to find all ancestor nodes (recursive CTE).

Walks the graph from the given node toward root nodes by following parent_of edges in reverse.
Stops when max_depth is reached or no more ancestors exist.

Required: id
Optional: max_depth (default: 10)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### children

**Endpoint:** `POST /api/tools/memory/children`


**Summary:** Get Child Nodes


**Description:**

Get the immediate child nodes connected via parent_of edges.

In the graph, "A parent_of B" means A→B where A is the parent.
This tool returns all B where A→B with relation='parent_of'.

Required: id


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### delete

**Endpoint:** `POST /api/tools/memory/delete`


**Summary:** Delete Knowledge Node


**Description:**

Delete a memory node and all its edges.

With cascade=false (default), lists nodes that would become orphaned (their only parent was this node)
but does not delete them. With cascade=true, also deletes those orphaned children.

IMPORTANT: This operation requires human approval by default.

Required: id
Optional: cascade (default: false)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### get

**Endpoint:** `POST /api/tools/memory/get`


**Summary:** Retrieve Knowledge Node


**Description:**

Retrieve a memory node by its ID along with its relationships.

Returns the full node content and metadata, plus connected edges and neighbor summaries.

Required: id
Optional: include_relations (default: true), depth (default: 1 — immediate neighbors only)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### link

**Endpoint:** `POST /api/tools/memory/link`


**Summary:** Create Knowledge Relationship


**Description:**

Create or update a directed relationship between two nodes.

If an edge with the same source, target, and relation already exists, updates its weight and metadata.

Common relation types: related_to, depends_on, parent_of, contradicts, supersedes, derived_from

Required: source_id, target_id, relation
Optional: weight (default: 1.0), bidirectional (default: false), metadata, valid_from, valid_until


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### related

**Endpoint:** `POST /api/tools/memory/related`


**Summary:** Get Related Nodes


**Description:**

Get all nodes connected to the given node by any edge type (or a specific type).

Traverses both outgoing and incoming edges (bidirectional single-hop).

Required: id
Optional: relation (filter to a specific relation type)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### roots

**Endpoint:** `POST /api/tools/memory/roots`


**Summary:** Get Root Nodes


**Description:**

Get all root nodes — nodes that have no incoming parent_of edges.

Root nodes are the top-level entries in the hierarchy: nothing is their parent.


**Responses:**

- **200:** Successful Response

---

### search

**Endpoint:** `POST /api/tools/memory/search`


**Summary:** Search Knowledge Graph


**Description:**

Search the knowledge graph using full-text search and/or tag filtering.

Three search modes:
- fulltext: FTS5 BM25 full-text search on name, content, and tags (best for keyword queries)
- tags: Filter by exact tag values (best for category lookups)
- hybrid: Full-text + tag filter combined (default, most flexible)

Required: query
Optional: entity_type, tags, max_results (default: 10), search_mode, temporal_filter (ISO date)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### stats

**Endpoint:** `POST /api/tools/memory/stats`


**Summary:** Knowledge Graph Statistics


**Description:**

Return knowledge graph statistics and metrics.

Provides an overview of the entire graph: node/edge counts, type breakdown,
most connected nodes, orphaned nodes, recent activity, and tag frequency.


**Responses:**

- **200:** Successful Response

---

### store

**Endpoint:** `POST /api/tools/memory/store`


**Summary:** Store Knowledge Node


**Description:**

Store a piece of knowledge as a node in the knowledge graph.

Each node holds an atomic fact, concept, or piece of information. Optionally
create edges to existing nodes in the same request.

Required: content
Optional: name (defaults to first 60 chars), entity_type (concept/fact/task/person/event/note),
          tags (list of strings), metadata (dict), source, relations (list of {target_id, relation, weight})

Entity types:
- concept: Abstract idea or category
- fact: Objective, verifiable statement
- task: An action item or TODO
- person: A person or agent
- event: Something that happened or will happen
- note: Free-form note or observation


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### subtree

**Endpoint:** `POST /api/tools/memory/subtree`


**Summary:** Get Node Subtree


**Description:**

Return the full subtree rooted at the given node using a recursive CTE.

Follows parent_of edges downward (from parent to children, then grandchildren, etc.).
The root node itself is NOT included in the results.

Required: id
Optional: max_depth (default: 10)


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### update

**Endpoint:** `POST /api/tools/memory/update`


**Summary:** Update Knowledge Node


**Description:**

Update a memory node's content or metadata.

Only provided fields are changed. Metadata is merged (patch semantics — existing keys preserved).
Tags replace the existing tag list entirely when provided.

Required: id
Optional: content, name, tags, metadata


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## PLAN Tools

### cancel

**Endpoint:** `POST /api/tools/plan/cancel`


**Summary:** Cancel Plan


**Description:**

Cancel a plan, marking all pending and running tasks as skipped.

A cancelled plan cannot be re-executed — create a new plan to re-run.
Useful for aborting long-running plans.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; ambiguous names return an error.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### create

**Endpoint:** `POST /api/tools/plan/create`


**Summary:** Create Plan


**Description:**

Create a new multi-step plan with a DAG of tasks.

Each task specifies an AnyIDE tool to call (tool_category + tool_name + params).
Tasks may depend on other tasks via `depends_on` (list of task IDs).
Task params may contain `{{task:TASK_ID.field}}` references resolved at runtime.

Validates the DAG at creation time using Kahn's algorithm (cycle detection, missing refs).
Returns the execution order grouped by parallel level.
The response includes `plan_id`; pass that value to `plan_execute`, `plan_update_task`, `plan_status`, and `plan_cancel`.

on_failure policies (plan-level default, overridable per-task):
- **stop**: abort all remaining tasks when any task fails (default)
- **skip_dependents**: skip only tasks that depend on the failed task
- **continue**: continue all tasks regardless of failures


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### execute

**Endpoint:** `POST /api/tools/plan/execute`


**Summary:** Get Ready Tasks


**Description:**

Evaluate plan readiness and return runnable tasks.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; if multiple plans share that name, execution fails with an ambiguity error.

This endpoint does not execute tools. It marks a pending plan as running (first call),
computes current `ready_tasks`, and resolves task refs in params using outputs from
already completed tasks.

Use `plan_update_task` after your orchestrator executes each task.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### list

**Endpoint:** `POST /api/tools/plan/list`


**Summary:** List Plans


**Description:**

List all plans with summary information.

Returns plan ID, name, status, task count, and timestamps for all plans.


**Responses:**

- **200:** Successful Response

---

### status

**Endpoint:** `POST /api/tools/plan/status`


**Summary:** Get Plan Status


**Description:**

Get current status of a plan and all its tasks.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; ambiguous names return an error.

Shows per-task status (pending|running|completed|failed|skipped),
output, error messages, and timing information.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### update_task

**Endpoint:** `POST /api/tools/plan/update_task`


**Summary:** Update Task Status


**Description:**

Update one task status after external execution.

Use this endpoint after your orchestrator runs a ready task:
- set status to `running` when execution starts
- set status to `completed` with `output` when execution succeeds
- set status to `failed` with `error` when execution fails

Failure policies (`stop`, `skip_dependents`, `continue`) are enforced here.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## SHELL Tools

### execute

**Endpoint:** `POST /api/tools/shell/execute`


**Summary:** Execute Shell Command


**Description:**

Execute a shell command in the workspace.

Use this tool when you need to:
- Run system commands
- Execute build scripts
- Run tests
- Interact with CLI tools
- Perform system operations

Required: command
Optional: workspace_dir, timeout (default: 60s), env (environment variables)

Security notes:
- Commands with dangerous metacharacters (;, |, &, >, <, etc.) require approval
- Commands not in the allowlist require approval
- Use {{secret:KEY}} syntax in env values for sensitive data
- Output is truncated at 100KB

Allowlisted commands: ls, cat, echo, pwd, git, python, node, npm, docker, curl, and more.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## SKILLS Tools

### install

**Endpoint:** `POST /api/tools/skills/install`


**Summary:** Install Skill


**Description:**

Install a skill from a remote repository using the skills CLI.

Runs `npx skills add <repo> [--skill <name>] -y` in project scope.
Request body fields:
- `repo`: source repository (for example `vercel-labs/agent-skills`)
- `skill_name` (or alias `skill_id`): optional skill within that repo

This operation is HITL-gated by default because it downloads and executes external code.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### list

**Endpoint:** `POST /api/tools/skills/list`


**Summary:** List Installed Skills


**Description:**

List all installed skills from the isolated /skills directory.

This tool is offline-capable and only reads local files.
No workspace path resolution is used.

Use `skills_list` first before `skills_read` or `skills_read_file` so the model has a valid skill name.


**Responses:**

- **200:** Successful Response

---

### read

**Endpoint:** `POST /api/tools/skills/read`


**Summary:** Read Skill File


**Description:**

Read a skill's SKILL.md content.

Use `skills_list` first, then call `skills_read` with `name`.
Compatibility aliases are accepted: `skill_id`, `skill_name`.

Optional `section` allows extracting a specific markdown section by header text.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### read_file

**Endpoint:** `POST /api/tools/skills/read_file`


**Summary:** Read Skill Nested File


**Description:**

Read a specific file inside an installed skill directory.

Use `skills_list` first and pass the selected skill as `name`
(compatibility aliases: `skill_id`, `skill_name`).

The provided `file_path` must be a relative path and resolve within the selected skill directory.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

### search

**Endpoint:** `POST /api/tools/skills/search`


**Summary:** Search Skills Registry


**Description:**

Search available skills using the skills CLI registry.

Runs `npx skills find <query> --json` and parses structured results.
Requires outbound network access.

If remote search is unavailable, fall back to local workflows:
`skills_list` -> `skills_read` -> `skills_read_file`.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## SUBAGENT Tools

### list

**Endpoint:** `POST /api/tools/subagent/list`


**Summary:** List Subagent Types


**Description:**

List configured subagent types from `config.subagents.types`.

Use this before `subagent_run` to discover valid type IDs and endpoint/model bindings.


**Responses:**

- **200:** Successful Response

---

### run

**Endpoint:** `POST /api/tools/subagent/run`


**Summary:** Run Subagent


**Description:**

Run one configured subagent task as a single LLM completion.

Execution flow:
1. Load subagent type config
2. Read and render system prompt template
3. Call unified LLM client with configured endpoint/model defaults
4. Return response plus metadata (latency/usage/model/endpoint)

`override_model` and `override_temperature` are only accepted when enabled for that subagent type.


**Request Body:**


**Responses:**

- **200:** Successful Response
- **422:** Validation Error

---

## WORKSPACE Tools

### info

**Endpoint:** `POST /api/tools/workspace/info`


**Summary:** Get Workspace Information


**Description:**

Get information about the workspace configuration.

Returns the default workspace directory, available paths, disk usage,
and available tool categories.

Use this tool when you need to:
- Understand the workspace boundaries
- Check available disk space
- See what tool categories are available
- Get the base workspace path for other operations

No parameters required.


**Responses:**

- **200:** Successful Response

---

### secrets

**Endpoint:** `POST /api/tools/workspace/secrets/list`


**Summary:** List Configured Secrets


**Description:**

List the names (keys) of all configured secrets.

Secret VALUES are never exposed — only their names are returned so you
know which keys are available for use as {{secret:KEY}} templates in
tool parameters (headers, environment variables, etc.).

Use this tool to:
- Discover available secret keys before using them in requests
- Verify that a required secret is configured

No parameters required.


**Responses:**

- **200:** Successful Response

---

## MCP Tool Names

When using MCP clients, tools are identified by their operation IDs:

- `docker_action` - docker/action
- `docker_inspect` - docker/inspect
- `docker_list` - docker/list
- `docker_logs` - docker/logs
- `fs_list` - fs/list
- `fs_read` - fs/read
- `fs_search` - fs/search
- `fs_write` - fs/write
- `git_branch` - git/branch
- `git_checkout` - git/checkout
- `git_commit` - git/commit
- `git_diff` - git/diff
- `git_list_branches` - git/list_branches
- `git_log` - git/log
- `git_pull` - git/pull
- `git_push` - git/push
- `git_remote` - git/remote
- `git_show` - git/show
- `git_stash` - git/stash
- `git_status` - git/status
- `http_request` - http/request
- `lang_apply_patch` - language/apply_patch
- `lang_create_file` - language/create_file
- `lang_diff` - language/diff
- `lang_index` - language/index
- `lang_read_file` - language/read_file
- `lang_reference_graph` - language/reference_graph
- `lang_search_symbols` - language/search_symbols
- `lang_skeleton` - language/skeleton
- `lang_validate` - language/validate
- `memory_ancestors` - memory/ancestors
- `memory_children` - memory/children
- `memory_delete` - memory/delete
- `memory_get` - memory/get
- `memory_link` - memory/link
- `memory_related` - memory/related
- `memory_roots` - memory/roots
- `memory_search` - memory/search
- `memory_stats` - memory/stats
- `memory_store` - memory/store
- `memory_subtree` - memory/subtree
- `memory_update` - memory/update
- `plan_cancel` - plan/cancel
- `plan_create` - plan/create
- `plan_execute` - plan/execute
- `plan_list` - plan/list
- `plan_status` - plan/status
- `plan_update_task` - plan/update_task
- `shell_execute` - shell/execute
- `skills_install` - skills/install
- `skills_list` - skills/list
- `skills_read` - skills/read
- `skills_read_file` - skills/read_file
- `skills_search` - skills/search
- `subagent_list` - subagent/list
- `subagent_run` - subagent/run
- `workspace_info` - workspace/info
- `workspace_secrets_list` - workspace/secrets
