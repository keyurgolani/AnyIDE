# AnyIDE User Guide

**Complete guide for using AnyIDE with LLM applications**

Version: 0.1.0
Last Updated: March 1, 2026

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Protocol Support](#protocol-support)
4. [Admin Dashboard](#admin-dashboard)
5. [Tool Categories](#tool-categories)
   - [Filesystem Tools](#filesystem-tools)
   - [Shell Execution](#shell-execution)
   - [Git Tools](#git-tools)
   - [Docker Tools](#docker-tools)
   - [HTTP Tools](#http-tools)
   - [Memory Tools (Knowledge Graph)](#memory-tools-knowledge-graph)
   - [Plan Tools (DAG Execution)](#plan-tools-dag-execution)
   - [Workspace Tools](#workspace-tools)
6. [Secrets Management](#secrets-management)
7. [Human-in-the-Loop (HITL)](#human-in-the-loop-hitl)
8. [Security Model](#security-model)
9. [Advanced Workflows](#advanced-workflows)
10. [Troubleshooting](#troubleshooting)
11. [API Reference](#api-reference)

---

## Introduction

AnyIDE is a self-hosted tool server that exposes host-machine capabilities to LLM applications. It provides a unified interface for AI assistants to interact with your development environment through industry-standard protocols.

### Key Features

- **Dual Protocol Support**: MCP (Model Context Protocol) and OpenAPI (REST) simultaneously
- **Comprehensive Tooling**: Filesystem, shell, git, docker, HTTP, memory graph, and plan execution
- **Human Oversight**: Built-in admin dashboard with HITL approval workflows
- **Security First**: Workspace boundaries, SSRF protection, audit logging, and secret management
- **Production Ready**: Docker container with health checks, logging, and monitoring

### Use Cases

- **AI-Assisted Development**: Let AI assistants read, write, and manage your codebase
- **Infrastructure Management**: Control Docker containers and execute shell commands
- **Knowledge Management**: Build and query a persistent knowledge graph
- **Automated Workflows**: Create and execute multi-step plans with dependency management

---

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Git (for repository operations)
- Port 8080 available (or configure custom port)

### Launch AnyIDE

```bash
# Clone the repository
git clone https://github.com/keyurgolani/AnyIDE.git
cd AnyIDE

# Start the container
docker compose up -d

# Verify it's running
curl http://localhost:8080/health
```

### Access the Admin Dashboard

```
URL: http://localhost:8080/admin/
Default Password: admin
```

### Test Your First Tool Call

```bash
# Read a file
curl -X POST http://localhost:8080/api/tools/fs/read \
  -H "Content-Type: application/json" \
  -d '{"path": "README.md"}'

# List workspace contents
curl -X POST http://localhost:8080/api/tools/fs/list \
  -H "Content-Type: application/json" \
  -d '{"path": "."}'
```

---

## Protocol Support

AnyIDE exposes all tools through two industry-standard protocols simultaneously:

### MCP (Model Context Protocol)

Modern protocol for AI tool integration using Streamable HTTP transport.

**Endpoint**: `http://localhost:8080/mcp`

**Compatible Clients**:
- Claude Desktop
- Cursor
- Continue.dev
- Any MCP-compatible client

**Configuration Example (Claude Desktop)**:
```json
{
  "mcpServers": {
    "anyide": {
      "url": "http://localhost:8080/mcp",
      "transport": "streamable-http"
    }
  }
}
```

### OpenAPI (REST)

Traditional HTTP REST API for broad compatibility.

**Base URL**: `http://localhost:8080/api/tools/`

**Compatible Clients**:
- Open WebUI
- Custom applications
- Any HTTP client

**Example Request**:
```bash
curl -X POST http://localhost:8080/api/tools/fs/read \
  -H "Content-Type: application/json" \
  -d '{"path": "README.md"}'
```

### Protocol Parity

Both protocols expose identical tools from a single source of truth. There is no code duplication - choose the protocol that best fits your client.

---

## Admin Dashboard

The admin dashboard provides human oversight, HITL management, and system monitoring.

### Access

```
URL: http://localhost:8080/admin/
Default Password: admin (change via ADMIN_PASSWORD env var)
```

### Dashboard Features

#### Unified Dashboard View
- **HITL Approval Queue Widget**: See pending requests, approve/reject directly
- **System Health Widget**: Monitor uptime, error rates, and metrics in real-time
- **Recent Activity Widget**: View last 5 tool executions with status badges

#### Dedicated Pages
- **HITL Queue**: Full request details with countdown timers
- **Audit Log**: Searchable history with export (JSON/CSV)
- **System Health**: CPU, memory, database, and workspace metrics
- **Tool Explorer**: Browse all tools with JSON schemas
- **Containers**: Docker container list with log viewer
- **Secrets**: View secret keys and trigger hot reload
- **Configuration**: View current server settings

### Dashboard Capabilities

- Real-time updates via WebSocket (no page refresh needed)
- Expandable/collapsible widgets for flexible monitoring
- Fully responsive design (mobile, tablet, desktop)
- Automatic redirect to login on session expiry
- Browser notifications for HITL requests

---

## Tool Categories

### Filesystem Tools

Manage files and directories within the workspace boundary.

#### fs_read

Read file contents with optional line ranges and encoding support.

**Natural Language Examples**:
- "Read the contents of README.md"
- "Show me the first 10 lines of example.txt"
- "Read lines 5 through 15 of test.txt"

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/fs/read \
  -H "Content-Type: application/json" \
  -d '{
    "path": "anyide/main.py",
    "start_line": 1,
    "end_line": 50,
    "encoding": "utf-8"
  }'
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| path | string | Yes | Relative path from workspace root |
| start_line | integer | No | First line to read (1-indexed) |
| end_line | integer | No | Last line to read |
| encoding | string | No | File encoding (default: utf-8) |

#### fs_write

Write, overwrite, or append to files with automatic directory creation.

**Natural Language Examples**:
- "Create a new file called hello.txt with content 'Hello, World!'"
- "Append 'New line' to the end of log.txt"
- "Overwrite config.yaml with new settings"

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/fs/write \
  -H "Content-Type: application/json" \
  -d '{
    "path": "output/result.txt",
    "content": "Processing complete",
    "mode": "overwrite",
    "create_dirs": true
  }'
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| path | string | Yes | Relative path from workspace root |
| content | string | Yes | Content to write |
| mode | string | No | "overwrite" (default), "append", or "create" |
| create_dirs | boolean | No | Create parent directories if needed |

**HITL Triggers**: Writing to `.conf`, `.env`, `.yaml`, `.yml` files requires approval.

#### fs_list

List directory contents with recursive traversal and filtering.

**Natural Language Examples**:
- "List all files in the current directory"
- "Show me all Python files recursively"
- "List files in anyide/components up to 2 levels deep"

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/fs/list \
  -H "Content-Type: application/json" \
  -d '{
    "path": "src",
    "recursive": true,
    "max_depth": 3,
    "pattern": "*.py"
  }'
```

#### fs_search

Search files by name or content with regex support.

**Natural Language Examples**:
- "Find all files with 'test' in the name"
- "Search for files containing 'TODO'"
- "Find Python files containing 'import requests'"

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/fs/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "TODO",
    "search_type": "content",
    "path": "src",
    "file_pattern": "*.py"
  }'
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| query | string | Yes | Search term or regex pattern |
| search_type | string | No | "filename", "content", or "both" |
| path | string | No | Directory to search (default: workspace root) |
| file_pattern | string | No | Glob pattern to filter files |
| case_sensitive | boolean | No | Case-sensitive search (default: false) |

---

### Shell Execution

Execute shell commands with security controls and allowlisting.

#### shell_execute

**Natural Language Examples**:
- "Run 'ls -la' to see all files"
- "Execute 'python --version' to check Python version"
- "Run 'git status' in the project directory"

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/shell/execute \
  -H "Content-Type: application/json" \
  -d '{
    "command": "npm test",
    "working_directory": "frontend",
    "timeout": 60,
    "env": {"NODE_ENV": "test"}
  }'
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| command | string | Yes | Shell command to execute |
| working_directory | string | No | Directory to run command in |
| timeout | integer | No | Timeout in seconds (default: 30) |
| env | object | No | Environment variables |

**Security Model**:
- **Allowlisted commands** execute immediately: `ls`, `cat`, `echo`, `git`, `python`, `npm`, `docker`, etc.
- **Dangerous patterns** require HITL approval: pipes (`|`), redirects (`>`, `<`), semicolons (`;`), background (`&`)
- **Secret injection**: Use `{{secret:KEY}}` in env values for secure credential handling

**Example with Secrets**:
```bash
curl -X POST http://localhost:8080/api/tools/shell/execute \
  -H "Content-Type: application/json" \
  -d '{
    "command": "git push origin main",
    "env": {"GIT_TOKEN": "{{secret:GITHUB_TOKEN}}"}
  }'
```

---

### Git Tools

Complete Git repository management with credential support.

#### Read Operations (No Approval Required)

| Tool | Description | Example |
|------|-------------|---------|
| git_status | Repository status | "What's the git status?" |
| git_log | Commit history | "Show the last 10 commits" |
| git_diff | File differences | "Show uncommitted changes" |
| git_show | Commit details | "Show details of commit abc123" |
| git_list_branches | Branch listing | "List all branches" |
| git_remote | Remote management | "List configured remotes" |
| git_stash | Stash operations (list) | "List all stashes" |

#### Write Operations (HITL Required)

| Tool | Description | Example |
|------|-------------|---------|
| git_commit | Create commits | "Commit with message 'Add feature'" |
| git_push | Push to remote | "Push to origin main" |
| git_checkout | Switch branches | "Checkout the develop branch" |
| git_branch | Create/delete branches | "Create branch feature-x" |

#### Authenticated Operations

Use secret templates for private repository access:

```bash
# Push with authentication
curl -X POST http://localhost:8080/api/tools/git/push \
  -H "Content-Type: application/json" \
  -d '{
    "repo_path": ".",
    "remote": "origin",
    "branch": "main",
    "username": "{{secret:GIT_USER}}",
    "token": "{{secret:GITHUB_TOKEN}}"
  }'
```

---

### Docker Tools

Container management and monitoring.

#### docker_list

List containers with filtering options.

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/docker/list \
  -H "Content-Type: application/json" \
  -d '{
    "all": true,
    "filters": {"status": "running"}
  }'
```

#### docker_inspect

Get detailed container information.

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/docker/inspect \
  -H "Content-Type: application/json" \
  -d '{"container": "anyide"}'
```

#### docker_logs

Retrieve container logs.

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/docker/logs \
  -H "Content-Type: application/json" \
  -d '{
    "container": "anyide",
    "tail": 100,
    "since": "2024-01-01T00:00:00Z"
  }'
```

#### docker_action (HITL Required)

Control container lifecycle.

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/docker/action \
  -H "Content-Type: application/json" \
  -d '{
    "container": "nginx",
    "action": "restart",
    "timeout": 30
  }'
```

**Available Actions**: `start`, `stop`, `restart`, `pause`, `unpause`

---

### HTTP Tools

Make outbound HTTP requests with SSRF protection.

#### http_request

**API Call**:
```bash
curl -X POST http://localhost:8080/api/tools/http/request \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://api.github.com/user",
    "method": "GET",
    "headers": {
      "Authorization": "Bearer {{secret:GITHUB_TOKEN}}",
      "Accept": "application/json"
    },
    "timeout": 30
  }'
```

**Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| url | string | Yes | Target URL |
| method | string | No | HTTP method (default: GET) |
| headers | object | No | Request headers |
| body | string | No | Request body |
| timeout | integer | No | Timeout in seconds |

**SSRF Protection**:
- Private IP ranges blocked: `10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`
- Loopback blocked: `127.x.x.x`, `localhost`
- Cloud metadata blocked: `169.254.169.254`

**Domain Filtering** (configured in `config.yaml`):
```yaml
http:
  allow_domains: []  # Empty = allow all non-blocked
  block_domains:
    - "*.internal.example.com"
```

---

### Memory Tools (Knowledge Graph)

Persistent knowledge storage with full-text search and graph traversal.

#### Core Operations

| Tool | Description | HITL |
|------|-------------|------|
| memory_store | Store a knowledge node | No |
| memory_get | Retrieve node by ID | No |
| memory_search | Full-text search (FTS5) | No |
| memory_update | Update node content/metadata | No |
| memory_delete | Delete a node | Yes |
| memory_link | Create typed edge between nodes | No |
| memory_stats | Graph statistics | No |

#### Graph Traversal

| Tool | Description |
|------|-------------|
| memory_children | Get direct children via `parent_of` edges |
| memory_ancestors | Traverse upward via `parent_of` edges |
| memory_roots | Get all root nodes (no incoming `parent_of`) |
| memory_related | Get all connected nodes (any edge type) |
| memory_subtree | Get full descendant subtree |

#### Example Workflow

```bash
# Store knowledge nodes
curl -X POST http://localhost:8080/api/tools/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Python",
    "content": "High-level programming language",
    "entity_type": "technology",
    "tags": ["programming", "language"]
  }'

curl -X POST http://localhost:8080/api/tools/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "name": "FastAPI",
    "content": "Modern Python web framework",
    "entity_type": "framework",
    "tags": ["web", "api"]
  }'

# Create relationship
curl -X POST http://localhost:8080/api/tools/memory/link \
  -H "Content-Type: application/json" \
  -d '{
    "source_id": "<python-node-id>",
    "target_id": "<fastapi-node-id>",
    "relation": "parent_of"
  }'

# Search
curl -X POST http://localhost:8080/api/tools/memory/search \
  -H "Content-Type: application/json" \
  -d '{"query": "programming language"}'
```

---

### Plan Tools (DAG Execution)

Multi-step workflow execution with dependency management.

#### Creating Plans

```bash
curl -X POST http://localhost:8080/api/tools/plan/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "deploy-workflow",
    "tasks": [
      {
        "id": "build",
        "name": "Build application",
        "tool_category": "shell",
        "tool_name": "execute",
        "params": {"command": "npm run build"}
      },
      {
        "id": "test",
        "name": "Run tests",
        "tool_category": "shell",
        "tool_name": "execute",
        "params": {"command": "npm test"},
        "depends_on": ["build"]
      },
      {
        "id": "deploy",
        "name": "Deploy to production",
        "tool_category": "shell",
        "tool_name": "execute",
        "params": {"command": "npm run deploy"},
        "depends_on": ["test"],
        "require_hitl": true
      }
    ]
  }'
```

#### Task References

Use outputs from previous tasks:

```json
{
  "id": "notify",
  "params": {
    "message": "Build {{task:build.output}} completed"
  }
}
```

#### Failure Policies

| Policy | Behavior |
|--------|----------|
| `stop` | Abort all tasks on failure (default) |
| `skip_dependents` | Skip dependent tasks, continue others |
| `continue` | Run all tasks regardless of failures |

#### Executing Plans

```bash
# Execute by plan_id (preferred)
curl -X POST http://localhost:8080/api/tools/plan/execute \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "<plan-id-from-create>"}'

# Execute by unique name
curl -X POST http://localhost:8080/api/tools/plan/execute \
  -H "Content-Type: application/json" \
  -d '{"plan_id": "deploy-workflow"}'
```

---

### Workspace Tools

Get workspace information and manage secrets.

#### workspace_info

```bash
curl -X POST http://localhost:8080/api/tools/workspace/info \
  -H "Content-Type: application/json" -d '{}'
```

Returns workspace directory, available paths, disk usage, and tool categories.

#### workspace_secrets_list

```bash
curl -X POST http://localhost:8080/api/tools/workspace/secrets/list \
  -H "Content-Type: application/json" -d '{}'
```

Returns list of loaded secret key names (values never exposed).

---

## Secrets Management

### Secret Templates

Use `{{secret:KEY}}` syntax to inject secrets into any tool parameter:

```bash
# HTTP Authorization header
curl -X POST http://localhost:8080/api/tools/http/request \
  -d '{"url": "https://api.example.com", "headers": {"Authorization": "Bearer {{secret:API_KEY}}"} }'

# Shell environment variable
curl -X POST http://localhost:8080/api/tools/shell/execute \
  -d '{"command": "git push", "env": {"GIT_TOKEN": "{{secret:GITHUB_TOKEN}}"}}'

# Git credentials
curl -X POST http://localhost:8080/api/tools/git/push \
  -d '{"token": "{{secret:GITHUB_TOKEN}}"}'
```

### Secrets File

Create `secrets.env` with your sensitive values:

```bash
# secrets.env
GITHUB_TOKEN=ghp_your_token_here
DB_PASSWORD=your_db_password
API_KEY=your_api_key
```

Mount as read-only in docker-compose.yaml:

```yaml
volumes:
  - ./secrets.env:/secrets/secrets.env:ro
```

### Security Guarantees

- Secrets are resolved server-side before execution
- Original templates (not resolved values) appear in audit logs
- Secret values are never returned in API responses
- Secret keys can be listed, but values are never exposed

---

## Human-in-the-Loop (HITL)

### Overview

HITL provides approval workflows for sensitive operations. When triggered:

1. Tool execution pauses
2. Request appears in admin dashboard
3. Admin approves or rejects
4. Tool completes or returns rejection error

### HITL Triggers

| Category | Triggers |
|----------|----------|
| Filesystem | Writing `.conf`, `.env`, `.yaml`, `.yml` files |
| Shell | Commands with pipes, redirects, or not in allowlist |
| Git | `commit`, `push`, `checkout`, branch `delete` |
| Docker | `docker_action` (start, stop, restart, pause, unpause) |
| Memory | `memory_delete` |
| Plan | Tasks with `require_hitl: true` |

### Approval Workflow

1. **Request Created**: Appears in HITL Queue widget with yellow glow
2. **Countdown Timer**: Shows remaining time (default 5 minutes)
3. **Admin Reviews**: See full request details including parameters
4. **Decision Made**:
   - **Approve**: Tool executes and returns result
   - **Reject**: Tool returns rejection error
   - **Timeout**: Auto-rejects (configurable)

### Dashboard Notifications

- Real-time WebSocket updates (no refresh needed)
- Browser notifications (if permitted)
- Sound alerts (configurable)
- Pending count badge in navigation

---

## Security Model

### Defense Layers

1. **Docker Isolation**: Container boundary
2. **Workspace Boundary**: All paths validated and confined
3. **Policy Engine**: Allow/block/HITL per tool
4. **HITL Approval**: Human review for sensitive operations
5. **Secret Isolation**: Server-side resolution, never exposed
6. **SSRF Protection**: Private IPs and metadata endpoints blocked
7. **Audit Logging**: Complete request/response history

### Workspace Security

```yaml
# All file operations are constrained to workspace
workspace:
  base_dir: /workspace

# Path traversal attempts are blocked
# /etc/passwd → BLOCKED (outside workspace)
# ../../../etc/passwd → BLOCKED (path traversal)
# symlink_escape → BLOCKED (post-resolution check)
```

### Network Security

```yaml
http:
  block_private_ips: true      # Block RFC 1918 ranges
  block_metadata_endpoints: true  # Block 169.254.169.254
  allow_domains: []            # Empty = allow all non-blocked
  block_domains: []            # Additional blocked domains
```

---

## Advanced Workflows

### Multi-Step File Processing

```bash
# Natural language request:
# "Read the config file, update the database URL, and write it back"

# This translates to:
# 1. fs_read config.yaml
# 2. (LLM processes content)
# 3. fs_write config.yaml (triggers HITL)
```

### Parallel Plan Execution

```json
{
  "name": "parallel-builds",
  "tasks": [
    {"id": "build-api", "tool_category": "shell", "tool_name": "execute", "params": {"command": "cd api && npm build"}},
    {"id": "build-web", "tool_category": "shell", "tool_name": "execute", "params": {"command": "cd web && npm build"}},
    {"id": "combine", "tool_category": "shell", "tool_name": "execute", "params": {"command": "npm run combine"}, "depends_on": ["build-api", "build-web"]}
  ]
}
```

### Conditional Container Management

```bash
# Natural language request:
# "Check if the database container is running, and if not, start it"

# This involves:
# 1. docker_list with status filter
# 2. (LLM evaluates result)
# 3. docker_action if needed (triggers HITL)
```

---

## Troubleshooting

### Common Issues

#### Path Outside Workspace

**Error**: `Path resolves outside workspace boundary`

**Solution**: Use relative paths from workspace root, not absolute paths.

#### HITL Timeout

**Error**: `HITL request expired`

**Solution**: Approve requests within the TTL window (default 5 minutes). Increase `HITL_TTL_SECONDS` if needed.

#### SSRF Blocked

**Error**: `SSRF protection: private IP address blocked`

**Solution**: Use public URLs only. Private IPs are blocked for security.

#### Secret Not Found

**Error**: `Secret 'KEY' not found`

**Solution**: Verify the key exists in `secrets.env` and the file is mounted correctly.

### Debug Commands

```bash
# Check container health
curl http://localhost:8080/health

# View container logs
docker compose logs anyide -f

# List loaded secrets (keys only)
curl -X POST http://localhost:8080/api/tools/workspace/secrets/list \
  -H "Content-Type: application/json" -d '{}'

# Check workspace info
curl -X POST http://localhost:8080/api/tools/workspace/info \
  -H "Content-Type: application/json" -d '{}'
```

### Log Analysis

```bash
# Find HITL-related logs
docker compose logs anyide | grep -i hitl

# Find error messages
docker compose logs anyide | grep -i error

# Follow live logs
docker compose logs anyide -f --tail 100
```

---

## API Reference

### OpenAPI Documentation

Interactive API documentation available at:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc
- **OpenAPI Spec**: http://localhost:8080/openapi.json

### MCP Tools

When using MCP clients, tools are identified by operation IDs:

| Tool | MCP Name |
|------|----------|
| Health check | `health_check_health_get` |
| Read file | `fs_read` |
| Write file | `fs_write` |
| List directory | `fs_list` |
| Search files | `fs_search` |
| Execute shell | `shell_execute` |
| Git status | `git_status` |
| Git log | `git_log` |
| Git diff | `git_diff` |
| Git commit | `git_commit` |
| Git push | `git_push` |
| Docker list | `docker_list` |
| Docker inspect | `docker_inspect` |
| Docker logs | `docker_logs` |
| Docker action | `docker_action` |
| HTTP request | `http_request` |
| Memory store | `memory_store` |
| Memory search | `memory_search` |
| Plan create | `plan_create` |
| Plan execute | `plan_execute` |

### REST Endpoints

All tools follow the pattern: `POST /api/tools/{category}/{tool_name}`

```
POST /api/tools/fs/read
POST /api/tools/fs/write
POST /api/tools/fs/list
POST /api/tools/fs/search
POST /api/tools/shell/execute
POST /api/tools/git/status
POST /api/tools/git/log
POST /api/tools/git/diff
POST /api/tools/git/commit
POST /api/tools/git/push
POST /api/tools/docker/list
POST /api/tools/docker/inspect
POST /api/tools/docker/logs
POST /api/tools/docker/action
POST /api/tools/http/request
POST /api/tools/memory/store
POST /api/tools/memory/search
POST /api/tools/plan/create
POST /api/tools/plan/execute
POST /api/tools/workspace/info
```

### Admin API Endpoints

```
POST /admin/api/login           # Authenticate
POST /admin/api/logout          # End session
GET  /admin/api/health          # System health
GET  /admin/api/secrets         # List secret keys
POST /admin/api/secrets/reload  # Reload secrets file
GET  /admin/api/audit           # Audit log (with filters)
GET  /admin/api/audit/export    # Export audit log
GET  /admin/api/config          # View configuration
GET  /admin/api/hitl/pending    # Pending HITL requests
POST /admin/api/hitl/decide     # Approve/reject HITL
```

---

## Tips for LLM Interaction

When working with an LLM that has access to AnyIDE tools:

1. **Be specific about paths** - Use relative paths from workspace root
2. **Specify your intent clearly** - "Create" vs "Overwrite" vs "Append"
3. **Check before destructive operations** - Ask to read before overwriting
4. **Use natural language** - The LLM translates requests to tool calls
5. **Combine operations** - Multi-step workflows in a single request
6. **Understand HITL** - Some operations require your approval in the dashboard

---

## Additional Resources

- **README.md** - Project overview and setup
- **docs/TOOL_CATALOG.md** - Auto-generated tool reference
- **docs/LLM_SYSTEM_PROMPT.md** - System prompt template for LLMs
- **docs/DOCKER_HUB_PUBLISHING.md** - Docker image publishing guide
- **admin/README.md** - Admin dashboard documentation
- **examples/** - Configuration examples and production templates

---

**AnyIDE** - Self-hosted tool server for LLM applications
**Version**: 0.1.0
**Repository**: https://github.com/keyurgolani/AnyIDE
