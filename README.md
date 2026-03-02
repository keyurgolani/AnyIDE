# AnyIDE

**Self-hosted tool server exposing host-machine capabilities to LLM clients via MCP and OpenAPI protocols**

Version: 0.1.0  
Status: ✅ Production Ready

---

## Overview

AnyIDE is a single Docker container that exposes host-machine management capabilities to LLM applications via two industry-standard protocols simultaneously:

- **MCP (Model Context Protocol)** over Streamable HTTP
- **OpenAPI (REST/JSON)** for tools like Open WebUI

Built-in admin dashboard provides human oversight, HITL (Human-in-the-Loop) approval workflows, audit logging, and secret management.

---

## Features

### ✅ Implemented

- **Dual Protocol Support:** MCP + OpenAPI simultaneously
- **Modular Tool Loading:** Enable/disable tool categories at startup via `ANYIDE_MODULES` or `config.yaml`
- **Filesystem Tools:** 
  - Read and write files with workspace sandboxing
  - List directory contents with recursive traversal
  - Search files by name or content with regex support
- **Shell Execution:** Execute commands with security controls and allowlisting
- **Git Tools:** Complete Git repository management
  - Status, log, diff, show, branches, remotes
  - Commit, push, pull, checkout, stash operations
  - HITL approval for write operations
  - Git credential support with `{{secret:KEY}}` templates for authenticated push/pull
  - Secure GIT_ASKPASS implementation with ephemeral scripts
- **Docker Tools:** Container management and monitoring
  - List containers with filtering (running, stopped, by name/status)
  - Inspect container details (config, network, mounts, state)
  - Retrieve container logs with tail and timestamp filtering
  - Control container lifecycle (start, stop, restart, pause, unpause)
  - HITL approval for destructive operations
  - Docker socket integration with security controls
- **Language Tools (Tree-sitter + LSP):** IDE-grade structural code tooling
  - `lang_skeleton` and `lang_read_file` for structure-aware code navigation
  - `lang_diff` and `lang_apply_patch` for function-anchored edit workflows with backup + validation
  - `lang_create_file`, `lang_validate`, `lang_index`, `lang_search_symbols`, `lang_reference_graph`
  - `lang_validate` supports syntax/lint/type checks (`pyright` + `typescript-language-server` when configured)
  - `lang_reference_graph` adds semantic cross-file edges for JavaScript/TypeScript via LSP
  - `lang_read_file` includes optional LSP hover/go-to-definition enrichments
  - LSP process lifecycle includes lazy startup, initialize handshake, timeout recovery, and restart on crash
  - Incremental SQLite-backed symbol index and baseline linter routing (ruff for Python)
- **Skills Module:** Isolated `/skills` storage and skills.sh integration
  - Offline-capable local tools: `skills_list`, `skills_read`, `skills_read_file`
  - Online tools: `skills_search` (`npx skills find ... --json`) and HITL-gated `skills_install`
  - `skills_install` uses project-scope installs under `/skills` (commonly `/skills/.agents/skills/<name>`)
  - `skills_list/read/read_file` discover skills from both `/skills/<name>` and `/skills/.agents/skills/<name>`
  - Robust CLI parsing/error normalization (JSON + ANSI/plaintext fallback for search output)
- **Subagent Module:** Config-driven specialist subagents backed by the unified LLM client
  - `subagent_list` discovers configured subagent types
  - `subagent_run` executes single-turn prompt templates with endpoint/model selection
  - Response metadata includes model, endpoint, token usage, latency, and configured JSON mode
  - Per-type override controls gate `override_model` and `override_temperature`
  - Policy integration supports allow/block/HITL controls for `subagent_list` and `subagent_run`
- **Workspace Management:** Secure path resolution and boundary enforcement
- **HITL System:** Real-time approval workflow for sensitive operations
- **Admin Dashboard:** Premium UI with real-time updates
  - Automatic redirect to login when admin session expires
  - Subpath-aware API and WebSocket routing (`/my-prefix/admin` deployments)
  - Header-based auth fallback for restricted-cookie browser scenarios
  - Resilient WebSocket message queueing during initial connect/reconnect
- **Audit Logging:** Complete execution history
- **Policy Engine:** Allow/block/HITL rules per tool
- **Secret Management:** Secure secret resolution with `{{secret:KEY}}` template syntax
- **System LLM Capability (Admin-Managed):** Central `llm.endpoints` config with provider adapters (OpenAI/OpenAI-compatible/Ollama, Anthropic, Google) for internal modules
  - Exposed through admin/config surfaces only, not as `/api/tools/*` endpoints
- **HTTP Client:** Make outbound HTTP requests with SSRF protection, domain filtering, and secret injection
- **Knowledge Graph Memory:** 12 tools for persistent knowledge storage with FTS5 search and graph traversal
  - Improved natural-language memory search recall (question-style queries)
- **Plan Orchestration:** DAG-based multi-step workflows with ready-task discovery, task references, and failure handling
  - External orchestrators execute tasks; backend tracks plan/task state
  - Plan reference resolution by `plan_id` (preferred) or unique plan name with ambiguity protection
- **WebSocket Support:** Real-time notifications
- **Operational Documentation:** Docker Hub publishing guide, LLM system prompt template, and auto-generated tool catalog
- **Deployment Examples:** Production compose file, policy-oriented config variants, and secrets template
- **Expanded Test Suites:** Unit, integration, security, and load-test coverage

### ✅ Admin Dashboard Enhancements (Complete)

- **Tool Explorer:** Browse and inspect all available tools with their JSON schemas
  - Tool list built from OpenAPI contract (not reflection)
  - Accurate HITL indicators from effective policy configuration
  - Input/output schemas populated from request/response models
- **Configuration Viewer:** View current server configuration and HTTP settings
- **Secrets Management:** View loaded secret keys and trigger hot reload from the UI
- **Enhanced System Health:** Real-time CPU, memory, database, and workspace metrics
- **Audit Log Enhancements:**
  - Export filtered logs as JSON or CSV
  - Real-time WebSocket streaming with polling fallback
  - Live connection status indicator (Live/Polling/Offline)
  - New log notification badges
- **Real-time Audit Stream:** WebSocket endpoint for live audit event streaming
- **Browser Notifications:** Desktop alerts for HITL approval requests
- **Container Log Viewer:** Dedicated page to browse containers and view their logs
- **Mobile Responsive:** Full responsive design for all device sizes

### ✅ MCP Protocol Improvements

- **Tool Parity:** All tools (including Docker) are now exposed via MCP with OpenAPI parity
- **Scope Restriction:** MCP only exposes tool endpoints, excluding admin/auth/system routes
- **Regression Tests:** Automated tests verify MCP and OpenAPI tool lists match

---

## Quick Start

### 1. Start the Container

```bash
docker compose up -d
```

### 2. Access the Admin Dashboard

```
http://localhost:8080/admin/
```

**Default Password:** `admin`
- Password precedence: `ANYIDE_ADMIN_PASSWORD` > `ADMIN_PASSWORD` (legacy) > `config.yaml auth.admin_password` > default `admin`.

The dashboard provides a unified view with expandable widgets:
- HITL Approval Queue (approve/reject directly from dashboard)
- System Health (real-time metrics and status)
- Recent Activity (last 5 tool executions)

Click widget headers to expand/collapse sections, or use "View All" buttons to navigate to dedicated pages for detailed analysis.

### 3. Test the Tools

```bash
# Read a file
curl -X POST http://localhost:8080/api/tools/fs/read \
  -H "Content-Type: application/json" \
  -d '{"path": "README.md"}'

# List directory contents
curl -X POST http://localhost:8080/api/tools/fs/list \
  -H "Content-Type: application/json" \
  -d '{"path": ".", "recursive": true}'

# Search for files
curl -X POST http://localhost:8080/api/tools/fs/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "search_type": "both"}'

# Execute a shell command
curl -X POST http://localhost:8080/api/tools/shell/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "ls -la"}'

# Check git repository status
curl -X POST http://localhost:8080/api/tools/git/status \
  -H "Content-Type: application/json" \
  -d '{"repo_path": "."}'

# View git commit history
curl -X POST http://localhost:8080/api/tools/git/log \
  -H "Content-Type: application/json" \
  -d '{"repo_path": ".", "max_count": 10}'

# List Docker containers
curl -X POST http://localhost:8080/api/tools/docker/list \
  -H "Content-Type: application/json" \
  -d '{"all": true}'

# Inspect a Docker container
curl -X POST http://localhost:8080/api/tools/docker/inspect \
  -H "Content-Type: application/json" \
  -d '{"container": "anyide"}'

# Get Docker container logs
curl -X POST http://localhost:8080/api/tools/docker/logs \
  -H "Content-Type: application/json" \
  -d '{"container": "anyide", "tail": 50}'

# Write a file (triggers HITL for .conf files)
curl -X POST http://localhost:8080/api/tools/fs/write \
  -H "Content-Type: application/json" \
  -d '{"path": "test.conf", "content": "test=value"}'

# Restart a Docker container (triggers HITL)
curl -X POST http://localhost:8080/api/tools/docker/action \
  -H "Content-Type: application/json" \
  -d '{"container": "nginx", "action": "restart"}'

# Read only a specific function from a source file
curl -X POST http://localhost:8080/api/tools/language/read_file \
  -H "Content-Type: application/json" \
  -d '{"path":"main.py","window":"function:run","format":"numbered"}'

# Validate syntax + lint + type for a Python file
curl -X POST http://localhost:8080/api/tools/language/validate \
  -H "Content-Type: application/json" \
  -d '{"path":"main.py","checks":["syntax","lint","type"]}'

# Validate TypeScript types via LSP
curl -X POST http://localhost:8080/api/tools/language/validate \
  -H "Content-Type: application/json" \
  -d '{"path":"app.ts","checks":["syntax","type"]}'

# List installed local skills (offline-capable)
curl -X POST http://localhost:8080/api/tools/skills/list

# Search remote skills registry
curl -X POST http://localhost:8080/api/tools/skills/search \
  -H "Content-Type: application/json" \
  -d '{"query":"react testing","max_results":5}'

# Install a skill (HITL-gated)
curl -X POST http://localhost:8080/api/tools/skills/install \
  -H "Content-Type: application/json" \
  -d '{"repo":"vercel-labs/agent-skills","skill_name":"vitest"}'

# List configured subagent types
curl -X POST http://localhost:8080/api/tools/subagent/list

# Run a configured subagent
curl -X POST http://localhost:8080/api/tools/subagent/run \
  -H "Content-Type: application/json" \
  -d '{"type":"prompt_optimizer","input":"Improve this prompt","context":"Audience: backend engineers"}'
```

### 4. Approve in Dashboard

1. Go to http://localhost:8080/admin/
2. Dashboard shows pending requests in HITL widget (yellow glow)
3. Expand the widget to see requests
4. Click "Approve" or "Reject" directly from dashboard
5. Or click "View All" to navigate to full HITL Queue page

---

## Architecture

```
┌─────────────────────────────────────────┐
│         Docker Container                │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  FastAPI Application              │  │
│  │                                   │  │
│  │  • OpenAPI: /api/tools/*          │  │
│  │  • MCP: /mcp                      │  │
│  │  • Admin: /admin/                 │  │
│  │  • WebSocket: /ws/hitl            │  │
│  │                                   │  │
│  │  ┌─────────────────────────────┐ │  │
│  │  │  Tool Execution Engine      │ │  │
│  │  │  • Module Registry          │ │  │
│  │  │  • Policy Enforcer          │ │  │
│  │  │  • HITL Manager             │ │  │
│  │  │  • Secret Resolver          │ │  │
│  │  │  • Audit Logger             │ │  │
│  │  └─────────────────────────────┘ │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Volumes:                               │
│  • /workspace (host directories)        │
│  • /skills (isolated skill storage)     │
│  • /data (SQLite, logs)                 │
│  • /secrets (secrets.env)               │
└─────────────────────────────────────────┘
```

---

## Configuration

### Environment Variables

```bash
# Required
ANYIDE_ADMIN_PASSWORD=your-secure-password
# Legacy fallback: ADMIN_PASSWORD=your-secure-password

# Precedence:
# 1) ANYIDE_ADMIN_PASSWORD
# 2) ADMIN_PASSWORD (legacy)
# 3) config.yaml auth.admin_password
# 4) default "admin"

# Optional
ANYIDE_WORKSPACE_BASE_DIR=/workspace
ANYIDE_PORT=8080
ANYIDE_AUDIT_RETENTION_DAYS=30
ANYIDE_LOG_LEVEL=INFO
ANYIDE_HITL_TTL_SECONDS=300
ANYIDE_MODULES=all
ANYIDE_SKILLS_BASE_DIR=/skills
ANYIDE_HOST_SKILLS_DIR=./skills
```

`ANYIDE_MODULES` supports:
- `all` (default): load all built-in modules
- `all,-docker,-http`: load all except listed modules
- `fs,workspace,shell,git,memory,plan,language,skills,subagent`: explicit allowlist

### Module Selection (`config.yaml`)

```yaml
modules:
  enabled: []          # empty => all available modules
  disabled: []         # e.g. ["docker", "http"]
```

Environment variable `ANYIDE_MODULES` overrides `modules.enabled/disabled`.

### Skills Storage and Connectivity (`config.yaml`)

```yaml
skills:
  base_dir: /skills
```

- `skills.base_dir` is isolated from workspace paths and should be mounted as a separate volume.
- Offline mode: `skills_list`, `skills_read`, and `skills_read_file` work from local `skills.base_dir` content, including `.agents/skills` installs.
- Online mode: `skills_search` and `skills_install` require outbound network access.
- `skills_install` runs in project scope (no `--global`) so installed skills remain under mounted `/skills` storage.
- `skills_install` is HITL-gated by default because it downloads and executes external code.

### Language + LSP (`config.yaml`)

```yaml
language:
  linters:
    python: "ruff"
  lsp_servers:
    python: "pyright"
    typescript: "typescript-language-server"
```

- LSP servers start lazily and stay resident for reuse.
- If a server binary is missing or initialization fails, language tools fall back to tree-sitter behavior.
- Type diagnostics are returned in `lang_validate.type_check.errors` when `checks` includes `"type"`.

### LLM Endpoints (`config.yaml`)

LLM endpoint configuration is a **system capability** (for internal modules and admin workflows), not a tool module.

```yaml
llm:
  endpoints:
    - id: "primary"
      provider: "openai"                 # openai | openai_compatible | ollama | anthropic | google
      base_url: "https://api.openai.com/v1"
      api_key_secret: "OPENAI_API_KEY"   # optional for ollama
      default_model: "gpt-4o-mini"
      timeout: 60
```

Admin-only LLM APIs:
- `GET /admin/api/llm/endpoints` (sanitized endpoint list)
- `POST /admin/api/llm/test` (connectivity test for one endpoint)

### Subagents (`config.yaml`)

Subagent types are configured in `subagents.types` and executed through `subagent_run`.

```yaml
subagents:
  types:
    prompt_optimizer:
      display_name: "Prompt Optimizer"
      description: "Improve prompts for clarity and constraints"
      llm_endpoint: "primary"
      model: "gpt-4o-mini"             # optional (falls back to endpoint default)
      temperature: 0.3                 # optional
      max_tokens: 2048                 # optional
      system_prompt_file: "prompts/prompt_optimizer.md"
      response_format: null            # or "json"
      allow_model_override: false
      allow_temperature_override: false
```

### Secrets File

Create `secrets.env` with your sensitive values:

```bash
# secrets.env — mounted read-only into the container
GITHUB_TOKEN=ghp_your_token_here
DB_PASSWORD=super_secret
API_KEY=your_api_key
```

Reference secrets in any tool parameter using `{{secret:KEY}}` syntax:

```bash
# Use a secret in an HTTP Authorization header
curl -X POST http://localhost:8080/api/tools/http/request \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://api.github.com/user",
    "method": "GET",
    "headers": {"Authorization": "Bearer {{secret:GITHUB_TOKEN}}"}
  }'

# List loaded secret key names (no values)
curl -X POST http://localhost:8080/api/tools/workspace/secrets/list
```

### HTTP Configuration (`config.yaml`)

```yaml
http:
  block_private_ips: true           # Block RFC 1918 / loopback ranges
  block_metadata_endpoints: true    # Block 169.254.169.254 and similar
  allow_domains: []                 # Empty = allow all (add entries to whitelist)
  block_domains:                    # Always blocked regardless of allowlist
    - "*.internal.example.com"
  max_response_size_kb: 1024        # Truncate responses larger than this
  default_timeout: 30               # Seconds
  max_timeout: 120                  # Hard cap regardless of request value
```

### Docker Compose

```yaml
services:
  anyide:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ANYIDE_ADMIN_PASSWORD=admin
      # Legacy fallback: ADMIN_PASSWORD=admin
      - WORKSPACE_BASE_DIR=/workspace
      - ANYIDE_SKILLS_BASE_DIR=/skills
    volumes:
      - ./workspace:/workspace
      - ./skills:/skills
      - ./data:/data
      - ./secrets.env:/secrets/secrets.env:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro  # For Docker tools
      - ./config.yaml:/app/config.yaml:ro
```

---

## Admin Dashboard

### Features

- **Unified Dashboard:** Widget-based interface showing all critical information at a glance
  - Expandable/collapsible sections for flexible monitoring
  - Real-time updates via WebSocket
  - Quick actions directly from dashboard widgets
- **HITL Approval Queue Widget:**
  - Approve/reject tool executions without navigation
  - Countdown timers and progress bars
  - Real-time notifications with visual alerts
  - Browser notifications for desktop alerts
- **System Health Widget:**
  - Overall health status with color-coded indicators
  - Key metrics: uptime, pending HITL, tools executed, error rate
  - Quick access to detailed health page
- **Recent Activity Widget:**
  - Last 5 tool executions with status badges
  - Quick stats: success, errors, blocked counts
  - Link to full audit log with filtering
- **Tool Explorer Page:**
  - Browse all available tools by category
  - View JSON schemas for each tool
  - See HITL requirements and descriptions
- **Configuration Page:**
  - View current server configuration
  - HTTP settings and policy rules
  - Workspace and database paths
  - Sanitized LLM endpoint inventory and endpoint test actions
- **Enhanced System Health Page:**
  - Real-time CPU and memory usage with progress bars
  - Database and workspace disk sizes
  - WebSocket connection count
  - System info: platform, Python version, framework
  - Tool category status overview
- **Audit Log Enhancements:**
  - Export logs as JSON or CSV
  - Filter by status and tool category
  - Pagination for large datasets
- **Container Management:**
  - List Docker containers with status
  - View container logs from admin UI
- **Dedicated Pages:**
  - Full HITL Queue management with detailed request information
  - Complete Audit Log with search, filter, and export
  - Detailed System Health with performance metrics
  - Secrets Management: list loaded key names, trigger hot reload
- **Premium UI:**
  - Glassmorphism design with 3D animations
  - Aurora backgrounds and floating particles
  - Fully responsive (mobile, tablet, desktop)
  - Real-time WebSocket updates
  - Touch-friendly interactions

### Access

```
http://localhost:8080/admin/
```

**Default Landing:** Unified dashboard with all widgets  
**Navigation:** Sidebar menu for dedicated pages  
**Documentation:** See `admin/README.md` for complete guide

---

## Available Tools

### Filesystem

- `fs_read` - Read file contents with line range support
- `fs_write` - Write file contents (HITL for .conf, .env, .yaml)
- `fs_list` - List directory contents with recursive traversal and filtering
- `fs_search` - Search files by name or content with regex support

### Shell

- `shell_execute` - Execute shell commands with security controls
  - Allowlist of safe commands (ls, cat, echo, git, python, npm, docker, etc.)
  - Dangerous metacharacter detection (;, |, &, >, <, etc.)
  - HITL for non-allowlisted or unsafe commands
  - Output truncation and timeout support

### Git

- `git_status` - Get repository status (branch, staged, unstaged, untracked files)
- `git_log` - View commit history with filtering options
- `git_diff` - View file differences (unstaged, staged, or against ref)
- `git_show` - Show commit details with full diff
- `git_list_branches` - List local and remote branches
- `git_remote` - Manage remote repositories
- `git_commit` - Create commits (HITL required)
- `git_push` - Push to remote (HITL required)
- `git_pull` - Pull from remote
- `git_checkout` - Switch branches or restore files (HITL required)
- `git_branch` - Create or delete branches (HITL for delete)
- `git_stash` - Stash operations (push, pop, list, drop)

### Docker

- `docker_list` - List Docker containers with filtering
  - Filter by name (partial match) or status (running, exited, paused, etc.)
  - Include/exclude stopped containers
  - Returns container ID, name, image, status, ports, creation time
- `docker_inspect` - Get detailed container information
  - Configuration (environment variables, command, entrypoint, labels)
  - Network settings (IP address, ports, networks)
  - Volume mounts and bind mounts
  - Container state (running, paused, exit code, PID, timestamps)
- `docker_logs` - Retrieve container logs
  - Configurable tail (number of lines from end)
  - Time-based filtering (since timestamp)
  - Returns stdout and stderr combined
- `docker_action` - Control container lifecycle (HITL required)
  - Start stopped containers
  - Stop running containers (graceful shutdown)
  - Restart containers
  - Pause/unpause containers
  - Returns previous and new status

### Workspace

- `workspace_info` - Get workspace configuration and disk usage
- `workspace_secrets_list` - List loaded secret key names (no values exposed)

### HTTP

- `http_request` - Make outbound HTTP requests
  - Domain allowlist and blocklist via `config.yaml`
  - SSRF protection: blocks private IP ranges (10.x, 192.168.x, 172.16-31.x) and cloud metadata endpoints
  - Secret template injection: use `{{secret:KEY}}` in headers, URL, or body
  - Configurable timeout (default 30s, max 120s)
  - Response truncation and content-type handling

### Memory Tools

- `memory_store` - Store a knowledge node with entity type, tags, and metadata; optionally link to existing nodes
- `memory_get` - Retrieve a node by ID with its immediate relationships (incoming and outgoing)
- `memory_search` - Full-text search (FTS5 BM25 ranking) with optional tag filter and entity type filter
- `memory_update` - Update node content, name, tags, or metadata (metadata is patch-merged)
- `memory_delete` - Delete a node and all its edges (HITL-gated; cascade option for orphaned children)
- `memory_link` - Create or update a typed, directed edge between nodes; supports bidirectional and temporal edges
- `memory_children` - Get immediate children connected via `parent_of` edges
- `memory_ancestors` - Traverse upward via `parent_of` edges (recursive CTE, configurable depth)
- `memory_roots` - Get all root nodes (nodes with no incoming `parent_of` edges)
- `memory_related` - Get all nodes connected by any edge type, with optional relation filter
- `memory_subtree` - Get full descendant subtree via `parent_of` edges (recursive CTE, configurable depth)
- `memory_stats` - Graph metrics: node/edge counts, type breakdown, tag frequency, most connected nodes

### Plan Tools

- `plan_create` - Create a new plan with DAG validation
  - Validates task dependencies for cycles using Kahn's algorithm
  - Computes execution levels for concurrent task scheduling
  - Returns `plan_id`, execution order, and task count
- `plan_execute` - Get current ready tasks and plan progress snapshot
  - Pass `plan_id` from `plan_create` response
  - Resilience fallback: a unique plan name is accepted; ambiguous names are rejected
  - Moves plan from `pending` to `running` on first call
  - Returns `ready_tasks` with dependency-checked, reference-resolved params
- `plan_update_task` - Update a task after external execution
  - Mark task `running`, `completed` (with `output`), or `failed` (with `error`)
  - Enforces failure policies: `stop`, `skip_dependents`, `continue`
  - Computes next ready tasks after each update
- Plan task references: `{{task:TASK_ID.field}}` in downstream params
  - Three failure policies: `stop`, `skip_dependents`, `continue`
  - Per-task `on_failure` override for fine-grained control
- `plan_status` - Get plan and per-task status
  - Prefer `plan_id` from `plan_create`; unique names are accepted when unambiguous
  - Task states: pending, running, completed, failed, skipped
  - Includes task outputs, errors, and timestamps
  - Counts: total, completed, failed, skipped, running
- `plan_list` - List all plans with summary info
- `plan_cancel` - Cancel a pending or running plan
  - Prefer `plan_id` from `plan_create`; unique names are accepted when unambiguous

### Language

- `lang_read_file` - Read files with structural windows (`function:`, `class:`, `import:*`, `lines:`)
- `lang_skeleton` - Return file structure (symbols/signatures) for one or more files
- `lang_diff` - Generate function-anchored structural diffs with syntax validation
- `lang_apply_patch` - Apply anchored patch hunks with fallback matching, backup, and validation
- `lang_create_file` - Create a new code file with syntax/lint validation and symbol extraction
- `lang_index` - Incrementally index workspace symbols into persistent SQLite tables
- `lang_search_symbols` - Query indexed symbols by wildcard/name/kind/language
- `lang_reference_graph` - Build file/workspace reference graph with LSP semantic cross-file edges for JS/TS
- `lang_validate` - Run syntax/lint checks plus optional LSP type diagnostics (`checks: ["type"]`)

### Skills

- `skills_list` - List installed skills from isolated `/skills` storage (offline-capable)
- `skills_read` - Read `SKILL.md` content with optional section extraction
- `skills_read_file` - Read scripts/references files within an installed skill directory
- `skills_search` - Search remote skills registry using `npx skills find ... --json`
- `skills_install` - Install skills from remote repos in project scope under `/skills` (HITL-gated; requires network egress)

### Subagent

- `subagent_list` - List configured subagent types from `config.yaml`
- `subagent_run` - Execute a configured single-turn subagent via the unified LLM client
  - Prompt template loading and `{{input}}` / `{{context}}` substitution
  - Per-type controls for `override_model` and `override_temperature`
  - Response metadata includes `endpoint_used`, `model_used`, `latency_ms`, and `usage`

---

## Security

### Defense Layers

1. **Volume Mounts:** Docker isolation
2. **Workspace Boundary:** Path resolution + validation
3. **Tool Policies:** Allow/block/HITL per tool
4. **HITL Approval:** Human review of requests
5. **Secret Isolation:** Secrets resolved server-side; templates (`{{secret:KEY}}`) appear in audit logs, never resolved values
6. **SSRF Protection:** HTTP client blocks private IPs, RFC 1918 ranges, and cloud metadata endpoints (169.254.169.254)
7. **Domain Filtering:** Per-host HTTP allowlist and blocklist
8. **Admin Auth:** Password-protected dashboard
9. **Audit Log:** Complete request/response logging

### Best Practices

- Use strong admin password
- Review HITL requests promptly
- Monitor audit log regularly
- Limit workspace mounts to necessary directories
- Use secrets for sensitive credentials
- Enable HTTPS in production

---

## Development

### Project Structure

```
.
├── anyide/                # Python backend
│   ├── main.py            # FastAPI app
│   ├── config.py          # App configuration models/loader
│   ├── models.py          # Request/response models
│   ├── admin_api.py       # Admin API routes
│   ├── logging_config.py  # Structured logging setup
│   ├── core/              # Shared runtime infrastructure
│   │   ├── audit.py       # Audit logger
│   │   ├── database.py    # SQLite access
│   │   ├── hitl.py        # HITL manager
│   │   ├── llm_client.py  # Unified system LLM client
│   │   ├── llm_adapters/  # Provider adapters (OpenAI/Anthropic/Google)
│   │   ├── policy.py      # Policy engine
│   │   ├── secrets.py     # Secret resolver
│   │   └── workspace.py   # Workspace/path security
│   └── modules/           # Plug-and-play tool modules
│       ├── registry.py
│       ├── base.py
│       ├── fs/
│       │   ├── module.py
│       │   └── tools.py
│       ├── language/
│       │   ├── module.py
│       │   ├── tools.py
│       │   ├── treesitter.py
│       │   └── schemas.py
│       ├── skills/
│       │   ├── module.py
│       │   ├── tools.py
│       │   └── schemas.py
│       ├── subagent/
│       │   ├── module.py
│       │   ├── tools.py
│       │   ├── schemas.py
│       │   └── prompts/
│       └── ...
├── admin/                 # React dashboard
│   ├── src/
│   │   ├── pages/         # Dashboard pages
│   │   ├── components/    # UI components
│   │   └── lib/           # API & WebSocket clients
│   └── dist/              # Built static files
├── docs/                  # Supplemental operational docs
│   ├── DOCKER_HUB_PUBLISHING.md
│   ├── LLM_SYSTEM_PROMPT.md
│   └── TOOL_CATALOG.md
├── examples/              # Config and deployment templates
├── scripts/               # Utility scripts (for docs generation, etc.)
├── tests/                 # Unit, integration, security, and load tests
├── development/           # Supplemental project documentation
├── docker-compose.yaml    # Docker config
└── Dockerfile            # Container image
```

### Build Admin Dashboard

```bash
cd admin
npm install
npm run build
```

### Test Admin Dashboard Frontend

```bash
cd admin
npm run test
```

### Run Tests

```bash
# Run all tests
./venv/bin/pytest

# Run specific test file
./venv/bin/pytest tests/test_mcp.py

# Run integration/security/load suites
./venv/bin/pytest tests/test_integration.py -v
./venv/bin/pytest tests/test_security.py -v
./venv/bin/pytest tests/test_load.py -v

# Run with coverage
./venv/bin/pytest --cov=anyide --cov-report=html

# Run with verbose output
./venv/bin/pytest -v

# Collect test inventory
./venv/bin/pytest --collect-only -q
```

### Run Locally (Development)

```bash
# Backend
python -m uvicorn anyide.main:app --reload

# Frontend (separate terminal)
cd admin
npm run dev
```

---

## Documentation

- **Admin Dashboard Guide:** `admin/README.md` - Complete dashboard documentation
- **Commands to Try:** `CommandsToTry.md` - Sample commands for LLM interaction
- **Tool Catalog:** `docs/TOOL_CATALOG.md` - Auto-generated endpoint and MCP tool reference
- **LLM Prompt Template:** `docs/LLM_SYSTEM_PROMPT.md` - Starter system prompt for AnyIDE-connected assistants
- **Docker Publishing Guide:** `docs/DOCKER_HUB_PUBLISHING.md` - Build/tag/publish workflow
- **Scaling Notes:** `docs/SCALING.md` - Vertical/horizontal scaling paths and module decomposition guidance
- **Release Baseline:** `docs/RELEASE_BASELINE.md` - Recorded regression and smoke-check metrics for release readiness
- **Deployment Examples:** `examples/` - `config.basic.yaml`, `config.development.yaml`, `config.restricted.yaml`, and production compose template
- **API Documentation:** http://localhost:8080/docs - Interactive OpenAPI docs
- **Regenerate Tool Catalog:** `python3 scripts/generate_tool_docs.py > docs/TOOL_CATALOG.md`

---

## Capability Reference

### Core Platform
- FastAPI service exposes MCP (`/mcp`) and OpenAPI (`/api/tools/*`) interfaces from one backend.
- SQLite persists audit history, HITL state, memory graph data, and plan orchestration state.
- Unified LLM access is a shared system capability (`llm.endpoints` + `LLMClient`), not an LLM-visible tool category.

### Security and Governance
- Workspace boundary enforcement prevents path traversal and out-of-scope file access.
- Policy engine supports allow, block, and HITL actions per tool operation.
- Secrets resolve server-side with `{{secret:KEY}}`; audit logs store templates, not secret values.
- HTTP tool includes SSRF protections for private ranges and cloud metadata endpoints.

### Admin Experience
- Password-protected dashboard with real-time HITL queue, health metrics, and recent activity.
- Tool explorer, configuration viewer, audit filtering/export, and container log views.
- Admin configuration surfaces include LLM endpoint listing and direct connectivity testing.
- Session expiry handling redirects users to `/admin/login` after unauthorized responses.
- Admin API accepts session cookies and `Authorization: Bearer <token>` fallback.
- Dashboard API/WebSocket clients support reverse-proxy path prefixes.

### Tooling
- Filesystem, shell, git, docker, workspace, HTTP, language, skills, and subagent tool categories.
- Memory graph tooling with full-text search and relationship traversal.
- DAG plan orchestration with ready-task snapshots, task references, and configurable failure policies.

### Test Coverage Snapshot
- `pytest --collect-only -q` reports 509 backend tests.
- Memory tool suite: 48 tests.
- Plan orchestration suite: 22 tests.
- HITL WebSocket roundtrip tests: 7 tests.
- Tool Explorer contract tests: 13 tests.
- LLM endpoint/config coverage: config validation + client/adapter normalization + admin endpoint behavior.
- Subagent API coverage: module registration, run path, override controls, and failure mapping.
- Frontend admin auth/session tests run with Vitest + jsdom.

---

## Contributing

Contributions are welcome. Prefer focused pull requests, include tests for behavior changes, and keep comments/docs focused on durable behavior and operational guidance.

---

## License

[Your License Here]

---

## Support

### Troubleshooting

1. **Check container logs:**
   ```bash
   docker compose logs anyide -f
   ```

2. **Verify health:**
   ```bash
   curl http://localhost:8080/health
   ```

3. **Test admin login:**
   ```bash
   curl -X POST http://localhost:8080/admin/api/login \
     -H "Content-Type: application/json" \
     -d '{"password": "admin"}'
   ```

4. **Check browser console** (F12) for frontend errors

### Common Issues

- **Blank admin page:** Check browser console, verify assets loading
- **Login fails:** Verify effective password precedence and container env (`ANYIDE_ADMIN_PASSWORD` preferred, `ADMIN_PASSWORD` legacy).
- **HITL not appearing:** Check WebSocket connection in browser console
- **Tool execution fails:** Check audit log for error details

---

## Acknowledgments

Built following the design principles from:
- Model Context Protocol (MCP) specification
- Open WebUI OpenAPI tool server pattern
- Premium UI inspiration from Magic UI, Aceternity UI, 21st.dev

---

**Status:** Production Ready  
**Version:** 0.1.0  
**Last Updated:** March 2, 2026

---

## Testing

The project includes comprehensive test coverage.

As of this snapshot, `pytest --collect-only -q` reports **481 tests collected** across:

- Unit tests for core modules and tool implementations
- API and admin endpoint integration tests
- MCP protocol and HITL workflow tests
- Security regression tests (path traversal, SSRF, auth enforcement, input handling)
- Load/concurrency tests for frequent file and API operations
- Feature-specific suites for Git, Docker, memory graph, plan orchestration, secrets, HTTP, and LLM config/client layers
- Tool Explorer contract tests verifying OpenAPI-based tool listing
- HITL WebSocket roundtrip and disconnect resilience tests
- Frontend unit tests (Vitest + jsdom) for admin auth/session behavior
