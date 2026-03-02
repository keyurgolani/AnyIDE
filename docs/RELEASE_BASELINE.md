# Release Validation Baseline

This document records the latest release-readiness validation baseline for AnyIDE.

## Run Snapshot

- Date: 2026-03-02
- Branch: `main`
- Validation environment: local Linux dev host, Python 3.12 virtualenv, Docker engine

## Test Suite Baseline (`P2-8.2`)

| Suite | Command | Collected | Result | Wall Time (s) | Pytest Summary |
|---|---|---:|---|---:|---|
| Full regression | `venv/bin/pytest` | 509 | pass | 19 | `505 passed, 4 skipped, 37 warnings in 17.91s` |
| Security | `venv/bin/pytest tests/test_security.py -v` | 18 | pass | 1 | `15 passed, 3 skipped in 0.87s` |
| Integration | `venv/bin/pytest tests/test_integration.py -v` | 18 | pass | 2 | `17 passed, 1 skipped, 4 warnings in 1.20s` |
| Load | `venv/bin/pytest tests/test_load.py -v` | 4 | pass | 1 | `4 passed in 0.92s` |

## Module Matrix Coverage (`P2-8.1`)

- Added matrix integration tests for `ANYIDE_MODULES` combinations across OpenAPI and MCP surfaces.
- Added dependency-edge test coverage for topological ordering and disabled-dependency failures.
- Validation command: `venv/bin/pytest tests/test_module_matrix_integration.py tests/test_module_registry.py -q`
- Result: `7 passed`

## Notes

- Warning counts are currently dominated by third-party `httpx` cookie deprecation warnings in existing tests.
- No test failures were observed in this baseline run.

## Container Flow Validation (`P2-8.4`)

- Buildx local-load validation:
  - Command: `docker buildx build --platform linux/amd64 --load -t hostbridge:anyide-release-check .`
  - Result: success.
- Clean deployment smoke:
  - Commands: `docker compose down --remove-orphans && docker compose up -d --build`
  - Health check: `{"status":"healthy","version":"0.1.0"}`
  - OpenAPI path count: `77`
  - MCP tools/list count: `58`

## Docker Publish Validation (`P2-8.6`)

- Published tags: `keyurgolani/anyide:latest`, `keyurgolani/anyide:0.1.0`
- Published manifest digest: `sha256:c3726582acf5303d9ef4bf2550375330d14485727031cfe78312dbaf8792acbf`
- Registry inspection confirms multi-arch manifests:
  - `linux/amd64`
  - `linux/arm64`
- Pull verification:
  - `docker pull keyurgolani/anyide:latest`
  - `docker pull keyurgolani/anyide:0.1.0`
- Run verification:
  - `docker run` requires workspace configuration (`WORKSPACE_BASE_DIR=/workspace` plus mounted workspace path).
  - Health status after pull/run: `healthy` (version `0.1.0`)
  - OpenAPI path count: `77`
  - MCP tools/list count: `58`

## Testing and Validation Improvement Opportunities

1. Add CI smoke test for published images (`docker pull` + `docker run` + `/health` + MCP `tools/list`) to guard release regressions.
2. Add explicit MCP HTTP conformance tests for required `Accept` header and session-id flow to prevent protocol drift.
3. Add container startup contract tests for entrypoint workspace defaults vs env-configured paths to catch runtime misconfiguration earlier.
4. Track arm64-specific build and startup timing separately from amd64 to detect architecture-specific performance regressions.
