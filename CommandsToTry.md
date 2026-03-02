# AnyIDE - Commands to Try

This document provides sample requests you can give to an LLM that has access to the AnyIDE tool server. These commands demonstrate the capabilities of each tool currently available.

## Admin Dashboard

Before trying commands, you can monitor and approve operations through the admin dashboard:

**Access:** http://localhost:8080/admin/  
**Default Password:** `admin`  
**Password precedence:** `ANYIDE_ADMIN_PASSWORD` > `ADMIN_PASSWORD` (legacy) > `config.yaml auth.admin_password` > default `admin`

The dashboard provides a unified widget-based interface:
- **HITL Approval Queue Widget:** See pending requests, approve/reject directly from dashboard
- **System Health Widget:** Monitor uptime, error rates, and system metrics in real-time
- **Recent Activity Widget:** View last 5 tool executions with status badges

**Features:**
- Expandable/collapsible widgets for flexible monitoring
- Real-time updates via WebSocket (no refresh needed)
- Quick actions directly from dashboard
- "View All" buttons to navigate to dedicated pages for detailed analysis
- Fully responsive design for mobile, tablet, and desktop
- Automatic redirect to `/admin/login` when session expires (401 handling)

## Admin LLM Endpoint Controls (System Capability)

LLM endpoint config is an admin/system feature (`config.yaml` + admin API), not a tool module.

**"List configured LLM endpoints from the admin API"**
- Calls `GET /admin/api/llm/endpoints`
- Returns endpoint IDs, providers, models, base URLs, timeout, and API-key presence flag (no secret values)

**"Test connectivity for the primary LLM endpoint"**
- Calls `POST /admin/api/llm/test` with `endpoint_id`
- Returns normalized success/failure, latency, and error type/message

```bash
# Login and export admin token
TOKEN=$(curl -s -X POST http://localhost:8080/admin/api/login \
  -H "Content-Type: application/json" \
  -d '{"password":"admin"}' | jq -r '.token')

# List configured endpoints (sanitized)
curl -s http://localhost:8080/admin/api/llm/endpoints \
  -H "Authorization: Bearer $TOKEN" | jq

# Test one endpoint
curl -s -X POST http://localhost:8080/admin/api/llm/test \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"endpoint_id":"primary","prompt":"Respond with exactly: OK"}' | jq
```

## Protocol Support

AnyIDE supports two protocols:
- **OpenAPI (REST)**: Traditional HTTP REST API
- **MCP (Model Context Protocol)**: Modern protocol for AI tool integration using Streamable HTTP

Both protocols expose the same tools from a single source of truth - no code duplication.
Admin-only system capabilities (like LLM endpoint config/testing) remain outside MCP and `/api/tools/*`.

## Getting Started

Before trying file operations, it's helpful to understand the workspace configuration:

### Module Selection

Use these deployment commands to verify module enable/disable behavior:

```bash
# Start with all modules except docker and http
ANYIDE_MODULES=all,-docker,-http docker compose up -d --build

# Confirm disabled modules are absent from OpenAPI
curl -s http://localhost:8080/openapi.json | jq '.paths | keys[]' | grep '/api/tools/docker/' || true
curl -s http://localhost:8080/openapi.json | jq '.paths | keys[]' | grep '/api/tools/http/' || true

# Start with an explicit allowlist
ANYIDE_MODULES=fs,workspace,shell,git,memory,plan,language,skills docker compose up -d --build
```

If `jq` is not installed, save `openapi.json` and inspect it manually.

For skills module operation modes:
- Ensure a dedicated `./skills:/skills` volume mount exists in `docker-compose.yaml`.
- Offline-capable tools: `skills_list`, `skills_read`, `skills_read_file`.
- Network-required tools: `skills_search`, `skills_install` (HITL-gated).
- `skills_install` runs in project scope and writes under mounted `/skills` (commonly `/skills/.agents/skills/<name>`).

### Workspace Information

**"What workspace am I working in?"**
- Gets the default workspace directory, available paths, disk usage, and tool categories

**"Show me the workspace configuration"**
- Returns workspace boundaries and available tool categories

**"What secrets are loaded?"**
- Lists the names of secrets available for use in `{{secret:KEY}}` templates (no values exposed)

**"Reload the secrets file"**
- Triggers the server to re-read `secrets.env` from disk (admin action)

### Documentation and Configuration Workflows

**"Read docs/TOOL_CATALOG.md and show me all Docker-related tools"**
- Uses the generated catalog as a quick reference for endpoint and MCP names

**"Generate a fresh tool catalog from the running OpenAPI schema"**
- Runs: `python3 scripts/generate_tool_docs.py > docs/TOOL_CATALOG.md`

**"Compare examples/config.basic.yaml and examples/config.restricted.yaml"**
- Highlights policy and HTTP boundary differences between baseline and hardened setups

**"Show me how to publish this image using docs/DOCKER_HUB_PUBLISHING.md"**
- Walks through build, tag, and push commands for Docker Hub

## Filesystem Tools

### Reading Files

**"Read the contents of README.md"**
- Reads the entire file from the workspace

**"Show me the first 10 lines of example.txt"**
- Reads a file with a line limit

**"Read lines 5 through 15 of test.txt"**
- Reads a specific range of lines from a file

**"What's in the file at workspace/nested/deep/file.txt?"**
- Reads a file from a nested directory path

**"Show me the contents of test.conf"**
- Reads a configuration file

### Listing Directories

**"List all files in the current directory"**
- Shows files and directories in the workspace root

**"Show me all Python files in the project"**
- Lists files matching the *.py pattern

**"List all files recursively up to 3 levels deep"**
- Recursive directory listing with depth control

**"Show me all files including hidden ones"**
- Lists files including those starting with a dot

**"What files are in the src directory?"**
- Lists contents of a specific subdirectory

### Searching Files

**"Find all files with 'test' in the name"**
- Searches for files by filename

**"Search for files containing the word 'TODO'"**
- Searches file contents for specific text

**"Find all configuration files"**
- Searches for files matching patterns like *.conf, *.yaml

**"Search for 'import requests' in Python files"**
- Searches file contents with specific patterns

**"Find files matching the regex pattern 'test_.*\.py'"**
- Uses regex for advanced filename matching

### Writing Files

**"Create a new file called hello.txt with the content 'Hello, World!'"**
- Creates a new file with specified content

**"Overwrite example.txt with 'New content here'"**
- Replaces the entire contents of an existing file

**"Append 'Additional line' to the end of test.txt"**
- Adds content to the end of an existing file

**"Create a file at workspace/new_folder/document.txt with content 'Test' and create any missing directories"**
- Creates a file and automatically creates parent directories if they don't exist

**"Write a configuration file at config/app.yaml with the following YAML content: [your YAML here]"**
- Creates a configuration file (may require HITL approval depending on policy)

## Shell Execution

### Safe Commands

**"Run 'ls -la' to see all files"**
- Lists files with details using shell command

**"Execute 'pwd' to show current directory"**
- Shows the current working directory

**"Run 'echo Hello World'"**
- Simple echo command

**"Execute 'git status' to check repository status"**
- Runs git commands (if git is available)

**"Run 'python --version' to check Python version"**
- Checks installed software versions

**"Execute 'cat README.md' to read the file"**
- Uses shell commands to read files

### Commands with Environment Variables

**"Run a command with custom environment variables"**
- Executes commands with additional env vars

**"Execute 'echo $MY_VAR' with MY_VAR set to 'test'"**
- Demonstrates environment variable usage

**"Run a git push command with GIT_TOKEN set to my GITHUB_TOKEN secret"**
- Use `{{secret:GITHUB_TOKEN}}` as the env var value — it will be resolved server-side before execution

### Working Directory Control

**"Run 'ls' in the src directory"**
- Executes command in a specific directory

**"Execute 'pwd' in workspace/nested"**
- Shows working directory control

### Commands Requiring Approval

**"Run 'rm -rf temp' to delete the temp directory"**
- Dangerous commands require HITL approval

**"Execute 'ls | grep test' to filter results"**
- Commands with pipes require approval

**"Run 'curl https://api.example.com > output.txt'"**
- Commands with redirects require approval

## Git Tools

### Repository Status

**"What's the status of the git repository?"**
- Shows current branch, staged/unstaged files, and untracked files

**"Check the git status of the project"**
- Returns branch info, commits ahead/behind, and working tree status

**"Show me what files have changed in the repository"**
- Lists modified, staged, and untracked files

### Commit History

**"Show me the last 10 commits"**
- Displays recent commit history with hashes, authors, and messages

**"View the commit history for the last week"**
- Filters commits by date range

**"Show commits by John Doe"**
- Filters commit history by author

**"What commits modified README.md?"**
- Shows commit history for a specific file

### Viewing Changes

**"Show me the diff of uncommitted changes"**
- Displays unstaged changes in unified diff format

**"What changes are staged for commit?"**
- Shows diff of staged changes

**"Compare current state with the last commit"**
- Shows differences between working tree and HEAD

**"Show me just the statistics of changes"**
- Returns files changed, insertions, and deletions counts

### Commit Details

**"Show me the details of the last commit"**
- Displays full commit information including diff

**"What did commit abc123 change?"**
- Shows specific commit details by hash

**"Show me the full diff for HEAD"**
- Displays complete commit information with changes

### Branch Management

**"List all branches in the repository"**
- Shows local branches with current branch indicator

**"Show me all branches including remote ones"**
- Lists both local and remote branches

**"Create a new branch called feature-x"**
- Creates a new branch from current HEAD

**"Switch to the develop branch"** (requires HITL approval)
- Checks out a different branch

**"Delete the old-feature branch"** (requires HITL approval)
- Removes a branch (with safety checks)

### Remote Operations

**"List all configured remotes"**
- Shows remote repositories with fetch/push URLs

**"Add a remote called upstream with URL https://github.com/user/repo.git"**
- Configures a new remote repository

**"Remove the old-remote remote"**
- Deletes a remote configuration

### Stash Operations

**"Stash my current changes"**
- Saves working directory changes to stash

**"List all stashes"**
- Shows all saved stashes with messages

**"Apply the most recent stash"**
- Restores stashed changes

**"Drop stash 0"**
- Removes a specific stash

### Write Operations (Require HITL Approval)

**"Commit the staged changes with message 'Add new feature'"** (requires approval)
- Creates a new commit with specified message

**"Commit all changes with message 'Update documentation'"** (requires approval)
- Stages all changes and creates a commit

**"Push changes to origin main"** (requires approval)
- Pushes commits to remote repository

**"Push to a private repository using my GITHUB_TOKEN secret"** (requires approval)
- Uses `{{secret:GITHUB_TOKEN}}` for authentication
- Secure GIT_ASKPASS flow handles credentials automatically

**"Pull from a private repository with credentials from secrets"**
- Uses `{{secret:GIT_USER}}` and `{{secret:GIT_TOKEN}}` for authentication
- Credentials are resolved server-side and never logged

**"Pull latest changes from origin"**
- Fetches and merges changes from remote

**"Checkout the feature branch"** (requires approval)
- Switches to a different branch

## Language Tools (Tree-sitter First)

### Structure-Aware Reading

**"Show me the skeleton of src/app.py"**
- Calls `lang_skeleton` to list classes/functions/methods with line ranges

**"Read only function process_data from src/app.py with line numbers"**
- Calls `lang_read_file` with `window: "function:process_data"` and `format: "numbered"`

**"Show only imports from src/app.py"**
- Calls `lang_read_file` with `window: "import:*"`

**"Read lines 40-80 from src/app.py"**
- Calls `lang_read_file` with `window: "lines:40-80"`

### Structural Editing

**"Generate a function-anchored diff for this updated content in src/app.py"**
- Calls `lang_diff` and returns anchored hunks + syntax validation

**"Apply this anchored patch to src/app.py and validate after patch"**
- Calls `lang_apply_patch` with `validate: true` and optional backup creation

**"Create src/new_module.py with this code and validate it"**
- Calls `lang_create_file` and returns parse/lint + symbol metadata

### Indexing and Symbol Search

**"Index the current workspace codebase"**
- Calls `lang_index` (incremental SQLite index)

**"Search symbols matching build_* in Python"**
- Calls `lang_search_symbols` with wildcard query and language filter

**"Build a reference graph for src/app.py"**
- Calls `lang_reference_graph` for file-scope caller/callee edges

### Validation

**"Validate syntax and lint for src/app.py"**
- Calls `lang_validate` with checks `["syntax","lint"]`

**"Check if src/broken.py has syntax errors"**
- Calls `lang_validate` with checks `["syntax"]`

### Curl Examples

```bash
# Skeleton overview
curl -X POST http://localhost:8080/api/tools/language/skeleton \
  -H "Content-Type: application/json" \
  -d '{"paths":["src/app.py"]}'

# Function-scoped read
curl -X POST http://localhost:8080/api/tools/language/read_file \
  -H "Content-Type: application/json" \
  -d '{"path":"src/app.py","window":"function:process_data","format":"numbered"}'

# Workspace indexing + symbol search
curl -X POST http://localhost:8080/api/tools/language/index \
  -H "Content-Type: application/json" \
  -d '{"force_reindex":true}'

curl -X POST http://localhost:8080/api/tools/language/search_symbols \
  -H "Content-Type: application/json" \
  -d '{"query":"build_*","language":"python"}'

# Syntax + lint
curl -X POST http://localhost:8080/api/tools/language/validate \
  -H "Content-Type: application/json" \
  -d '{"path":"src/app.py","checks":["syntax","lint"]}'
```

## Skills Module

### Offline-Capable Skill Reads

**"List installed skills"**
- Calls `skills_list` and reads local `/skills` (including `.agents/skills` installs)

**"Read the SKILL.md for the vitest skill"**
- Calls `skills_read` with `name: "vitest"`
- Supports optional `section` extraction

**"Read scripts/install.sh from the vitest skill"**
- Calls `skills_read_file` with `name` + relative `file_path`
- File path is constrained to the selected skill directory

### Online Registry Actions

**"Search for skills about React testing"**
- Calls `skills_search` (`npx skills find ... --json`)
- Requires outbound network access

**"Install the vitest skill from vercel-labs/agent-skills"** (requires approval)
- Calls `skills_install` (HITL-gated by default)
- Install runs in project scope (no `--global`) so follow-up `skills_list`/`skills_read` can find the new skill immediately
- Fails with a clear network/egress error if outbound access is blocked

### Curl Examples

```bash
# List local installed skills
curl -X POST http://localhost:8080/api/tools/skills/list

# Read a skill (optionally include "section":"Usage")
curl -X POST http://localhost:8080/api/tools/skills/read \
  -H "Content-Type: application/json" \
  -d '{"name":"vitest"}'

# Read a nested skill file
curl -X POST http://localhost:8080/api/tools/skills/read_file \
  -H "Content-Type: application/json" \
  -d '{"name":"vitest","file_path":"scripts/install.sh"}'

# Search remote skills
curl -X POST http://localhost:8080/api/tools/skills/search \
  -H "Content-Type: application/json" \
  -d '{"query":"react testing","max_results":5}'

# Install a skill (will enter HITL queue)
curl -X POST http://localhost:8080/api/tools/skills/install \
  -H "Content-Type: application/json" \
  -d '{"repo":"vercel-labs/agent-skills","skill_name":"vitest"}'

# Verify installed skill is discoverable immediately
curl -X POST http://localhost:8080/api/tools/skills/list
curl -X POST http://localhost:8080/api/tools/skills/read \
  -H "Content-Type: application/json" \
  -d '{"name":"vitest"}'
```

## Secrets and HTTP Tools

### Secret Templates

AnyIDE resolves `{{secret:KEY}}` placeholders server-side in any tool parameter before execution. The original template (not the resolved value) is stored in audit logs.

**"What secrets are available to use?"**
- Returns the list of loaded secret key names without exposing their values

**"Make an API call to GitHub using my GITHUB_TOKEN secret"**
- The LLM will use `{{secret:GITHUB_TOKEN}}` in the Authorization header

**"Run a shell command that uses my DB_PASSWORD secret in the environment"**
- Secrets resolve in shell environment variables too — use `{{secret:DB_PASSWORD}}`

### HTTP Requests

**"Fetch the contents of https://httpbin.org/get"**
- Makes a simple GET request and returns the response body

**"POST to https://api.example.com/data with JSON body {\"key\": \"value\"}"**
- Makes a POST request with a JSON payload

**"Make a GET request to https://api.github.com/user with Authorization header using my GITHUB_TOKEN"**
- Uses secret template injection: `Authorization: Bearer {{secret:GITHUB_TOKEN}}`

**"Fetch https://httpbin.org/headers and show me what headers were sent"**
- Inspects the outgoing request headers

**"Make a request to https://slow-api.example.com with a 60-second timeout"**
- Configurable timeout per request (capped by server's max_timeout setting)

### SSRF Protection (Security Boundaries)

**"Fetch http://192.168.1.1/admin"**
- This will fail — private IP ranges are blocked by SSRF protection

**"Make a request to http://localhost:9200"**
- Blocked — loopback addresses are private ranges

**"Fetch http://169.254.169.254/latest/meta-data"**
- Blocked — cloud metadata endpoints are explicitly denied

**"Try to reach http://10.0.0.1/internal"**
- Blocked — RFC 1918 address space is protected

## Docker Tools

### Listing Containers

**"Show me all Docker containers"**
- Lists all containers (running and stopped) with details

**"List only running Docker containers"**
- Shows containers that are currently running

**"Find containers with 'nginx' in the name"**
- Filters containers by name (partial match)

**"Show me all exited containers"**
- Filters containers by status (exited, paused, etc.)

**"What Docker containers are on this system?"**
- Returns container ID, name, image, status, ports, and creation time

### Inspecting Containers

**"Inspect the anyide container"**
- Gets detailed information about a specific container

**"Show me the configuration of the nginx container"**
- Returns environment variables, command, entrypoint, labels

**"What network settings does the database container have?"**
- Shows IP address, ports, networks

**"Show me the volume mounts for the app container"**
- Lists all volume and bind mounts

**"What's the current state of the redis container?"**
- Returns running status, PID, exit code, timestamps

### Viewing Container Logs

**"Show me the logs from the anyide container"**
- Retrieves last 100 lines of container logs (default)

**"Get the last 50 lines of logs from nginx"**
- Retrieves specific number of log lines

**"Show me logs from the app container since 2024-01-01"**
- Filters logs by timestamp

**"What errors are in the database container logs?"**
- LLM can analyze logs for errors after retrieval

### Container Control (Requires HITL Approval)

**"Restart the nginx container"** (requires approval)
- Stops and starts the container

**"Start the stopped database container"** (requires approval)
- Starts a container that's not running

**"Stop the app container"** (requires approval)
- Gracefully stops a running container

**"Pause the redis container"** (requires approval)
- Freezes container processes

**"Unpause the redis container"** (requires approval)
- Resumes a paused container

### Multi-Step Docker Workflows

**"List all containers, then show me the logs from any that are failing"**
- Combines listing and log retrieval

**"Inspect the nginx container and tell me if it's configured correctly"**
- LLM analyzes container configuration

**"Check if the database container is running, and if not, start it"** (requires approval)
- Conditional container management

## Memory Tools (Knowledge Graph)

### Store and Retrieve Knowledge

**"Remember that the production database host is db.prod.internal"**
- Stores a fact node with entity type `fact`

**"Store this as a concept: Python is a high-level, dynamically-typed programming language"**
- Creates a named concept node with content

**"What do you know about Python?"** (after storing related nodes)
- Uses `memory_search` to find relevant nodes via FTS5 BM25 ranking

**"What do you know about Keyur Golani?"** (after storing facts)
- Natural-language question phrasing is normalized for better recall on person-name queries

**"Find everything related to databases"**
- Searches knowledge graph for database-related nodes

### Linking and Relationships

**"Note that FastAPI depends on Python"**
- Creates a `depends_on` typed edge from FastAPI node to Python node

**"Mark FastAPI as a child of Python in the knowledge hierarchy"**
- Creates a `parent_of` edge (Python → FastAPI)

**"What are all the children of the Python node?"**
- Traverses `parent_of` edges to list direct children

**"What are all the ancestors of the FastAPI node?"**
- Recursive CTE traversal upward through `parent_of` edges

### Graph Navigation

**"Show me the entire subtree under the Python knowledge node"**
- Returns all descendants via `memory_subtree` (recursive, configurable depth)

**"What are all root-level knowledge nodes?"**
- Returns nodes with no incoming `parent_of` edges via `memory_roots`

**"What is FastAPI related to?"**
- Returns all nodes connected by any edge type via `memory_related`

### Knowledge Management

**"Update the Python node to mention it's version 3.12"**
- Merges metadata and updates content via `memory_update`

**"Show me knowledge graph statistics"**
- Returns node/edge counts, type breakdown, tag frequency, most-connected nodes

**"Delete the outdated API endpoint node"** (requires HITL approval)
- HITL-gated deletion to prevent accidental knowledge loss

### Curl Examples

```bash
# Store a node
curl -X POST http://localhost:8080/api/tools/memory/store \
  -H "Content-Type: application/json" \
  -d '{"name": "Python", "content": "High-level programming language", "entity_type": "technology", "tags": ["programming", "language"]}'

# Search by text
curl -X POST http://localhost:8080/api/tools/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query": "programming language"}'

# Search by tags only
curl -X POST http://localhost:8080/api/tools/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query": "", "tags": ["programming"], "search_mode": "tags"}'

# Create a relationship
curl -X POST http://localhost:8080/api/tools/memory/link \
  -H "Content-Type: application/json" \
  -d '{"source_id": "<parent-id>", "target_id": "<child-id>", "relation": "parent_of"}'

# Get graph statistics
curl -X POST http://localhost:8080/api/tools/memory/stats \
  -H "Content-Type: application/json" -d '{}'
```

## Understanding Tool Behavior

### Security and Boundaries

**"Try to read /etc/passwd"**
- This will fail with a security error - paths must be within the workspace boundary

**"Read a file at ../../../etc/passwd"**
- Path traversal attempts are blocked by the workspace security model

### Error Handling

**"Read a file called nonexistent.txt"**
- Demonstrates file not found error with helpful suggestion to use workspace info

**"Write to example.txt with mode 'create'"**
- If the file exists, this will fail and suggest using 'overwrite' or 'append' mode

### HITL (Human-in-the-Loop) Scenarios

Certain operations require human approval through the admin dashboard. When triggered, these requests appear in real-time in the HITL Approval Queue widget:

**"Overwrite the file test.conf with new configuration"**
- Writing to .conf files requires approval
- Request appears in dashboard widget with yellow glow and countdown timer
- Expand widget to see request details
- Admin can approve or reject directly from dashboard
- Or click "View All" to see full request details on dedicated page

**"Create a new .env file with environment variables"**
- Writing to .env files requires approval
- Dashboard widget shows pending count badge
- Real-time WebSocket notification

**"Write to production.yaml with updated settings"**
- Writing to .yaml files requires approval
- Widget updates immediately with visual alert
- Sound notification plays (if enabled)

## Advanced Usage Patterns

### Working with Encodings

**"Read the file data.txt using UTF-8 encoding"**
- Explicitly specify file encoding (UTF-8 is the default)

**"Read the file legacy.txt using latin-1 encoding"**
- Read files with non-UTF-8 encodings

### Large File Handling

**"Read the first 100 lines of large_log.txt"**
- Limit the number of lines returned for large files

**"Show me lines 1000 to 1100 of big_file.txt"**
- Read a specific section from a large file

### Multi-Step Workflows

**"First, show me what's in the workspace, then read README.md, and create a summary file called SUMMARY.txt"**
- Combines workspace info, file reading, and file writing

**"Read test.txt, then create a backup called test.txt.backup with the same content"**
- Demonstrates reading and writing in sequence

## Testing Tool Server Features

### Policy Enforcement

**"Write to a file called .secret"**
- Tests dotfile blocking policy (if configured)

**"Try to write binary content to a file"**
- Tests binary file blocking (if configured)

### Workspace Override (Advanced)

**"Read a file from a different workspace directory"**
- Tests workspace_dir parameter override (may require HITL approval)

### Test Suite Workflows

**"Run the integration test suite with pytest tests/test_integration.py -v"**
- Exercises end-to-end API/admin flows in one pass

**"Run the security regression suite with pytest tests/test_security.py -v"**
- Validates SSRF, path traversal, auth, and input-handling protections

**"Run the load/concurrency suite with pytest tests/test_load.py -v"**
- Checks behavior under concurrent file/API activity

**"Run admin frontend unit tests with cd admin && npm run test"**
- Validates auth/session behavior, including redirect on expired sessions

## Tips for LLM Interaction

When working with an LLM that has access to these tools:

1. **Be specific about paths** - Use relative paths from the workspace root or full paths within the workspace
2. **Specify your intent clearly** - "Create a new file" vs "Overwrite existing file" vs "Append to file"
3. **Check before destructive operations** - Ask the LLM to read a file before overwriting it
4. **Use natural language** - The LLM will translate your request into the appropriate tool calls
5. **Combine operations** - You can ask for multi-step workflows in a single request

## Current Tool Inventory

As of this version, AnyIDE supports:

- **Health Check** (via MCP: `health_check_health_get`)
  - Check server health and version

- **Filesystem Tools** (category: `fs`)
  - `fs_read` - Read file contents with optional line ranges and encoding
  - `fs_write` - Write, overwrite, or append to files with security controls
  - `fs_list` - List directory contents with recursive traversal and filtering
  - `fs_search` - Search files by name or content with regex support

- **Shell Tools** (category: `shell`)
  - `shell_execute` - Execute shell commands with security controls
    - Allowlist of safe commands (ls, cat, echo, git, python, npm, docker, etc.)
    - Dangerous metacharacter detection (;, |, &, >, <, etc.)
    - HITL for non-allowlisted or unsafe commands

- **Git Tools** (category: `git`)
  - `git_status` - Get repository status (branch, staged, unstaged, untracked)
  - `git_log` - View commit history with filtering options
  - `git_diff` - View file differences (unstaged, staged, or against ref)
  - `git_show` - Show commit details with full diff
  - `git_list_branches` - List local and remote branches
  - `git_remote` - Manage remote repositories (list, add, remove)
  - `git_commit` - Create commits (HITL required)
  - `git_push` - Push to remote (HITL required)
  - `git_pull` - Pull from remote
  - `git_checkout` - Switch branches or restore files (HITL required)
  - `git_branch` - Create or delete branches (HITL for delete)
  - `git_stash` - Stash operations (push, pop, list, drop)

- **Docker Tools** (category: `docker`)
  - `docker_list` - List Docker containers with filtering
    - Filter by name (partial match) or status (running, exited, paused, etc.)
    - Include/exclude stopped containers
  - `docker_inspect` - Get detailed container information
    - Configuration (environment variables, command, entrypoint, labels)
    - Network settings (IP address, ports, networks)
    - Volume mounts and bind mounts
    - Container state (running, paused, exit code, PID, timestamps)
  - `docker_logs` - Retrieve container logs
    - Configurable tail (number of lines from end)
    - Time-based filtering (since timestamp)
  - `docker_action` - Control container lifecycle (HITL required)
    - Start, stop, restart, pause, unpause containers

- **Workspace Tools** (category: `workspace`)
  - `workspace_info` - Get workspace configuration and boundaries
  - `workspace_secrets_list` - List loaded secret key names (no values exposed)

- **HTTP Tools** (category: `http`)
  - `http_request` - Make outbound HTTP requests
    - Supports GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS
    - Custom headers and JSON/text request bodies
    - `{{secret:KEY}}` template injection in URL, headers, and body
    - SSRF protection: private IPs and metadata endpoints blocked
    - Domain allowlist/blocklist (configured in `config.yaml`)
    - Configurable timeout (up to server's max_timeout)
    - Response truncation at configured `max_response_size_kb`

- **Language Tools** (category: `language`)
  - `lang_read_file` - Read files using structural windows (`function:`, `class:`, `import:*`, `lines:`)
  - `lang_skeleton` - Return class/function/method skeleton with line ranges
  - `lang_diff` - Produce function-anchored diffs with syntax validation
  - `lang_apply_patch` - Apply anchored patch hunks with backup + validation options
  - `lang_create_file` - Create files with syntax/lint validation and symbol extraction
  - `lang_index` - Build/update workspace symbol index
  - `lang_search_symbols` - Query indexed symbols by wildcard/name/kind/language
  - `lang_reference_graph` - Build baseline reference graph for file/workspace scope
  - `lang_validate` - Run syntax and linter checks

- **Skills Tools** (category: `skills`)
  - `skills_list` - List locally installed skills from isolated `/skills` storage (including `.agents/skills` installs)
  - `skills_read` - Read `SKILL.md` content (optional section extraction)
  - `skills_read_file` - Read scripts/references files within a skill directory
  - `skills_search` - Search remote skills registry (`npx skills find ... --json`)
  - `skills_install` - Install skills from remote repo in project scope under `/skills` (HITL required; network egress needed)

- **Plan Tools** (category: `plan`)
  - `plan_create` - Create a plan with DAG validation
    - Validates task dependencies, detects cycles via Kahn's algorithm
    - Returns plan_id, execution order, task count
  - `plan_execute` - Evaluate readiness and return runnable tasks
    - Prefer `plan_id` from `plan_create` response
    - Unique plan names are accepted as fallback; ambiguous names are rejected
    - Marks plan `pending -> running` on first call
    - Returns `ready_tasks` with `resolved_params` and dependency metadata
  - `plan_update_task` - Update one task after external execution
    - Set `running`, `completed` (with `output`), `failed` (with `error`), or `skipped`
    - Enforces failure policies (`stop`, `skip_dependents`, `continue`)
    - Returns updated counts and the next `ready_tasks` set
  - `plan_status` - Get plan and per-task status
    - Task states: pending, running, completed, failed, skipped
    - Includes outputs, errors, timestamps
  - `plan_list` - List all plans with summary info
  - `plan_cancel` - Cancel a pending or running plan

### MCP-Specific Tool Names

When using MCP clients (Claude Desktop, Cursor, etc.), tools are identified by their operation IDs:
- `health_check_health_get` - Health check
- `fs_read` - Read files
- `fs_write` - Write files
- `fs_list` - List directories
- `fs_search` - Search files
- `shell_execute` - Execute shell commands
- `git_status` - Git repository status
- `git_log` - Git commit history
- `git_diff` - Git file differences
- `git_show` - Git commit details
- `git_list_branches` - Git branch list
- `git_remote` - Git remote management
- `git_commit` - Git commit creation
- `git_push` - Git push to remote
- `git_pull` - Git pull from remote
- `git_checkout` - Git checkout branch
- `git_branch` - Git branch operations
- `git_stash` - Git stash operations
- `docker_list` - List Docker containers
- `docker_inspect` - Inspect Docker container
- `docker_logs` - Get Docker container logs
- `docker_action` - Control Docker container lifecycle
- `workspace_info` - Workspace information
- `workspace_secrets_list` - List secret key names
- `http_request` - Make outbound HTTP requests
- `lang_read_file` - Read files with structure-aware windows
- `lang_skeleton` - Get file skeleton
- `lang_diff` - Generate function-anchored diffs
- `lang_apply_patch` - Apply anchored patch hunks
- `lang_create_file` - Create code files with validation
- `lang_index` - Build/update symbol index
- `lang_search_symbols` - Search indexed symbols
- `lang_reference_graph` - Build baseline reference graph
- `lang_validate` - Run syntax/lint validation
- `skills_list` - List installed skills
- `skills_read` - Read SKILL.md content
- `skills_read_file` - Read files inside skill directories
- `skills_search` - Search remote skills registry
- `skills_install` - Install remote skills (HITL-gated)
- `memory_store` - Store a knowledge node
- `memory_get` - Retrieve a node with its relationships
- `memory_search` - Full-text search across knowledge graph
- `memory_update` - Update node content or metadata
- `memory_delete` - Delete a node (HITL-gated)
- `memory_link` - Create a typed edge between nodes
- `memory_children` - Get child nodes via parent_of edges
- `memory_ancestors` - Traverse upward via parent_of edges
- `memory_roots` - Get all root nodes
- `memory_related` - Get all connected nodes
- `memory_subtree` - Get full descendant subtree
- `memory_stats` - Knowledge graph metrics
- `plan_create` - Create a DAG-based orchestration plan
- `plan_execute` - Get current ready tasks
- `plan_update_task` - Update task status after external execution
- `plan_status` - Get plan and task status
- `plan_list` - List all plans
- `plan_cancel` - Cancel a plan

### OpenAPI Endpoints

When using REST API directly:
- Assumes `ANYIDE_MODULES=all`; disabled modules are omitted from discovery and endpoint registration.
- `GET /health` - Health check
- `POST /api/tools/fs/read` - Read files
- `POST /api/tools/fs/write` - Write files
- `POST /api/tools/fs/list` - List directories
- `POST /api/tools/fs/search` - Search files
- `POST /api/tools/shell/execute` - Execute shell commands
- `POST /api/tools/git/status` - Git repository status
- `POST /api/tools/git/log` - Git commit history
- `POST /api/tools/git/diff` - Git file differences
- `POST /api/tools/git/show` - Git commit details
- `POST /api/tools/git/list_branches` - Git branch list
- `POST /api/tools/git/remote` - Git remote management
- `POST /api/tools/git/commit` - Git commit creation
- `POST /api/tools/git/push` - Git push to remote
- `POST /api/tools/git/pull` - Git pull from remote
- `POST /api/tools/git/checkout` - Git checkout branch
- `POST /api/tools/git/branch` - Git branch operations
- `POST /api/tools/git/stash` - Git stash operations
- `POST /api/tools/docker/list` - List Docker containers
- `POST /api/tools/docker/inspect` - Inspect Docker container
- `POST /api/tools/docker/logs` - Get Docker container logs
- `POST /api/tools/docker/action` - Control Docker container lifecycle
- `POST /api/tools/workspace/info` - Workspace information
- `POST /api/tools/workspace/secrets/list` - List secret key names
- `POST /api/tools/http/request` - Make outbound HTTP requests
- `POST /api/tools/language/read_file` - Read file with structural windowing
- `POST /api/tools/language/skeleton` - Get file skeleton
- `POST /api/tools/language/diff` - Generate function-anchored diff
- `POST /api/tools/language/apply_patch` - Apply anchored patch
- `POST /api/tools/language/create_file` - Create code file with validation
- `POST /api/tools/language/index` - Index workspace symbols
- `POST /api/tools/language/search_symbols` - Search indexed symbols
- `POST /api/tools/language/reference_graph` - Build reference graph
- `POST /api/tools/language/validate` - Validate syntax/lint
- `POST /api/tools/skills/list` - List locally installed skills
- `POST /api/tools/skills/read` - Read SKILL.md content
- `POST /api/tools/skills/read_file` - Read a specific skill file
- `POST /api/tools/skills/search` - Search remote skills registry
- `POST /api/tools/skills/install` - Install skill from remote repo (HITL-gated)
- `POST /api/tools/memory/store` - Store a knowledge node
- `POST /api/tools/memory/get` - Retrieve a node with relations
- `POST /api/tools/memory/search` - Full-text search knowledge graph
- `POST /api/tools/memory/update` - Update node content or metadata
- `POST /api/tools/memory/delete` - Delete a node (HITL-gated)
- `POST /api/tools/memory/link` - Create a typed edge between nodes
- `POST /api/tools/memory/children` - Get child nodes via parent_of edges
- `POST /api/tools/memory/ancestors` - Traverse upward via parent_of edges
- `POST /api/tools/memory/roots` - Get all root nodes
- `POST /api/tools/memory/related` - Get all connected nodes
- `POST /api/tools/memory/subtree` - Get full descendant subtree
- `POST /api/tools/memory/stats` - Knowledge graph metrics
- `POST /api/tools/plan/create` - Create a DAG-based orchestration plan
- `POST /api/tools/plan/execute` - Return current ready tasks
- `POST /api/tools/plan/update_task` - Update one task status
- `POST /api/tools/plan/status` - Get plan and task status
- `POST /api/tools/plan/list` - List all plans
- `POST /api/tools/plan/cancel` - Cancel a plan

### Admin API Endpoints

- `POST /admin/api/login` - Create admin session (returns token + cookie)
- `GET /admin/api/health` - System health (admin auth required)
- `GET /admin/api/secrets` - List loaded secret key names (admin auth required)
- `POST /admin/api/secrets/reload` - Reload secrets from file (admin auth required)
- `GET /admin/api/llm/endpoints` - List sanitized configured LLM endpoints (admin auth required)
- `POST /admin/api/llm/test` - Test one configured LLM endpoint (admin auth required)
- Protected admin endpoints accept session cookie or `Authorization: Bearer <token>`

## Plan Tools (DAG Orchestration)

### Creating Plans

**"Create a plan to write a file and then read it back"**
- Creates a DAG with two tasks where read depends on write
- Returns plan_id, execution order, and validation status

**"Set up a parallel execution plan: write two files, then merge their contents"**
- Tasks without dependencies run concurrently
- Merge task waits for both write tasks to complete

**"Create a plan with cycle detection: task A depends on B, B depends on A"**
- This will fail with validation error - cycles are detected at creation time

### Executing Plans

**"Execute the plan I just created"**
- Returns the tasks that are currently ready to run
- Prefer passing `plan_id` returned by `plan_create`
- Unique plan names are accepted only when exactly one plan matches
- Returns `ready_tasks`, plan status, and task counters

**"After I run a task, mark it completed and get next ready tasks"**
- Call `plan_update_task` with `status: "completed"` and `output`
- Response includes updated counts and newly ready downstream tasks

**"Mark a task as failed and apply failure policy"**
- Call `plan_update_task` with `status: "failed"` and `error`
- Server applies `stop`, `skip_dependents`, or `continue` automatically

### Plan Status and Management

**"Show me the status of plan abc123"**
- Returns plan status (pending/running/completed/failed/cancelled)
- Per-task progress with outputs and errors
- Task counts: total, completed, failed, skipped, running

**"List all plans"**
- Shows all plans with names, status, task counts, timestamps

**"Cancel the running plan"**
- Marks all pending/running tasks as skipped
- Sets plan status to cancelled

### Task References

**"Use the output from task A as input to task B"**
- Reference syntax: `{{task:task_a_id.output_field}}`
- Resolved before task B executes
- Preserves types (dict, list, int, etc.) for full references

### Failure Handling

**"Create a plan that stops all tasks if any task fails"**
- Use `on_failure: "stop"` (default policy)

**"Create a plan that skips only dependent tasks on failure"**
- Use `on_failure: "skip_dependents"` - independent tasks continue

**"Create a plan that continues all tasks regardless of failures"**
- Use `on_failure: "continue"` - all tasks run

### HITL in Plans

**"Create a plan where `git_push` is HITL-tagged for my orchestrator"**
- Set `require_hitl: true` on the task definition
- `plan_execute` exposes that flag in each `ready_task`
- External orchestrator decides how to enforce approval

### Curl Examples

```bash
# Create a sequential plan
curl -X POST http://localhost:8080/api/tools/plan/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "write-then-read",
    "tasks": [
      {"id": "write", "name": "Write file", "tool_category": "fs", "tool_name": "write", "params": {"path": "test.txt", "content": "Hello"}},
      {"id": "read", "name": "Read file", "tool_category": "fs", "tool_name": "read", "params": {"path": "test.txt"}, "depends_on": ["write"]}
    ]
  }'

# Get ready tasks for a plan
curl -X POST http://localhost:8080/api/tools/plan/execute \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id>"}'

# Mark task as running
curl -X POST http://localhost:8080/api/tools/plan/update_task \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id>", "task_id": "write", "status": "running"}'

# Mark task as completed and retrieve next ready tasks
curl -X POST http://localhost:8080/api/tools/plan/update_task \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id>", "task_id": "write", "status": "completed", "output": {"ok": true}}'

# Mark task as failed
curl -X POST http://localhost:8080/api/tools/plan/update_task \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id>", "task_id": "write", "status": "failed", "error": "write failed"}'

# Check plan status
curl -X POST http://localhost:8080/api/tools/plan/status \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id>"}'

# List all plans
curl -X POST http://localhost:8080/api/tools/plan/list \
  -H "Content-Type: application/json" -d '{}'

# Cancel a plan
curl -X POST http://localhost:8080/api/tools/plan/cancel \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id>"}'
```

---

**Note:** The actual behavior of these commands depends on:
- Your workspace configuration and mounted volumes
- Policy rules defined in `config.yaml`
- HITL settings and approval requirements
- The specific LLM client you're using (Open WebUI, Claude Desktop, etc.)
