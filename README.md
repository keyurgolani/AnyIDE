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
- **Workspace Management:** Secure path resolution and boundary enforcement
- **HITL System:** Real-time approval workflow for sensitive operations
- **Admin Dashboard:** Premium UI with real-time updates
  - Automatic redirect to login when admin session expires
- **Audit Logging:** Complete execution history
- **Policy Engine:** Allow/block/HITL rules per tool
- **Secret Management:** Secure secret resolution with `{{secret:KEY}}` template syntax
- **HTTP Client:** Make outbound HTTP requests with SSRF protection, domain filtering, and secret injection
- **Knowledge Graph Memory:** 12 tools for persistent knowledge storage with FTS5 search and graph traversal
  - Improved natural-language memory search recall (question-style queries)
- **Plan Execution:** DAG-based multi-step workflows with concurrent execution, task references, and failure handling
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

# Optional
ANYIDE_WORKSPACE_BASE_DIR=/workspace
ANYIDE_PORT=8080
ANYIDE_AUDIT_RETENTION_DAYS=30
ANYIDE_LOG_LEVEL=INFO
ANYIDE_HITL_TTL_SECONDS=300
ANYIDE_MODULES=all
```

`ANYIDE_MODULES` supports:
- `all` (default): load all built-in modules
- `all,-docker,-http`: load all except listed modules
- `fs,workspace,shell,git,memory,plan`: explicit allowlist

### Module Selection (`config.yaml`)

```yaml
modules:
  enabled: []          # empty => all available modules
  disabled: []         # e.g. ["docker", "http"]
```

Environment variable `ANYIDE_MODULES` overrides `modules.enabled/disabled`.

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
      - ADMIN_PASSWORD=admin
      - WORKSPACE_BASE_DIR=/workspace
    volumes:
      - ./workspace:/workspace
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
- `plan_execute` - Execute a plan synchronously until completion
  - Pass `plan_id` from `plan_create` response
  - Resilience fallback: a unique plan name is accepted; ambiguous names are rejected
  - Topological sort ensures correct dependency order
  - Concurrent execution via `asyncio.gather` for tasks at same level
  - Task reference resolution: `{{task:TASK_ID.field}}` in params
  - Three failure policies: `stop`, `skip_dependents`, `continue`
  - Per-task `on_failure` override for fine-grained control
  - HITL integration: tasks with `require_hitl=True` block for approval
- `plan_status` - Get plan and per-task status
  - Prefer `plan_id` from `plan_create`; unique names are accepted when unambiguous
  - Task states: pending, running, completed, failed, skipped
  - Includes task outputs, errors, and timestamps
  - Counts: total, completed, failed, skipped, running
- `plan_list` - List all plans with summary info
- `plan_cancel` - Cancel a pending or running plan
  - Prefer `plan_id` from `plan_create`; unique names are accepted when unambiguous

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
├── src/                    # Python backend
│   ├── main.py            # FastAPI app
│   ├── hitl.py            # HITL manager
│   ├── audit.py           # Audit logger
│   ├── policy.py          # Policy engine
│   ├── workspace.py       # Path resolution
│   ├── secrets.py         # Secret manager (template resolver)
│   ├── admin_api.py       # Admin API
│   └── tools/             # Tool implementations
│       ├── http_tools.py  # HTTP client with SSRF protection
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
pytest

# Run specific test file
pytest tests/test_mcp.py

# Run integration/security/load suites
pytest tests/test_integration.py -v
pytest tests/test_security.py -v
pytest tests/test_load.py -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run with verbose output
pytest -v

# Collect test inventory
pytest --collect-only -q
```

### Run Locally (Development)

```bash
# Backend
python -m uvicorn src.main:app --reload

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
- **Deployment Examples:** `examples/` - `config.basic.yaml`, `config.development.yaml`, `config.restricted.yaml`, and production compose template
- **API Documentation:** http://localhost:8080/docs - Interactive OpenAPI docs
- **Regenerate Tool Catalog:** `python3 scripts/generate_tool_docs.py > docs/TOOL_CATALOG.md`

---

## Capability Reference

### Core Platform
- FastAPI service exposes MCP (`/mcp`) and OpenAPI (`/api/tools/*`) interfaces from one backend.
- SQLite persists audit history, HITL state, memory graph data, and plan execution data.

### Security and Governance
- Workspace boundary enforcement prevents path traversal and out-of-scope file access.
- Policy engine supports allow, block, and HITL actions per tool operation.
- Secrets resolve server-side with `{{secret:KEY}}`; audit logs store templates, not secret values.
- HTTP tool includes SSRF protections for private ranges and cloud metadata endpoints.

### Admin Experience
- Password-protected dashboard with real-time HITL queue, health metrics, and recent activity.
- Tool explorer, configuration viewer, audit filtering/export, and container log views.
- Session expiry handling redirects users to `/admin/login` after unauthorized responses.

### Tooling
- Filesystem, shell, git, docker, workspace, and HTTP tool categories.
- Memory graph tooling with full-text search and relationship traversal.
- DAG plan execution with concurrency, task references, and configurable failure policies.

### Test Coverage Snapshot
- `pytest --collect-only -q` reports 434 backend tests.
- Memory tool suite: 48 tests.
- Plan execution suite: 57 tests.
- HITL WebSocket roundtrip tests: 7 tests.
- Tool Explorer contract tests: 13 tests.
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
- **Login fails:** Verify ADMIN_PASSWORD in docker-compose.yaml
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
**Last Updated:** March 1, 2026

---

## Testing

The project includes comprehensive test coverage.

As of this snapshot, `pytest --collect-only -q` reports **434 tests collected** across:

- Unit tests for core modules and tool implementations
- API and admin endpoint integration tests
- MCP protocol and HITL workflow tests
- Security regression tests (path traversal, SSRF, auth enforcement, input handling)
- Load/concurrency tests for frequent file and API operations
- Feature-specific suites for Git, Docker, memory graph, plan execution, secrets, and HTTP
- Tool Explorer contract tests verifying OpenAPI-based tool listing
- HITL WebSocket roundtrip and disconnect resilience tests
- Frontend unit tests (Vitest + jsdom) for admin auth/session behavior
