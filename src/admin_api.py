"""Admin API endpoints."""

import json
import os
import platform
import psutil
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, Cookie, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.config import Config
from src.audit import AuditLogger
from src.logging_config import get_logger
from src.models import DockerListRequest, DockerLogsRequest

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/api", tags=["admin"])

# Simple session storage (in-memory for MVP)
active_sessions: dict[str, datetime] = {}

# Track WebSocket connections
websocket_connections: int = 0


def increment_ws_connections():
    """Increment WebSocket connection count."""
    global websocket_connections
    websocket_connections += 1


def decrement_ws_connections():
    """Decrement WebSocket connection count."""
    global websocket_connections
    websocket_connections = max(0, websocket_connections - 1)


class LoginRequest(BaseModel):
    """Login request."""
    password: str


class LoginResponse(BaseModel):
    """Login response."""
    token: str


class SystemHealthResponse(BaseModel):
    """System health response."""
    uptime: int
    pending_hitl: int
    tools_executed: int
    error_rate: float


class DetailedHealthResponse(BaseModel):
    """Detailed system health response."""
    uptime: int
    pending_hitl: int
    tools_executed: int
    error_rate: float
    memory_used_mb: float
    memory_total_mb: float
    memory_percent: float
    cpu_percent: float
    db_size_mb: float
    db_path: str
    workspace_size_mb: float
    workspace_path: str
    websocket_connections: int
    python_version: str
    platform: str
    version: str


class ToolSchema(BaseModel):
    """Tool schema information."""
    name: str
    category: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    requires_hitl: bool = False


class ToolListResponse(BaseModel):
    """List of available tools."""
    tools: List[ToolSchema]
    total: int


class ConfigResponse(BaseModel):
    """Configuration response (sanitized)."""
    auth_enabled: bool
    workspace_path: str
    database_path: str
    log_level: str
    http_config: Dict[str, Any]
    policy_rules_count: int
    tool_configs: Dict[str, Any]


class AuditLogFilterResponse(BaseModel):
    """Audit log with filtering support."""
    logs: List[Dict[str, Any]]
    total: int
    filtered: int


# Dependency to check authentication
async def require_auth(session_token: Optional[str] = Cookie(None)):
    """Require authentication."""
    if not session_token or session_token not in active_sessions:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if session is expired (24 hours)
    session_time = active_sessions[session_token]
    if datetime.now(timezone.utc) - session_time > timedelta(hours=24):
        del active_sessions[session_token]
        raise HTTPException(status_code=401, detail="Session expired")
    
    return session_token


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, response: Response, config: Config = Depends(lambda: None)):
    """Admin login endpoint."""
    # Get config from global state (will be injected properly)
    from src.main import config as global_config
    
    if request.password != global_config.auth.admin_password:
        logger.warning("failed_login_attempt")
        raise HTTPException(status_code=401, detail="Invalid password")
    
    # Generate session token
    import secrets
    session_token = secrets.token_urlsafe(32)
    active_sessions[session_token] = datetime.now(timezone.utc)
    
    # Set httponly cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=False,  # Set to True in production with HTTPS
        samesite="lax",
        max_age=86400,  # 24 hours
    )
    
    logger.info("admin_login_successful")
    
    return LoginResponse(token=session_token)


@router.post("/logout")
async def logout(
    response: Response,
    session_token: str = Depends(require_auth)
):
    """Admin logout endpoint."""
    if session_token in active_sessions:
        del active_sessions[session_token]
    
    response.delete_cookie("session_token")
    logger.info("admin_logout")
    
    return {"message": "Logged out successfully"}


@router.get("/audit")
async def get_audit_logs(
    limit: int = 100,
    session_token: str = Depends(require_auth)
):
    """Get audit logs."""
    from src.main import audit_logger
    
    logs = await audit_logger.get_recent_logs(limit)
    return logs


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(session_token: str = Depends(require_auth)):
    """Get system health metrics."""
    from src.main import db, hitl_manager

    # Calculate uptime
    from src.main import app
    start_time = getattr(app.state, 'start_time', time.time())
    uptime = int(time.time() - start_time)

    # Get pending HITL count
    pending_hitl = len(hitl_manager.get_pending_requests())

    # Get total tools executed from audit log
    cursor = await db.connection.execute(
        "SELECT COUNT(*) as count FROM audit_log"
    )
    row = await cursor.fetchone()
    tools_executed = row["count"] if row else 0

    # Calculate error rate
    cursor = await db.connection.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
        FROM audit_log
        WHERE timestamp > datetime('now', '-1 hour')
        """
    )
    row = await cursor.fetchone()
    total = row["total"] if row and row["total"] else 0
    errors = row["errors"] if row and row["errors"] else 0
    error_rate = errors / total if total > 0 else 0.0

    return SystemHealthResponse(
        uptime=uptime,
        pending_hitl=pending_hitl,
        tools_executed=tools_executed,
        error_rate=error_rate,
    )


# ---------------------------------------------------------------------------
# Secrets management endpoints
# ---------------------------------------------------------------------------

class SecretsInfoResponse(BaseModel):
    """Secrets info response."""
    keys: list[str]
    count: int
    secrets_file: str


@router.get("/secrets", response_model=SecretsInfoResponse)
async def list_secrets(session_token: str = Depends(require_auth)):
    """List configured secret keys (admin view).

    Returns key names only — values are never exposed.
    """
    from src.main import secret_manager

    return SecretsInfoResponse(
        keys=secret_manager.list_keys(),
        count=secret_manager.count(),
        secrets_file=str(secret_manager.secrets_file),
    )


@router.post("/secrets/reload")
async def reload_secrets(session_token: str = Depends(require_auth)):
    """Reload secrets from the secrets file.

    Useful after adding or updating secrets without restarting the server.
    """
    from src.main import secret_manager, workspace_tools

    count = secret_manager.reload()
    logger.info("secrets_reloaded_via_admin", count=count)

    return {
        "message": f"Secrets reloaded successfully. {count} secret(s) loaded.",
        "count": count,
        "secrets_file": str(secret_manager.secrets_file),
    }


# ---------------------------------------------------------------------------
# Detailed Health Metrics
# ---------------------------------------------------------------------------

@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def get_detailed_health(session_token: str = Depends(require_auth)):
    """Get detailed system health metrics."""
    from src.main import db, hitl_manager, app, config

    # Calculate uptime
    start_time = getattr(app.state, 'start_time', time.time())
    uptime = int(time.time() - start_time)

    # Get pending HITL count
    pending_hitl = len(hitl_manager.get_pending_requests())

    # Get total tools executed from audit log
    cursor = await db.connection.execute(
        "SELECT COUNT(*) as count FROM audit_log"
    )
    row = await cursor.fetchone()
    tools_executed = row["count"] if row else 0

    # Calculate error rate (last hour)
    cursor = await db.connection.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
        FROM audit_log
        WHERE timestamp > datetime('now', '-1 hour')
        """
    )
    row = await cursor.fetchone()
    total = row["total"] if row and row["total"] else 0
    errors = row["errors"] if row and row["errors"] else 0
    error_rate = errors / total if total > 0 else 0.0

    # Memory metrics
    process = psutil.Process()
    memory_info = process.memory_info()
    memory_used_mb = memory_info.rss / (1024 * 1024)

    system_memory = psutil.virtual_memory()
    memory_total_mb = system_memory.total / (1024 * 1024)
    memory_percent = system_memory.percent

    # CPU metrics
    cpu_percent = process.cpu_percent(interval=0.1)

    # Database size
    db_path = "/app/data/hostbridge.db"
    db_size_mb = 0.0
    if os.path.exists(db_path):
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024)

    # Workspace size
    workspace_path = str(config.workspace.base_dir) if hasattr(config, 'workspace') and hasattr(config.workspace, 'base_dir') else "/workspace"
    workspace_size_mb = 0.0
    if os.path.exists(workspace_path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(workspace_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total_size += os.path.getsize(fp)
                except OSError:
                    pass
        workspace_size_mb = total_size / (1024 * 1024)

    return DetailedHealthResponse(
        uptime=uptime,
        pending_hitl=pending_hitl,
        tools_executed=tools_executed,
        error_rate=error_rate,
        memory_used_mb=round(memory_used_mb, 2),
        memory_total_mb=round(memory_total_mb, 2),
        memory_percent=round(memory_percent, 2),
        cpu_percent=round(cpu_percent, 2),
        db_size_mb=round(db_size_mb, 2),
        db_path=db_path,
        workspace_size_mb=round(workspace_size_mb, 2),
        workspace_path=workspace_path,
        websocket_connections=websocket_connections,
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
        version="0.1.0",
    )


# ---------------------------------------------------------------------------
# Tool Explorer - Built from OpenAPI Contract
# ---------------------------------------------------------------------------

# Valid tool categories derived from mounted sub-apps
TOOL_CATEGORIES = ["fs", "workspace", "shell", "git", "docker", "http", "memory", "plan"]


def _extract_tools_from_openapi(openapi_schema: dict, policy_engine) -> List[ToolSchema]:
    """Extract tool information from the OpenAPI schema.

    This function parses the OpenAPI schema to find tool endpoints,
    extracting their names, categories, descriptions, and schemas.
    HITL requirements are computed from the effective policy configuration.
    """
    tools = []
    paths = openapi_schema.get("paths", {})
    components = openapi_schema.get("components", {}).get("schemas", {})

    for path, path_item in paths.items():
        # Only consider tool API paths (not admin, health, or other routes)
        if not path.startswith("/api/tools/"):
            continue

        # Extract category and name from path: /api/tools/{category}/{name}
        path_parts = path.split("/")
        if len(path_parts) < 5:
            continue

        category = path_parts[3]
        name = path_parts[4]

        # Skip if not a valid tool category
        if category not in TOOL_CATEGORIES:
            continue

        # Get POST operation (all tool endpoints use POST)
        post_op = path_item.get("post")
        if not post_op:
            continue

        # Get operation_id to validate it matches expected pattern
        operation_id = post_op.get("operationId", "")
        if operation_id != f"{category}_{name}":
            continue

        # Get description from the operation
        description = post_op.get("summary", f"Execute {name} operation")
        if post_op.get("description"):
            description = post_op["description"]

        # Extract input schema from request body
        input_schema = {}
        request_body = post_op.get("requestBody")
        if request_body:
            content = request_body.get("content", {})
            json_content = content.get("application/json", {})
            schema_ref = json_content.get("schema", {})

            # Resolve $ref if present
            if "$ref" in schema_ref:
                ref_name = schema_ref["$ref"].split("/")[-1]
                if ref_name in components:
                    input_schema = components[ref_name]
            else:
                input_schema = schema_ref

        # Extract output schema from responses
        output_schema = None
        responses = post_op.get("responses", {})
        success_response = responses.get("200", responses.get("200", {}))
        if success_response:
            content = success_response.get("content", {})
            json_content = content.get("application/json", {})
            schema_ref = json_content.get("schema", {})

            if "$ref" in schema_ref:
                ref_name = schema_ref["$ref"].split("/")[-1]
                if ref_name in components:
                    output_schema = components[ref_name]
            elif schema_ref:
                output_schema = schema_ref

        # Compute HITL requirement from effective policy configuration
        tool_key = f"{category}_{name}"
        requires_hitl = False

        # Check if policy engine has rules and if any rule requires HITL for this tool
        if hasattr(policy_engine, 'rules') and policy_engine.rules:
            for rule in policy_engine.rules:
                if rule.tool == tool_key and rule.action == 'hitl':
                    requires_hitl = True
                    break
        elif hasattr(policy_engine, 'should_require_hitl'):
            # Fallback to checking via should_require_hitl method if available
            requires_hitl = policy_engine.should_require_hitl(tool_key)

        tools.append(ToolSchema(
            name=name,
            category=category,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            requires_hitl=requires_hitl,
        ))

    # Sort by category then name for consistent ordering
    tools.sort(key=lambda t: (t.category, t.name))

    return tools


@router.get("/tools", response_model=ToolListResponse)
async def list_tools(session_token: str = Depends(require_auth)):
    """List all available tools with their schemas derived from OpenAPI contract."""
    from src.main import app, policy_engine

    # Get the OpenAPI schema from the FastAPI app
    openapi_schema = app.openapi()

    # Extract tools from the OpenAPI schema
    tools = _extract_tools_from_openapi(openapi_schema, policy_engine)

    return ToolListResponse(tools=tools, total=len(tools))


@router.get("/tools/{category}/{name}", response_model=ToolSchema)
async def get_tool_schema(
    category: str,
    name: str,
    session_token: str = Depends(require_auth)
):
    """Get detailed schema for a specific tool from OpenAPI contract."""
    from src.main import app, policy_engine

    # Validate category
    if category not in TOOL_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"Tool category '{category}' not found")

    # Get the OpenAPI schema
    openapi_schema = app.openapi()

    # Look for the specific tool endpoint
    tool_path = f"/api/tools/{category}/{name}"
    paths = openapi_schema.get("paths", {})
    components = openapi_schema.get("components", {}).get("schemas", {})

    path_item = paths.get(tool_path)
    if not path_item:
        raise HTTPException(status_code=404, detail=f"Tool '{category}_{name}' not found")

    post_op = path_item.get("post")
    if not post_op:
        raise HTTPException(status_code=404, detail=f"Tool '{category}_{name}' not found")

    # Validate operation_id
    operation_id = post_op.get("operationId", "")
    if operation_id != f"{category}_{name}":
        raise HTTPException(status_code=404, detail=f"Tool '{category}_{name}' not found")

    # Get description
    description = post_op.get("summary", f"Execute {name} operation")
    if post_op.get("description"):
        description = post_op["description"]

    # Extract input schema
    input_schema = {}
    request_body = post_op.get("requestBody")
    if request_body:
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema_ref = json_content.get("schema", {})

        if "$ref" in schema_ref:
            ref_name = schema_ref["$ref"].split("/")[-1]
            if ref_name in components:
                input_schema = components[ref_name]
        else:
            input_schema = schema_ref

    # Extract output schema
    output_schema = None
    responses = post_op.get("responses", {})
    success_response = responses.get("200", {})
    if success_response:
        content = success_response.get("content", {})
        json_content = content.get("application/json", {})
        schema_ref = json_content.get("schema", {})

        if "$ref" in schema_ref:
            ref_name = schema_ref["$ref"].split("/")[-1]
            if ref_name in components:
                output_schema = components[ref_name]
        elif schema_ref:
            output_schema = schema_ref

    # Compute HITL requirement
    tool_key = f"{category}_{name}"
    requires_hitl = False

    if hasattr(policy_engine, 'rules') and policy_engine.rules:
        for rule in policy_engine.rules:
            if rule.tool == tool_key and rule.action == 'hitl':
                requires_hitl = True
                break
    elif hasattr(policy_engine, 'should_require_hitl'):
        requires_hitl = policy_engine.should_require_hitl(tool_key)

    return ToolSchema(
        name=name,
        category=category,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        requires_hitl=requires_hitl,
    )


# ---------------------------------------------------------------------------
# Configuration Viewer
# ---------------------------------------------------------------------------

@router.get("/config", response_model=ConfigResponse)
async def get_config(session_token: str = Depends(require_auth)):
    """Get current configuration (sanitized for security)."""
    from src.main import config, policy_engine

    # Extract safe config values
    http_config = {}
    if hasattr(config, 'http'):
        http_config = {
            "block_private_ips": getattr(config.http, 'block_private_ips', True),
            "block_metadata_endpoints": getattr(config.http, 'block_metadata_endpoints', True),
            "allow_domains": getattr(config.http, 'allow_domains', []),
            "block_domains": getattr(config.http, 'block_domains', []),
            "timeout_seconds": getattr(config.http, 'timeout_seconds', 30),
        }

    tool_configs = {}
    if hasattr(config, 'tools'):
        for tool_name in ['fs', 'workspace', 'shell', 'git', 'docker', 'http', 'memory', 'plan']:
            tool_cfg = getattr(config.tools, tool_name, None)
            if tool_cfg:
                tool_configs[tool_name] = {
                    "enabled": getattr(tool_cfg, 'enabled', True),
                }
                if hasattr(tool_cfg, 'policy'):
                    tool_configs[tool_name]["policy"] = tool_cfg.policy

    policy_rules_count = 0
    if hasattr(policy_engine, 'rules'):
        policy_rules_count = len(policy_engine.rules)

    return ConfigResponse(
        auth_enabled=True,  # Auth is always enabled for admin
        workspace_path=str(config.workspace.base_dir) if hasattr(config, 'workspace') and hasattr(config.workspace, 'base_dir') else "/workspace",
        database_path="/app/data/hostbridge.db",
        log_level=getattr(config.audit, 'log_level', 'INFO') if hasattr(config, 'audit') else 'INFO',
        http_config=http_config,
        policy_rules_count=policy_rules_count,
        tool_configs=tool_configs,
    )


# ---------------------------------------------------------------------------
# Audit Log Filtering and Export
# ---------------------------------------------------------------------------

@router.get("/audit/filtered", response_model=AuditLogFilterResponse)
async def get_filtered_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    tool_category: Optional[str] = Query(None),
    tool_name: Optional[str] = Query(None),
    protocol: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    session_token: str = Depends(require_auth)
):
    """Get audit logs with filtering support."""
    from src.main import db

    # Build query
    conditions = []
    params = {}

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if tool_category:
        conditions.append("tool_category = :tool_category")
        params["tool_category"] = tool_category

    if tool_name:
        conditions.append("tool_name = :tool_name")
        params["tool_name"] = tool_name

    if protocol:
        conditions.append("protocol = :protocol")
        params["protocol"] = protocol

    if start_time:
        conditions.append("timestamp >= :start_time")
        params["start_time"] = start_time

    if end_time:
        conditions.append("timestamp <= :end_time")
        params["end_time"] = end_time

    if search:
        conditions.append("(tool_name LIKE :search OR tool_category LIKE :search OR error_message LIKE :search)")
        params["search"] = f"%{search}%"

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Get total count
    count_query = f"SELECT COUNT(*) as count FROM audit_log WHERE {where_clause}"
    cursor = await db.connection.execute(count_query, params)
    row = await cursor.fetchone()
    total = row["count"] if row else 0

    # Get filtered count (same as total when no pagination)
    filtered = total

    # Get logs with pagination
    query = f"""
        SELECT * FROM audit_log
        WHERE {where_clause}
        ORDER BY timestamp DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    cursor = await db.connection.execute(query, params)
    rows = await cursor.fetchall()

    logs = [dict(row) for row in rows]

    return AuditLogFilterResponse(logs=logs, total=total, filtered=filtered)


@router.get("/audit/export")
async def export_audit_logs(
    format: str = Query("json", pattern="^(json|csv)$"),
    status: Optional[str] = Query(None),
    tool_category: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    session_token: str = Depends(require_auth)
):
    """Export audit logs as JSON or CSV."""
    from src.main import db

    # Build query
    conditions = []
    params = {}

    if status:
        conditions.append("status = :status")
        params["status"] = status

    if tool_category:
        conditions.append("tool_category = :tool_category")
        params["tool_category"] = tool_category

    if start_time:
        conditions.append("timestamp >= :start_time")
        params["start_time"] = start_time

    if end_time:
        conditions.append("timestamp <= :end_time")
        params["end_time"] = end_time

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    query = f"SELECT * FROM audit_log WHERE {where_clause} ORDER BY timestamp DESC"
    cursor = await db.connection.execute(query, params)
    rows = await cursor.fetchall()

    logs = [dict(row) for row in rows]

    if format == "json":
        # Return JSON file
        import io

        output = io.BytesIO()
        output.write(json.dumps(logs, indent=2, default=str).encode('utf-8'))
        output.seek(0)

        return StreamingResponse(
            output,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )
    else:
        # Return CSV file
        import csv
        import io

        output = io.StringIO()
        if logs:
            writer = csv.DictWriter(output, fieldnames=logs[0].keys())
            writer.writeheader()
            writer.writerows(logs)

        output.seek(0)
        bytes_output = io.BytesIO(output.getvalue().encode('utf-8'))

        return StreamingResponse(
            bytes_output,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )


# ---------------------------------------------------------------------------
# Container Logs
# ---------------------------------------------------------------------------

@router.get("/containers")
async def list_containers(session_token: str = Depends(require_auth)):
    """List all Docker containers (for log viewing)."""
    from src.main import docker_tools

    if not docker_tools:
        raise HTTPException(status_code=503, detail="Docker tools not available")

    try:
        result = await docker_tools.list_containers(DockerListRequest(all=True))
        return result
    except RuntimeError as e:
        error = str(e)
        logger.error("failed_to_list_containers", error=error)
        if "docker support not available" in error.lower() or "failed to connect to docker daemon" in error.lower():
            raise HTTPException(status_code=503, detail=error)
        raise HTTPException(status_code=500, detail=error)
    except Exception as e:
        logger.error("failed_to_list_containers", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containers/{container_id}/logs")
async def get_container_logs(
    container_id: str,
    tail: int = Query(100, ge=1, le=1000),
    follow: bool = Query(False),
    session_token: str = Depends(require_auth)
):
    """Get logs from a specific Docker container."""
    from src.main import docker_tools

    if not docker_tools:
        raise HTTPException(status_code=503, detail="Docker tools not available")

    try:
        request = DockerLogsRequest(container=container_id, tail=tail, follow=follow)
        result = await docker_tools.get_logs(request)
        return result
    except ValueError as e:
        logger.warning("container_logs_not_found", container_id=container_id, error=str(e))
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        error = str(e)
        logger.error("failed_to_get_container_logs", container_id=container_id, error=error)
        if "docker support not available" in error.lower() or "failed to connect to docker daemon" in error.lower():
            raise HTTPException(status_code=503, detail=error)
        raise HTTPException(status_code=500, detail=error)
    except Exception as e:
        logger.error("failed_to_get_container_logs", container_id=container_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Statistics for Dashboard
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_dashboard_stats(session_token: str = Depends(require_auth)):
    """Get summary statistics for dashboard."""
    from src.main import db, hitl_manager

    # Tool executions by category (last 24 hours)
    cursor = await db.connection.execute(
        """
        SELECT tool_category, COUNT(*) as count
        FROM audit_log
        WHERE timestamp > datetime('now', '-24 hours')
        GROUP BY tool_category
        ORDER BY count DESC
        """
    )
    tool_stats = [dict(row) for row in await cursor.fetchall()]

    # Status distribution (last 24 hours)
    cursor = await db.connection.execute(
        """
        SELECT status, COUNT(*) as count
        FROM audit_log
        WHERE timestamp > datetime('now', '-24 hours')
        GROUP BY status
        """
    )
    status_stats = [dict(row) for row in await cursor.fetchall()]

    # Hourly distribution (last 24 hours)
    cursor = await db.connection.execute(
        """
        SELECT strftime('%Y-%m-%d %H:00', timestamp) as hour, COUNT(*) as count
        FROM audit_log
        WHERE timestamp > datetime('now', '-24 hours')
        GROUP BY hour
        ORDER BY hour
        """
    )
    hourly_stats = [dict(row) for row in await cursor.fetchall()]

    # Average duration by tool (last 24 hours)
    cursor = await db.connection.execute(
        """
        SELECT tool_category, tool_name, AVG(duration_ms) as avg_duration_ms
        FROM audit_log
        WHERE timestamp > datetime('now', '-24 hours')
        AND duration_ms IS NOT NULL
        GROUP BY tool_category, tool_name
        ORDER BY avg_duration_ms DESC
        LIMIT 10
        """
    )
    duration_stats = [dict(row) for row in await cursor.fetchall()]

    return {
        "tool_stats": tool_stats,
        "status_stats": status_stats,
        "hourly_stats": hourly_stats,
        "duration_stats": duration_stats,
        "pending_hitl": len(hitl_manager.get_pending_requests()),
    }
