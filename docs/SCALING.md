# AnyIDE Scaling Notes

This document captures practical scaling options for AnyIDE beyond the default single-instance deployment.

## Current Default (Phase 2 Baseline)

- Deployment target: single container, single process.
- Data store: SQLite (`/data/hostbridge.db`).
- Module set: typically `ANYIDE_MODULES=all`.
- Fit: self-hosted LLM users with low to moderate concurrency.

## Vertical Scaling

Use these options first before introducing distributed complexity.

### Increase API Concurrency

- Run Uvicorn with multiple workers behind a reverse proxy.
- Keep in mind SQLite has a single-writer constraint; read-heavy workloads scale better than write-heavy.
- Prefer enabling SQLite WAL mode when write contention appears.

### CPU and Memory Tuning

- Language tooling (tree-sitter + LSP) is CPU-sensitive under heavy parallel requests.
- Subagent and HTTP-heavy flows can increase outbound network latency pressure.
- Set container resource limits and monitor queue depth/latency before raising concurrency.

### LSP Process Behavior

- LSP servers are long-lived subprocesses (one per configured language).
- First request pays startup/initialize cost; subsequent requests reuse the process.
- Under sustained memory pressure, monitor/restart language server processes proactively.

## Horizontal Scaling Path

Move to this model when a single host no longer meets latency or throughput targets.

### Data Layer Migration

- Replace SQLite with PostgreSQL for multi-instance safe writes.
- Keep schema and repository interfaces abstraction-friendly during migration.

### Eventing and HITL Coordination

- Replace in-process `asyncio.Event` request signaling with Redis pub/sub or streams.
- Use shared state for HITL request lifecycle, approval events, and timeout handling.

### WebSocket Fan-out

- Admin dashboard websocket streams require sticky sessions or external fan-out.
- Recommended: Redis-backed pub/sub fan-out for `/ws/hitl` and `/ws/logs`.

### Shared Storage

- Ensure all instances resolve the same workspace and skills roots (or shard explicitly).
- Use consistent mount conventions for `/workspace`, `/skills`, `/data`, `/secrets`.

## Module Decomposition Strategy

AnyIDE modules can be split by workload profile without changing tool contracts.

### Suggested Split

- `core`: `fs,workspace,shell,git,http,memory,plan`
- `language`: `language`
- `ai`: `subagent,skills`

### Example Multi-Service Compose Pattern

```yaml
services:
  anyide-core:
    environment:
      ANYIDE_MODULES: "fs,workspace,shell,git,http,memory,plan"
    ports: ["8080:8080"]

  anyide-language:
    environment:
      ANYIDE_MODULES: "language"
    ports: ["8081:8080"]

  anyide-ai:
    environment:
      ANYIDE_MODULES: "subagent,skills"
    ports: ["8082:8080"]
```

## Operational Baselines to Track

- p50/p95 API latency by tool category.
- HITL queue depth and approval turnaround.
- LSP cold-start time by language.
- Database write latency and lock wait rates.
- Memory and CPU per module-heavy request mix.

## Migration Checklist

1. Measure current baseline using `docs/RELEASE_BASELINE.md`.
2. Identify the bottleneck (CPU, DB locks, network, websocket fan-out).
3. Scale vertically first and verify gains.
4. Introduce PostgreSQL + Redis before adding multiple AnyIDE instances.
5. Split modules by traffic profile only after shared state is externalized.
