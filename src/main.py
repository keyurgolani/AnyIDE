"""Main FastAPI application."""

import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi_mcp import FastApiMCP

from src.config import load_config
from src.database import Database
from src.logging_config import setup_logging, get_logger
from src.workspace import WorkspaceManager, SecurityError
from src.audit import AuditLogger
from src.policy import PolicyEngine
from src.hitl import HITLManager
from src.secrets import SecretManager, SecretNotFoundError
from src.tools.fs_tools import FilesystemTools
from src.tools.workspace_tools import WorkspaceTools
from src.tools.shell_tools import ShellTools
from src.tools.git_tools import GitTools
from src.tools.docker_tools import DockerTools
from src.tools.http_tools import HttpTools, SSRFError, DomainBlockedError
from src.tools.memory_tools import MemoryTools, NodeNotFoundError
from src.tools.plan_tools import PlanTools, PlanNotFoundError, PlanValidationError
from src.models import (
    FsReadRequest,
    FsReadResponse,
    FsWriteRequest,
    FsWriteResponse,
    FsListRequest,
    FsListResponse,
    FsSearchRequest,
    FsSearchResponse,
    ShellExecuteRequest,
    ShellExecuteResponse,
    WorkspaceInfoResponse,
    GitStatusRequest,
    GitStatusResponse,
    GitLogRequest,
    GitLogResponse,
    GitDiffRequest,
    GitDiffResponse,
    GitCommitRequest,
    GitCommitResponse,
    GitPushRequest,
    GitPushResponse,
    GitPullRequest,
    GitPullResponse,
    GitCheckoutRequest,
    GitCheckoutResponse,
    GitBranchRequest,
    GitBranchResponse,
    GitListBranchesRequest,
    GitListBranchesResponse,
    GitStashRequest,
    GitStashResponse,
    GitShowRequest,
    GitShowResponse,
    GitRemoteRequest,
    GitRemoteResponse,
    DockerListRequest,
    DockerListResponse,
    DockerInspectRequest,
    DockerInspectResponse,
    DockerLogsRequest,
    DockerLogsResponse,
    DockerActionRequest,
    DockerActionResponse,
    WorkspaceSecretsListResponse,
    HttpRequestRequest,
    HttpRequestResponse,
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemoryGetRequest,
    MemoryGetResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryUpdateRequest,
    MemoryUpdateResponse,
    MemoryDeleteRequest,
    MemoryDeleteResponse,
    MemoryLinkRequest,
    MemoryLinkResponse,
    MemoryChildrenRequest,
    MemoryAncestorsRequest,
    MemoryRelatedRequest,
    MemorySubtreeRequest,
    MemoryNodesResponse,
    MemoryStatsResponse,
    PlanCreateRequest,
    PlanCreateResponse,
    PlanExecuteRequest,
    PlanExecuteResponse,
    PlanStatusRequest,
    PlanStatusResponse,
    PlanListResponse,
    PlanCancelRequest,
    PlanCancelResponse,
    ErrorResponse,
)

# Global state
config = load_config()
setup_logging(config.audit.log_level)
logger = get_logger(__name__)

# Initialize components
db = Database(db_path=os.getenv("DB_PATH", "/data/hostbridge.db"))
workspace_manager = WorkspaceManager(config.workspace.base_dir)
audit_logger = AuditLogger(db)
policy_engine = PolicyEngine(config)
hitl_manager = HITLManager(db, config.hitl.default_ttl_seconds)

# Initialize secrets manager
secret_manager = SecretManager(config.secrets.file)

# Initialize tools
fs_tools = FilesystemTools(workspace_manager)
workspace_tools = WorkspaceTools(workspace_manager, secret_manager)
shell_tools = ShellTools(workspace_manager)
git_tools = GitTools(workspace_manager)
docker_tools = DockerTools()
http_tools = HttpTools(config.http)
memory_tools = MemoryTools(db)


async def _tool_dispatch(category: str, name: str, params: dict) -> dict:
    """Dispatch a tool call for plan task execution.

    Uses inspect to auto-detect the request model from the method signature,
    so no manual mapping is needed when new tools are added.
    """
    import inspect

    tool_map = {
        "fs": fs_tools,
        "shell": shell_tools,
        "git": git_tools,
        "http": http_tools,
        "memory": memory_tools,
        "workspace": workspace_tools,
        "docker": docker_tools,
    }

    tool_obj = tool_map.get(category)
    if not tool_obj:
        raise ValueError(
            f"Unknown tool category '{category}'. Available: {sorted(tool_map)}"
        )

    method = getattr(tool_obj, name, None)
    if not method or not callable(method):
        raise ValueError(f"Unknown tool '{name}' in category '{category}'")

    sig = inspect.signature(method)
    param_list = [p for pname, p in sig.parameters.items() if pname != "self"]

    if not param_list:
        # Methods like memory_tools.roots() / memory_tools.stats() take no args
        result = await method()
    else:
        annotation = param_list[0].annotation
        if annotation is inspect.Parameter.empty:
            raise ValueError(
                f"Tool method '{category}.{name}' has unannotated first parameter"
            )
        request = annotation(**params)
        result = await method(request)

    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(result) if result else {}


plan_tools = PlanTools(db, hitl_manager, _tool_dispatch)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("starting_hostbridge", version="0.1.0")
    app.state.start_time = time.time()
    await db.connect()
    await hitl_manager.start()
    logger.info("hostbridge_started")
    
    yield
    
    # Shutdown
    logger.info("shutting_down_hostbridge")
    await hitl_manager.stop()
    await docker_tools.close()
    await db.close()
    logger.info("hostbridge_stopped")


# Create FastAPI apps
app = FastAPI(
    title="AnyIDE",
    description="Self-hosted tool server exposing host-machine capabilities to LLM clients via MCP and OpenAPI protocols",
    version="0.1.0",
    lifespan=lifespan,
)

# Per-category sub-apps
fs_app = FastAPI(
    title="AnyIDE — Filesystem Tools",
    description="Filesystem operations for AnyIDE",
    version="0.1.0",
)

workspace_app = FastAPI(
    title="AnyIDE — Workspace Tools",
    description="Workspace management for AnyIDE",
    version="0.1.0",
)

git_app = FastAPI(
    title="AnyIDE — Git Tools",
    description="Git repository management for AnyIDE",
    version="0.1.0",
)

docker_app = FastAPI(
    title="AnyIDE — Docker Tools",
    description="Docker container management for AnyIDE",
    version="0.1.0",
)

memory_app = FastAPI(
    title="AnyIDE — Memory Tools",
    description="Graph-based knowledge storage for AnyIDE",
    version="0.1.0",
)

plan_app = FastAPI(
    title="AnyIDE — Plan Tools",
    description="DAG-based multi-step plan execution for AnyIDE",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Error handlers
@app.exception_handler(SecurityError)
async def security_error_handler(request: Request, exc: SecurityError):
    """Handle security errors."""
    logger.warning("security_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content=ErrorResponse(
            error_type="security_error",
            message=str(exc),
            suggestion="Ensure the path is within the workspace boundary",
        ).model_dump(),
    )


@app.exception_handler(FileNotFoundError)
async def file_not_found_handler(request: Request, exc: FileNotFoundError):
    """Handle file not found errors."""
    logger.warning("file_not_found", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error_type="file_not_found",
            message=str(exc),
            suggestion_tool="fs_list",
        ).model_dump(),
    )


@app.exception_handler(NodeNotFoundError)
async def node_not_found_handler(request: Request, exc: NodeNotFoundError):
    """Handle memory node not found errors."""
    logger.warning("node_not_found", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error_type="node_not_found",
            message=str(exc),
            suggestion_tool="memory_search",
        ).model_dump(),
    )


@app.exception_handler(PlanNotFoundError)
async def plan_not_found_handler(request: Request, exc: PlanNotFoundError):
    """Handle plan not found errors."""
    logger.warning("plan_not_found", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error_type="plan_not_found",
            message=str(exc),
            suggestion="Use the plan_id returned by plan_create, or call plan_list to look up available plan IDs.",
            suggestion_tool="plan_list",
        ).model_dump(),
    )


@app.exception_handler(PlanValidationError)
async def plan_validation_error_handler(request: Request, exc: PlanValidationError):
    """Handle plan DAG validation errors."""
    logger.warning("plan_validation_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=ErrorResponse(
            error_type="plan_validation_error",
            message=str(exc),
        ).model_dump(),
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle value errors."""
    logger.warning("value_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error_type="invalid_parameter",
            message=str(exc),
        ).model_dump(),
    )


@app.exception_handler(TimeoutError)
async def timeout_error_handler(request: Request, exc: TimeoutError):
    """Handle timeout errors (e.g. HITL timeout)."""
    logger.warning("timeout_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_408_REQUEST_TIMEOUT,
        content=ErrorResponse(
            error_type="timeout",
            message=str(exc),
            suggestion="Retry the request or contact the administrator",
        ).model_dump(),
    )


@app.exception_handler(ConnectionError)
async def connection_error_handler(request: Request, exc: ConnectionError):
    """Handle HTTP connection errors."""
    logger.warning("connection_error", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content=ErrorResponse(
            error_type="connection_error",
            message=str(exc),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception):
    """Handle general errors."""
    logger.error("unexpected_error", error=str(exc), path=request.url.path, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_type="internal_error",
            message="An unexpected error occurred. Please check the logs.",
        ).model_dump(),
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


# Tool execution wrapper with policy and audit
async def execute_tool(
    tool_category: str,
    tool_name: str,
    params: Dict[str, Any],
    tool_func,
    protocol: str = "openapi",
    force_hitl: bool = False,
    hitl_reason: Optional[str] = None,
):
    """Execute a tool with policy enforcement and audit logging.

    Pipeline order:
      1. Policy check (runs on original/template params)
      2. HITL gate (if required)
      3. Tool execution (tool_func is expected to have already received a resolved request)
      4. Audit log (records *original* template params, not resolved values)

    Secret template resolution ({{secret:KEY}} → actual values) happens at the
    endpoint level via ``resolve_request_secrets()`` BEFORE the execute_tool call.
    The ``params`` dict passed here must contain the original (template) values so
    that policy patterns and audit logs see what the caller intended, not the
    resolved secrets.

    Args:
        tool_category: Tool category
        tool_name: Tool name
        params: Tool parameters with original template strings (for policy/audit)
        tool_func: Tool function to execute (closure bound to a *resolved* request)
        protocol: Protocol used (openapi or mcp)
        force_hitl: Force HITL approval regardless of policy
        hitl_reason: Reason for HITL requirement

    Returns:
        Tool execution result
    """
    start_time = time.time()

    # --- 1. Policy check on ORIGINAL (template) params ---
    if force_hitl:
        decision = "hitl"
        reason = hitl_reason or "Requires approval"
    else:
        decision, reason = policy_engine.evaluate(tool_category, tool_name, params)

    if decision == "block":
        await audit_logger.log_execution(
            tool_name=tool_name,
            tool_category=tool_category,
            protocol=protocol,
            request_params=params,  # original templates recorded
            status="blocked",
            error_message=reason,
        )
        raise SecurityError(f"Operation blocked: {reason}")

    # --- 2. HITL gate ---
    hitl_request_id = None
    if decision == "hitl":
        logger.info("hitl_required", tool=f"{tool_category}_{tool_name}", reason=reason)

        hitl_request = await hitl_manager.create_request(
            tool_name=tool_name,
            tool_category=tool_category,
            request_params=params,
            request_context={"protocol": protocol},
            policy_rule_matched=reason,
        )
        hitl_request_id = hitl_request.id

        decision_result = await hitl_manager.wait_for_decision(hitl_request.id)

        if decision_result == "rejected":
            await audit_logger.log_execution(
                tool_name=tool_name,
                tool_category=tool_category,
                protocol=protocol,
                request_params=params,
                status="hitl_rejected",
                error_message="Operation rejected by administrator",
                hitl_request_id=hitl_request_id,
            )
            raise SecurityError(
                "Operation not permitted. The request was reviewed and rejected."
            )

        elif decision_result == "expired":
            await audit_logger.log_execution(
                tool_name=tool_name,
                tool_category=tool_category,
                protocol=protocol,
                request_params=params,
                status="hitl_expired",
                error_message="Operation timed out waiting for approval",
                hitl_request_id=hitl_request_id,
            )
            raise TimeoutError(
                "Operation timed out waiting for processing. Please try again later."
            )

        logger.info("hitl_approved_executing", tool=f"{tool_category}_{tool_name}")

    # --- 3. Execute tool ---
    try:
        result = await tool_func()
        duration_ms = int((time.time() - start_time) * 1000)

        # --- 5. Audit log: record ORIGINAL template params (not resolved) ---
        await audit_logger.log_execution(
            tool_name=tool_name,
            tool_category=tool_category,
            protocol=protocol,
            request_params=params,  # templates, not resolved values
            response_body=result.model_dump() if hasattr(result, "model_dump") else result,
            status="success" if decision != "hitl" else "hitl_approved",
            duration_ms=duration_ms,
            workspace_dir=workspace_manager.base_dir,
            hitl_request_id=hitl_request_id,
        )

        return result

    except (SecurityError, SecretNotFoundError, SSRFError, DomainBlockedError):
        raise
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        # Mask any leaked secret values from the error message before logging
        safe_error = secret_manager.mask_value(str(e))
        await audit_logger.log_execution(
            tool_name=tool_name,
            tool_category=tool_category,
            protocol=protocol,
            request_params=params,  # original templates
            status="error",
            duration_ms=duration_ms,
            error_message=safe_error,
            hitl_request_id=hitl_request_id,
        )
        raise


def resolve_request_secrets(request):
    """Resolve {{secret:KEY}} templates in a pydantic request model.

    Creates a deep copy of the request dict with all template strings replaced
    by their actual secret values, then constructs a new model of the same type.

    The original ``request`` object is NOT mutated — callers should pass the
    ORIGINAL params dict to ``execute_tool`` for audit/policy, while passing
    the resolved model to the tool function closure.

    Args:
        request: Any pydantic BaseModel instance (request model)

    Returns:
        New instance of the same model class with all templates resolved

    Raises:
        ValueError (wrapping SecretNotFoundError): If a key is not found
    """
    if not secret_manager.has_templates(request.model_dump()):
        return request  # Nothing to resolve — return original
    try:
        resolved_dict = secret_manager.resolve_params(request.model_dump())
        return type(request)(**resolved_dict)
    except SecretNotFoundError as exc:
        raise ValueError(str(exc)) from exc


# Filesystem tools - Root app
@app.post(
    "/api/tools/fs/read",
    operation_id="fs_read",
    summary="Read File",
    description="""Read the contents of a file at the specified path.

The path is relative to the workspace directory unless an absolute 
path within the workspace is provided. Returns the file contents 
as text.

Use this tool when you need to:
- Examine file contents before making changes
- Read configuration files
- Inspect source code
- Check log files

Required: path (relative to workspace directory)
Optional: encoding, max_lines (for large files), line_start/line_end (for specific sections)""",
    response_model=FsReadResponse,
    tags=["filesystem"],
)
async def fs_read_root(request: FsReadRequest) -> FsReadResponse:
    """Read file contents (root app endpoint)."""
    return await execute_tool(
        "fs",
        "read",
        request.model_dump(),
        lambda: fs_tools.read(request),
    )


# Filesystem tools - Sub-app
@fs_app.post(
    "/read",
    operation_id="fs_read",
    summary="Read File",
    description="""Read the contents of a file at the specified path.

The path is relative to the workspace directory unless an absolute 
path within the workspace is provided. Returns the file contents 
as text.

Use this tool when you need to:
- Examine file contents before making changes
- Read configuration files
- Inspect source code
- Check log files

Required: path (relative to workspace directory)
Optional: encoding, max_lines (for large files), line_start/line_end (for specific sections)""",
    response_model=FsReadResponse,
    tags=["filesystem"],
)
async def fs_read_sub(request: FsReadRequest) -> FsReadResponse:
    """Read file contents (sub-app endpoint)."""
    return await execute_tool(
        "fs",
        "read",
        request.model_dump(),
        lambda: fs_tools.read(request),
    )


# Workspace tools - Root app
@app.post(
    "/api/tools/workspace/info",
    operation_id="workspace_info",
    summary="Get Workspace Information",
    description="""Get information about the workspace configuration.

Returns the default workspace directory, available paths, disk usage,
and available tool categories.

Use this tool when you need to:
- Understand the workspace boundaries
- Check available disk space
- See what tool categories are available
- Get the base workspace path for other operations

No parameters required.""",
    response_model=WorkspaceInfoResponse,
    tags=["workspace"],
)
async def workspace_info_root() -> WorkspaceInfoResponse:
    """Get workspace information (root app endpoint)."""
    return await execute_tool(
        "workspace",
        "info",
        {},
        lambda: workspace_tools.info(),
    )


# Workspace tools - Sub-app
@workspace_app.post(
    "/info",
    operation_id="workspace_info",
    summary="Get Workspace Information",
    description="""Get information about the workspace configuration.

Returns the default workspace directory, available paths, disk usage,
and available tool categories.

Use this tool when you need to:
- Understand the workspace boundaries
- Check available disk space
- See what tool categories are available
- Get the base workspace path for other operations

No parameters required.""",
    response_model=WorkspaceInfoResponse,
    tags=["workspace"],
)
async def workspace_info_sub() -> WorkspaceInfoResponse:
    """Get workspace information (sub-app endpoint)."""
    return await execute_tool(
        "workspace",
        "info",
        {},
        lambda: workspace_tools.info(),
    )


# workspace_secrets_list endpoints
@app.post(
    "/api/tools/workspace/secrets/list",
    operation_id="workspace_secrets_list",
    summary="List Configured Secrets",
    description="""List the names (keys) of all configured secrets.

Secret VALUES are never exposed — only their names are returned so you
know which keys are available for use as {{secret:KEY}} templates in
tool parameters (headers, environment variables, etc.).

Use this tool to:
- Discover available secret keys before using them in requests
- Verify that a required secret is configured

No parameters required.""",
    response_model=WorkspaceSecretsListResponse,
    tags=["workspace"],
)
async def workspace_secrets_list_root() -> WorkspaceSecretsListResponse:
    """List configured secret keys (root app endpoint)."""
    return await execute_tool(
        "workspace",
        "secrets_list",
        {},
        lambda: _workspace_secrets_list(),
    )


@workspace_app.post(
    "/secrets/list",
    operation_id="workspace_secrets_list",
    summary="List Configured Secrets",
    description="""List the names (keys) of all configured secrets.

Secret VALUES are never exposed — only their names are returned so you
know which keys are available for use as {{secret:KEY}} templates in
tool parameters (headers, environment variables, etc.).

Use this tool to:
- Discover available secret keys before using them in requests
- Verify that a required secret is configured

No parameters required.""",
    response_model=WorkspaceSecretsListResponse,
    tags=["workspace"],
)
async def workspace_secrets_list_sub() -> WorkspaceSecretsListResponse:
    """List configured secret keys (sub-app endpoint)."""
    return await execute_tool(
        "workspace",
        "secrets_list",
        {},
        lambda: _workspace_secrets_list(),
    )


async def _workspace_secrets_list() -> WorkspaceSecretsListResponse:
    """Internal helper to build the secrets list response."""
    import asyncio
    # Run synchronous call in executor to keep async path clean
    keys = secret_manager.list_keys()
    return WorkspaceSecretsListResponse(
        keys=keys,
        count=len(keys),
        secrets_file=str(secret_manager.secrets_file),
    )


# http_request endpoints

# Create http sub-app
http_app = FastAPI(
    title="AnyIDE — HTTP Tools",
    description="HTTP client with SSRF protection for AnyIDE",
    version="0.1.0",
)


@app.post(
    "/api/tools/http/request",
    operation_id="http_request",
    summary="Make HTTP Request",
    description="""Make an HTTP request to an external URL.

Supported methods: GET, POST, PUT, PATCH, DELETE, HEAD

Use {{secret:KEY}} syntax in headers or body values to inject secrets
without exposing them in the request parameters or audit logs.

Security protections:
- Private/reserved IP addresses are blocked (SSRF protection)
- Cloud metadata endpoints (169.254.169.254, etc.) are blocked
- Domain allowlist/blocklist enforced from configuration
- Response body is truncated at the configured size limit

Required: url
Optional: method (default: GET), headers, body, json_body, timeout (max 120s), follow_redirects""",
    response_model=HttpRequestResponse,
    tags=["http"],
)
async def http_request_root(request: HttpRequestRequest) -> HttpRequestResponse:
    """Make HTTP request (root app endpoint)."""
    # Resolve {{secret:KEY}} templates → execution uses resolved request;
    # execute_tool receives original params dict for policy/audit logging.
    resolved = resolve_request_secrets(request)
    return await execute_tool(
        "http",
        "request",
        request.model_dump(),
        lambda: http_tools.request(resolved),
    )


@http_app.post(
    "/request",
    operation_id="http_request",
    summary="Make HTTP Request",
    description="""Make an HTTP request to an external URL.

Supported methods: GET, POST, PUT, PATCH, DELETE, HEAD

Use {{secret:KEY}} syntax in headers or body values to inject secrets
without exposing them in the request parameters or audit logs.

Security protections:
- Private/reserved IP addresses are blocked (SSRF protection)
- Cloud metadata endpoints (169.254.169.254, etc.) are blocked
- Domain allowlist/blocklist enforced from configuration
- Response body is truncated at the configured size limit

Required: url
Optional: method (default: GET), headers, body, json_body, timeout (max 120s), follow_redirects""",
    response_model=HttpRequestResponse,
    tags=["http"],
)
async def http_request_sub(request: HttpRequestRequest) -> HttpRequestResponse:
    """Make HTTP request (sub-app endpoint)."""
    resolved = resolve_request_secrets(request)
    return await execute_tool(
        "http",
        "request",
        request.model_dump(),
        lambda: http_tools.request(resolved),
    )


# Include admin API
from src.admin_api import router as admin_router
app.include_router(admin_router)

# Serve admin dashboard static files with SPA fallback
import os
from fastapi.responses import FileResponse

static_dir = os.path.join(os.path.dirname(__file__), "..", "static", "admin")
if os.path.exists(static_dir):
    # Mount static assets
    app.mount("/admin/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="admin-assets")
    
    # Serve index.html for all admin routes (SPA fallback)
    @app.get("/admin/{full_path:path}")
    async def serve_admin(full_path: str):
        """Serve admin dashboard with SPA fallback."""
        # Try to serve the file if it exists
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise serve index.html (SPA fallback)
        return FileResponse(os.path.join(static_dir, "index.html"))
    
    logger.info("admin_dashboard_mounted", path="/admin")
else:
    logger.warning("admin_dashboard_not_found", path=static_dir)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
    )


# WebSocket endpoint for HITL
from fastapi import WebSocket, WebSocketDisconnect
import json

class ConnectionManager:
    """Manage WebSocket connections."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", total_connections=len(self.active_connections))
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("websocket_disconnected", total_connections=len(self.active_connections))
    
    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error("websocket_send_error", error=str(e))
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for connection in disconnected:
            if connection in self.active_connections:
                self.active_connections.remove(connection)

connection_manager = ConnectionManager()

# Register WebSocket callback with HITL manager
async def hitl_websocket_callback(event_type: str, data: dict):
    """Callback for HITL events to broadcast via WebSocket."""
    await connection_manager.broadcast({
        "type": event_type,
        "data": data,
    })

hitl_manager.register_websocket_callback(hitl_websocket_callback)


@app.websocket("/ws/hitl")
async def websocket_hitl(websocket: WebSocket):
    """WebSocket endpoint for HITL notifications and decisions."""
    await connection_manager.connect(websocket)
    
    try:
        # Send current pending requests
        pending = hitl_manager.get_pending_requests()
        await websocket.send_json({
            "type": "pending_requests",
            "data": [req.to_dict() for req in pending],
        })
        
        # Listen for decisions
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "request_pending":
                # Client is requesting current pending requests
                pending = hitl_manager.get_pending_requests()
                await websocket.send_json({
                    "type": "pending_requests",
                    "data": [req.to_dict() for req in pending],
                })
            
            elif data.get("type") == "hitl_decision":
                decision_data = data.get("data", {})
                request_id = decision_data.get("id")
                decision = decision_data.get("decision")
                note = decision_data.get("note")
                
                if not request_id or not decision:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": "Missing required fields: id and decision"},
                    })
                    continue
                
                try:
                    if decision == "approve":
                        await hitl_manager.approve(request_id, reviewer="admin", note=note)
                        await websocket.send_json({
                            "type": "decision_accepted",
                            "data": {"id": request_id, "decision": "approved"},
                        })
                    elif decision == "reject":
                        await hitl_manager.reject(request_id, reviewer="admin", note=note)
                        await websocket.send_json({
                            "type": "decision_accepted",
                            "data": {"id": request_id, "decision": "rejected"},
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": f"Invalid decision: {decision}"},
                        })
                
                except ValueError as e:
                    await websocket.send_json({
                        "type": "error",
                        "data": {"message": str(e)},
                    })
    
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error("websocket_error", error=str(e), exc_info=True)
        connection_manager.disconnect(websocket)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for streaming audit log events.

    Provides real-time updates for tool executions, errors, and HITL decisions.
    Clients can filter events by category, status, etc.
    """
    await websocket.accept()
    from src.admin_api import increment_ws_connections, decrement_ws_connections
    increment_ws_connections()

    try:
        # Send recent audit log entries on connect
        recent_logs = await audit_logger.get_logs(limit=10)
        await websocket.send_json({
            "type": "initial_logs",
            "data": recent_logs,
        })

        # Listen for client commands
        last_timestamp = None
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "subscribe":
                # Client wants to subscribe to new log events
                # For now, we poll for new logs periodically
                # In a production system, this would use a pub/sub mechanism
                poll_interval = data.get("poll_interval", 2)  # seconds

                while True:
                    try:
                        # Check for new logs
                        new_logs = await audit_logger.get_logs(limit=50)

                        if new_logs:
                            # Filter to only new logs since last check
                            if last_timestamp:
                                filtered_logs = [
                                    log for log in new_logs
                                    if log.get("timestamp", "") > last_timestamp
                                ]
                            else:
                                filtered_logs = new_logs

                            if filtered_logs:
                                await websocket.send_json({
                                    "type": "new_logs",
                                    "data": filtered_logs,
                                })
                                last_timestamp = filtered_logs[0].get("timestamp")

                        # Wait for next poll
                        await asyncio.sleep(poll_interval)

                    except WebSocketDisconnect:
                        raise
                    except Exception as e:
                        logger.error("log_stream_error", error=str(e))
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": str(e)},
                        })
                        break

            elif data.get("type") == "get_logs":
                # Client requests specific logs
                limit = data.get("limit", 50)
                category = data.get("category")
                status = data.get("status")

                logs = await audit_logger.get_logs(limit=limit)
                # Filter if needed
                if category:
                    logs = [l for l in logs if l.get("tool_category") == category]
                if status:
                    logs = [l for l in logs if l.get("status") == status]

                await websocket.send_json({
                    "type": "logs",
                    "data": logs,
                })

    except WebSocketDisconnect:
        logger.info("logs_websocket_disconnected")
    except Exception as e:
        logger.error("logs_websocket_error", error=str(e), exc_info=True)
    finally:
        decrement_ws_connections()


# fs_write endpoints
@app.post(
    "/api/tools/fs/write",
    operation_id="fs_write",
    summary="Write File",
    description="""Write content to a file at the specified path.

The path is relative to the workspace directory unless an absolute 
path within the workspace is provided.

Use this tool when you need to:
- Create new files
- Update existing files
- Append content to files
- Save generated content

Required: path, content
Optional: mode ('create', 'overwrite', 'append'), workspace_dir, create_dirs, encoding

Note: Writing to configuration files (*.conf, *.env, *.yaml, *.yml) requires approval.""",
    response_model=FsWriteResponse,
    tags=["filesystem"],
)
async def fs_write_root(request: FsWriteRequest) -> FsWriteResponse:
    """Write file contents (root app endpoint)."""
    return await execute_tool(
        "fs",
        "write",
        request.model_dump(),
        lambda: fs_tools.write(request),
    )


@fs_app.post(
    "/write",
    operation_id="fs_write",
    summary="Write File",
    description="""Write content to a file at the specified path.

The path is relative to the workspace directory unless an absolute 
path within the workspace is provided.

Use this tool when you need to:
- Create new files
- Update existing files
- Append content to files
- Save generated content

Required: path, content
Optional: mode ('create', 'overwrite', 'append'), workspace_dir, create_dirs, encoding

Note: Writing to configuration files (*.conf, *.env, *.yaml, *.yml) requires approval.""",
    response_model=FsWriteResponse,
    tags=["filesystem"],
)
async def fs_write_sub(request: FsWriteRequest) -> FsWriteResponse:
    """Write file contents (sub-app endpoint)."""
    return await execute_tool(
        "fs",
        "write",
        request.model_dump(),
        lambda: fs_tools.write(request),
    )


# fs_list endpoints
@app.post(
    "/api/tools/fs/list",
    operation_id="fs_list",
    summary="List Directory",
    description="""List contents of a directory.

The path is relative to the workspace directory unless an absolute 
path within the workspace is provided.

Use this tool when you need to:
- Browse directory contents
- Find files in a directory
- Explore project structure
- Check if files exist

Optional: path (default: '.'), workspace_dir, recursive, max_depth, include_hidden, pattern

Supports glob patterns like '*.py', 'test_*.txt' for filtering.""",
    response_model=FsListResponse,
    tags=["filesystem"],
)
async def fs_list_root(request: FsListRequest) -> FsListResponse:
    """List directory contents (root app endpoint)."""
    return await execute_tool(
        "fs",
        "list",
        request.model_dump(),
        lambda: fs_tools.list(request),
    )


@fs_app.post(
    "/list",
    operation_id="fs_list",
    summary="List Directory",
    description="""List contents of a directory.

The path is relative to the workspace directory unless an absolute 
path within the workspace is provided.

Use this tool when you need to:
- Browse directory contents
- Find files in a directory
- Explore project structure
- Check if files exist

Optional: path (default: '.'), workspace_dir, recursive, max_depth, include_hidden, pattern

Supports glob patterns like '*.py', 'test_*.txt' for filtering.""",
    response_model=FsListResponse,
    tags=["filesystem"],
)
async def fs_list_sub(request: FsListRequest) -> FsListResponse:
    """List directory contents (sub-app endpoint)."""
    return await execute_tool(
        "fs",
        "list",
        request.model_dump(),
        lambda: fs_tools.list(request),
    )


# fs_search endpoints
@app.post(
    "/api/tools/fs/search",
    operation_id="fs_search",
    summary="Search Files",
    description="""Search for files by name or content.

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

Supports both simple text search and regex patterns.""",
    response_model=FsSearchResponse,
    tags=["filesystem"],
)
async def fs_search_root(request: FsSearchRequest) -> FsSearchResponse:
    """Search files (root app endpoint)."""
    return await execute_tool(
        "fs",
        "search",
        request.model_dump(),
        lambda: fs_tools.search(request),
    )


@fs_app.post(
    "/search",
    operation_id="fs_search",
    summary="Search Files",
    description="""Search for files by name or content.

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

Supports both simple text search and regex patterns.""",
    response_model=FsSearchResponse,
    tags=["filesystem"],
)
async def fs_search_sub(request: FsSearchRequest) -> FsSearchResponse:
    """Search files (sub-app endpoint)."""
    return await execute_tool(
        "fs",
        "search",
        request.model_dump(),
        lambda: fs_tools.search(request),
    )


# shell_execute endpoints
@app.post(
    "/api/tools/shell/execute",
    operation_id="shell_execute",
    summary="Execute Shell Command",
    description="""Execute a shell command in the workspace.

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

Allowlisted commands: ls, cat, echo, pwd, git, python, node, npm, docker, curl, and more.""",
    response_model=ShellExecuteResponse,
    tags=["shell"],
)
async def shell_execute_root(request: ShellExecuteRequest) -> ShellExecuteResponse:
    """Execute shell command (root app endpoint)."""
    # Check command safety for policy
    is_safe, reason = shell_tools._check_command_safety(request.command)

    # Evaluate policy with safety check
    decision, policy_reason = policy_engine.evaluate_shell_command(
        request.command,
        is_safe,
        reason,
    )

    # Handle policy decision
    if decision == "block":
        raise SecurityError(policy_reason or "Command execution blocked by policy")

    # Resolve {{secret:KEY}} templates in env vars (originals preserved for audit)
    resolved = resolve_request_secrets(request)

    # Execute with HITL if needed
    if decision == "hitl":
        return await execute_tool(
            "shell",
            "execute",
            request.model_dump(),
            lambda: shell_tools.execute(resolved),
            force_hitl=True,
            hitl_reason=policy_reason or reason,
        )

    # Execute normally
    return await execute_tool(
        "shell",
        "execute",
        request.model_dump(),
        lambda: shell_tools.execute(resolved),
    )


# Create shell sub-app
shell_app = FastAPI(
    title="AnyIDE — Shell Tools",
    description="Shell command execution for AnyIDE",
    version="0.1.0",
)


@shell_app.post(
    "/execute",
    operation_id="shell_execute",
    summary="Execute Shell Command",
    description="""Execute a shell command in the workspace.

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

Allowlisted commands: ls, cat, echo, pwd, git, python, node, npm, docker, curl, and more.""",
    response_model=ShellExecuteResponse,
    tags=["shell"],
)
async def shell_execute_sub(request: ShellExecuteRequest) -> ShellExecuteResponse:
    """Execute shell command (sub-app endpoint)."""
    # Check command safety for policy
    is_safe, reason = shell_tools._check_command_safety(request.command)

    # Evaluate policy with safety check
    decision, policy_reason = policy_engine.evaluate_shell_command(
        request.command,
        is_safe,
        reason,
    )

    # Handle policy decision
    if decision == "block":
        raise SecurityError(policy_reason or "Command execution blocked by policy")

    # Resolve {{secret:KEY}} templates in env vars (originals preserved for audit)
    resolved = resolve_request_secrets(request)

    # Execute with HITL if needed
    if decision == "hitl":
        return await execute_tool(
            "shell",
            "execute",
            request.model_dump(),
            lambda: shell_tools.execute(resolved),
            force_hitl=True,
            hitl_reason=policy_reason or reason,
        )

    # Execute normally
    return await execute_tool(
        "shell",
        "execute",
        request.model_dump(),
        lambda: shell_tools.execute(resolved),
    )


# Create git sub-app
git_app = FastAPI(
    title="AnyIDE — Git Tools",
    description="Git repository management for AnyIDE",
    version="0.1.0",
)


# Git tool endpoints

@app.post(
    "/api/tools/git/status",
    operation_id="git_status",
    summary="Get Git Repository Status",
    description="""Get the current status of a git repository.

Shows:
- Current branch
- Staged files
- Unstaged changes
- Untracked files
- Commits ahead/behind remote

Use this tool to check the state of a repository before making changes.""",
    response_model=GitStatusResponse,
    tags=["git"],
)
async def git_status_root(request: GitStatusRequest) -> GitStatusResponse:
    """Get git repository status (root endpoint)."""
    return await execute_tool(
        "git",
        "status",
        request.model_dump(),
        lambda: git_tools.status(
            repo_path=request.repo_path,
            workspace_dir=request.workspace_dir,
        ),
    )


@git_app.post(
    "/status",
    operation_id="git_status",
    summary="Get Git Repository Status",
    description="""Get the current status of a git repository.

Shows:
- Current branch
- Staged files
- Unstaged changes
- Untracked files
- Commits ahead/behind remote

Use this tool to check the state of a repository before making changes.""",
    response_model=GitStatusResponse,
    tags=["git"],
)
async def git_status_sub(request: GitStatusRequest) -> GitStatusResponse:
    """Get git repository status (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "status",
        request.model_dump(),
        lambda: git_tools.status(
            repo_path=request.repo_path,
            workspace_dir=request.workspace_dir,
        ),
    )


@app.post(
    "/api/tools/git/log",
    operation_id="git_log",
    summary="View Git Commit History",
    description="""View the commit history of a git repository.

Supports filtering by:
- Author
- Date range (since/until)
- File path
- Maximum number of commits

Use this tool to review recent changes or find specific commits.""",
    response_model=GitLogResponse,
    tags=["git"],
)
async def git_log_root(request: GitLogRequest) -> GitLogResponse:
    """View git commit history (root endpoint)."""
    return await execute_tool(
        "git",
        "log",
        request.model_dump(),
        lambda: git_tools.log(
            repo_path=request.repo_path,
            max_count=request.max_count,
            author=request.author,
            since=request.since,
            until=request.until,
            path=request.path,
            format=request.format,
            workspace_dir=request.workspace_dir,
        ),
    )


@git_app.post(
    "/log",
    operation_id="git_log",
    summary="View Git Commit History",
    description="""View the commit history of a git repository.

Supports filtering by:
- Author
- Date range (since/until)
- File path
- Maximum number of commits

Use this tool to review recent changes or find specific commits.""",
    response_model=GitLogResponse,
    tags=["git"],
)
async def git_log_sub(request: GitLogRequest) -> GitLogResponse:
    """View git commit history (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "log",
        request.model_dump(),
        lambda: git_tools.log(
            repo_path=request.repo_path,
            max_count=request.max_count,
            author=request.author,
            since=request.since,
            until=request.until,
            path=request.path,
            format=request.format,
            workspace_dir=request.workspace_dir,
        ),
    )


@app.post(
    "/api/tools/git/diff",
    operation_id="git_diff",
    summary="View Git File Differences",
    description="""View file differences in a git repository.

Can show:
- Unstaged changes (default)
- Staged changes (--cached)
- Diff against specific commit/branch
- Statistics only (files changed, insertions, deletions)

Use this tool to review changes before committing.""",
    response_model=GitDiffResponse,
    tags=["git"],
)
async def git_diff_root(request: GitDiffRequest) -> GitDiffResponse:
    """View git file differences (root endpoint)."""
    return await execute_tool(
        "git",
        "diff",
        request.model_dump(),
        lambda: git_tools.diff(
            repo_path=request.repo_path,
            ref=request.ref,
            path=request.path,
            staged=request.staged,
            stat_only=request.stat_only,
            workspace_dir=request.workspace_dir,
        ),
    )


@git_app.post(
    "/diff",
    operation_id="git_diff",
    summary="View Git File Differences",
    description="""View file differences in a git repository.

Can show:
- Unstaged changes (default)
- Staged changes (--cached)
- Diff against specific commit/branch
- Statistics only (files changed, insertions, deletions)

Use this tool to review changes before committing.""",
    response_model=GitDiffResponse,
    tags=["git"],
)
async def git_diff_sub(request: GitDiffRequest) -> GitDiffResponse:
    """View git file differences (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "diff",
        request.model_dump(),
        lambda: git_tools.diff(
            repo_path=request.repo_path,
            ref=request.ref,
            path=request.path,
            staged=request.staged,
            stat_only=request.stat_only,
            workspace_dir=request.workspace_dir,
        ),
    )


@app.post(
    "/api/tools/git/commit",
    operation_id="git_commit",
    summary="Create Git Commit",
    description="""Create a git commit with the specified message.

This operation:
- Stages specified files (or all changes if none specified)
- Creates a commit with the provided message
- Returns the commit hash and list of files committed

IMPORTANT: This operation requires approval by default as it modifies repository history.

Use this tool after reviewing changes with git_diff.""",
    response_model=GitCommitResponse,
    tags=["git"],
)
async def git_commit_root(request: GitCommitRequest) -> GitCommitResponse:
    """Create git commit (root endpoint)."""
    return await execute_tool(
        "git",
        "commit",
        request.model_dump(),
        lambda: git_tools.commit(
            message=request.message,
            repo_path=request.repo_path,
            files=request.files,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=True,
        hitl_reason="Git commit requires approval",
    )


@git_app.post(
    "/commit",
    operation_id="git_commit",
    summary="Create Git Commit",
    description="""Create a git commit with the specified message.

This operation:
- Stages specified files (or all changes if none specified)
- Creates a commit with the provided message
- Returns the commit hash and list of files committed

IMPORTANT: This operation requires approval by default as it modifies repository history.

Use this tool after reviewing changes with git_diff.""",
    response_model=GitCommitResponse,
    tags=["git"],
)
async def git_commit_sub(request: GitCommitRequest) -> GitCommitResponse:
    """Create git commit (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "commit",
        request.model_dump(),
        lambda: git_tools.commit(
            message=request.message,
            repo_path=request.repo_path,
            files=request.files,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=True,
        hitl_reason="Git commit requires approval",
    )


@app.post(
    "/api/tools/git/push",
    operation_id="git_push",
    summary="Push to Git Remote",
    description="""Push commits to a remote repository.

This operation:
- Pushes commits to the specified remote and branch
- Can force push if needed (use with caution)
- Returns number of commits pushed

IMPORTANT: This operation requires approval by default as it modifies remote repository.

Use {{secret:KEY}} syntax for git credentials in environment variables.

Example with credentials:
Set GIT_ASKPASS environment variable to use stored credentials.""",
    response_model=GitPushResponse,
    tags=["git"],
)
async def git_push_root(request: GitPushRequest) -> GitPushResponse:
    """Push to git remote (root endpoint)."""
    # Resolve {{secret:KEY}} templates for credentials
    resolved = resolve_request_secrets(request)
    return await execute_tool(
        "git",
        "push",
        request.model_dump(),  # Original params for audit (templates, not resolved)
        lambda: git_tools.push(
            repo_path=resolved.repo_path,
            remote=resolved.remote,
            branch=resolved.branch,
            force=resolved.force,
            workspace_dir=resolved.workspace_dir,
            auth_username=resolved.auth_username,
            auth_password=resolved.auth_password,
            auth_env=resolved.auth_env,
        ),
        force_hitl=True,
        hitl_reason="Git push requires approval",
    )


@git_app.post(
    "/push",
    operation_id="git_push",
    summary="Push to Git Remote",
    description="""Push commits to a remote repository.

This operation:
- Pushes commits to the specified remote and branch
- Can force push if needed (use with caution)
- Returns number of commits pushed

IMPORTANT: This operation requires approval by default as it modifies remote repository.

Use {{secret:KEY}} syntax for git credentials in environment variables.

Example with credentials:
Set GIT_ASKPASS environment variable to use stored credentials.""",
    response_model=GitPushResponse,
    tags=["git"],
)
async def git_push_sub(request: GitPushRequest) -> GitPushResponse:
    """Push to git remote (sub-app endpoint)."""
    # Resolve {{secret:KEY}} templates for credentials
    resolved = resolve_request_secrets(request)
    return await execute_tool(
        "git",
        "push",
        request.model_dump(),  # Original params for audit (templates, not resolved)
        lambda: git_tools.push(
            repo_path=resolved.repo_path,
            remote=resolved.remote,
            branch=resolved.branch,
            force=resolved.force,
            workspace_dir=resolved.workspace_dir,
            auth_username=resolved.auth_username,
            auth_password=resolved.auth_password,
            auth_env=resolved.auth_env,
        ),
        force_hitl=True,
        hitl_reason="Git push requires approval",
    )


@app.post(
    "/api/tools/git/pull",
    operation_id="git_pull",
    summary="Pull from Git Remote",
    description="""Pull commits from a remote repository.

This operation:
- Fetches and merges (or rebases) commits from remote
- Returns list of files changed
- Can use rebase instead of merge

Use {{secret:KEY}} syntax for git credentials in environment variables.""",
    response_model=GitPullResponse,
    tags=["git"],
)
async def git_pull_root(request: GitPullRequest) -> GitPullResponse:
    """Pull from git remote (root endpoint)."""
    # Resolve {{secret:KEY}} templates for credentials
    resolved = resolve_request_secrets(request)
    return await execute_tool(
        "git",
        "pull",
        request.model_dump(),  # Original params for audit (templates, not resolved)
        lambda: git_tools.pull(
            repo_path=resolved.repo_path,
            remote=resolved.remote,
            branch=resolved.branch,
            rebase=resolved.rebase,
            workspace_dir=resolved.workspace_dir,
            auth_username=resolved.auth_username,
            auth_password=resolved.auth_password,
            auth_env=resolved.auth_env,
        ),
        force_hitl=True,
        hitl_reason="Git pull requires approval (can modify local files)",
    )


@git_app.post(
    "/pull",
    operation_id="git_pull",
    summary="Pull from Git Remote",
    description="""Pull commits from a remote repository.

This operation:
- Fetches and merges (or rebases) commits from remote
- Returns list of files changed
- Can use rebase instead of merge

Use {{secret:KEY}} syntax for git credentials in environment variables.""",
    response_model=GitPullResponse,
    tags=["git"],
)
async def git_pull_sub(request: GitPullRequest) -> GitPullResponse:
    """Pull from git remote (sub-app endpoint)."""
    # Resolve {{secret:KEY}} templates for credentials
    resolved = resolve_request_secrets(request)
    return await execute_tool(
        "git",
        "pull",
        request.model_dump(),  # Original params for audit (templates, not resolved)
        lambda: git_tools.pull(
            repo_path=resolved.repo_path,
            remote=resolved.remote,
            branch=resolved.branch,
            rebase=resolved.rebase,
            workspace_dir=resolved.workspace_dir,
            auth_username=resolved.auth_username,
            auth_password=resolved.auth_password,
            auth_env=resolved.auth_env,
        ),
        force_hitl=True,
        hitl_reason="Git pull requires approval (can modify local files)",
    )


@app.post(
    "/api/tools/git/checkout",
    operation_id="git_checkout",
    summary="Git Checkout Branch or Commit",
    description="""Switch to a different branch or commit.

This operation:
- Switches to the specified branch or commit
- Can create a new branch if requested
- Returns previous and current branch

IMPORTANT: This operation requires approval by default as it modifies working tree.

Use this tool to switch between branches or restore files.""",
    response_model=GitCheckoutResponse,
    tags=["git"],
)
async def git_checkout_root(request: GitCheckoutRequest) -> GitCheckoutResponse:
    """Git checkout (root endpoint)."""
    return await execute_tool(
        "git",
        "checkout",
        request.model_dump(),
        lambda: git_tools.checkout(
            target=request.target,
            repo_path=request.repo_path,
            create=request.create,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=True,
        hitl_reason="Git checkout requires approval",
    )


@git_app.post(
    "/checkout",
    operation_id="git_checkout",
    summary="Git Checkout Branch or Commit",
    description="""Switch to a different branch or commit.

This operation:
- Switches to the specified branch or commit
- Can create a new branch if requested
- Returns previous and current branch

IMPORTANT: This operation requires approval by default as it modifies working tree.

Use this tool to switch between branches or restore files.""",
    response_model=GitCheckoutResponse,
    tags=["git"],
)
async def git_checkout_sub(request: GitCheckoutRequest) -> GitCheckoutResponse:
    """Git checkout (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "checkout",
        request.model_dump(),
        lambda: git_tools.checkout(
            target=request.target,
            repo_path=request.repo_path,
            create=request.create,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=True,
        hitl_reason="Git checkout requires approval",
    )


@app.post(
    "/api/tools/git/branch",
    operation_id="git_branch",
    summary="Create or Delete Git Branch",
    description="""Create or delete a git branch.

This operation:
- Creates a new branch from current HEAD
- Or deletes an existing branch
- Can force delete unmerged branches

IMPORTANT: Branch deletion requires approval by default.

Use git_list_branches to see available branches.""",
    response_model=GitBranchResponse,
    tags=["git"],
)
async def git_branch_root(request: GitBranchRequest) -> GitBranchResponse:
    """Create or delete git branch (root endpoint)."""
    force_hitl = request.action == "delete"
    return await execute_tool(
        "git",
        "branch",
        request.model_dump(),
        lambda: git_tools.branch(
            name=request.name,
            repo_path=request.repo_path,
            action=request.action,
            force=request.force,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=force_hitl,
        hitl_reason="Git branch deletion requires approval" if force_hitl else None,
    )


@git_app.post(
    "/branch",
    operation_id="git_branch",
    summary="Create or Delete Git Branch",
    description="""Create or delete a git branch.

This operation:
- Creates a new branch from current HEAD
- Or deletes an existing branch
- Can force delete unmerged branches

IMPORTANT: Branch deletion requires approval by default.

Use git_list_branches to see available branches.""",
    response_model=GitBranchResponse,
    tags=["git"],
)
async def git_branch_sub(request: GitBranchRequest) -> GitBranchResponse:
    """Create or delete git branch (sub-app endpoint)."""
    force_hitl = request.action == "delete"
    return await execute_tool(
        "git",
        "branch",
        request.model_dump(),
        lambda: git_tools.branch(
            name=request.name,
            repo_path=request.repo_path,
            action=request.action,
            force=request.force,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=force_hitl,
        hitl_reason="Git branch deletion requires approval" if force_hitl else None,
    )


@app.post(
    "/api/tools/git/list_branches",
    operation_id="git_list_branches",
    summary="List Git Branches",
    description="""List all branches in a git repository.

Shows:
- Branch names
- Current branch indicator
- Remote branches (if requested)
- Last commit on each branch

Use this tool to see available branches before checkout.""",
    response_model=GitListBranchesResponse,
    tags=["git"],
)
async def git_list_branches_root(request: GitListBranchesRequest) -> GitListBranchesResponse:
    """List git branches (root endpoint)."""
    return await execute_tool(
        "git",
        "list_branches",
        request.model_dump(),
        lambda: git_tools.list_branches(
            repo_path=request.repo_path,
            remote=request.remote,
            workspace_dir=request.workspace_dir,
        ),
    )


@git_app.post(
    "/list_branches",
    operation_id="git_list_branches",
    summary="List Git Branches",
    description="""List all branches in a git repository.

Shows:
- Branch names
- Current branch indicator
- Remote branches (if requested)
- Last commit on each branch

Use this tool to see available branches before checkout.""",
    response_model=GitListBranchesResponse,
    tags=["git"],
)
async def git_list_branches_sub(request: GitListBranchesRequest) -> GitListBranchesResponse:
    """List git branches (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "list_branches",
        request.model_dump(),
        lambda: git_tools.list_branches(
            repo_path=request.repo_path,
            remote=request.remote,
            workspace_dir=request.workspace_dir,
        ),
    )


@app.post(
    "/api/tools/git/stash",
    operation_id="git_stash",
    summary="Git Stash Operations",
    description="""Manage git stash (temporary storage for changes).

Supported actions:
- push: Save current changes to stash
- pop: Apply and remove most recent stash
- list: Show all stashes
- drop: Remove a specific stash

Use this tool to temporarily save work in progress.""",
    response_model=GitStashResponse,
    tags=["git"],
)
async def git_stash_root(request: GitStashRequest) -> GitStashResponse:
    """Git stash operations (root endpoint)."""
    # Destructive stash operations (pop/drop) require HITL
    destructive_actions = {"pop", "drop"}
    force_hitl = request.action in destructive_actions
    hitl_reason = f"Git stash {request.action} requires approval (modifies stash stack)" if force_hitl else None

    return await execute_tool(
        "git",
        "stash",
        request.model_dump(),
        lambda: git_tools.stash(
            repo_path=request.repo_path,
            action=request.action,
            message=request.message,
            index=request.index,
            workspace_dir=request.workspace_dir,
        ),
        force_hitl=force_hitl,
        hitl_reason=hitl_reason,
    )


@git_app.post(
    "/stash",
    operation_id="git_stash",
    summary="Git Stash Operations",
    description="""Manage git stash (temporary storage for changes).

Supported actions:
- push: Save current changes to stash
- pop: Apply and remove most recent stash
- list: Show all stashes
- drop: Remove a specific stash

Use this tool to temporarily save work in progress.""",
    response_model=GitStashResponse,
    tags=["git"],
)
async def git_stash_sub(request: GitStashRequest) -> GitStashResponse:
    """Git stash operations (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "stash",
        request.model_dump(),
        lambda: git_tools.stash(
            repo_path=request.repo_path,
            action=request.action,
            message=request.message,
            index=request.index,
            workspace_dir=request.workspace_dir,
        ),
    )


@app.post(
    "/api/tools/git/show",
    operation_id="git_show",
    summary="Show Git Commit Details",
    description="""Show detailed information about a specific commit.

Returns:
- Commit hash and metadata
- Author and date
- Commit message and body
- Full diff of changes
- List of files changed

Use this tool to inspect a specific commit.""",
    response_model=GitShowResponse,
    tags=["git"],
)
async def git_show_root(request: GitShowRequest) -> GitShowResponse:
    """Show git commit details (root endpoint)."""
    return await execute_tool(
        "git",
        "show",
        request.model_dump(),
        lambda: git_tools.show(
            repo_path=request.repo_path,
            ref=request.ref,
            workspace_dir=request.workspace_dir,
        ),
    )


@git_app.post(
    "/show",
    operation_id="git_show",
    summary="Show Git Commit Details",
    description="""Show detailed information about a specific commit.

Returns:
- Commit hash and metadata
- Author and date
- Commit message and body
- Full diff of changes
- List of files changed

Use this tool to inspect a specific commit.""",
    response_model=GitShowResponse,
    tags=["git"],
)
async def git_show_sub(request: GitShowRequest) -> GitShowResponse:
    """Show git commit details (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "show",
        request.model_dump(),
        lambda: git_tools.show(
            repo_path=request.repo_path,
            ref=request.ref,
            workspace_dir=request.workspace_dir,
        ),
    )


@app.post(
    "/api/tools/git/remote",
    operation_id="git_remote",
    summary="Manage Git Remotes",
    description="""Manage git remote repositories.

Supported actions:
- list: Show all configured remotes
- add: Add a new remote
- remove: Remove an existing remote

Use this tool to configure remote repositories.""",
    response_model=GitRemoteResponse,
    tags=["git"],
)
async def git_remote_root(request: GitRemoteRequest) -> GitRemoteResponse:
    """Manage git remotes (root endpoint)."""
    return await execute_tool(
        "git",
        "remote",
        request.model_dump(),
        lambda: git_tools.remote(
            repo_path=request.repo_path,
            action=request.action,
            name=request.name,
            url=request.url,
            workspace_dir=request.workspace_dir,
        ),
    )


@git_app.post(
    "/remote",
    operation_id="git_remote",
    summary="Manage Git Remotes",
    description="""Manage git remote repositories.

Supported actions:
- list: Show all configured remotes
- add: Add a new remote
- remove: Remove an existing remote

Use this tool to configure remote repositories.""",
    response_model=GitRemoteResponse,
    tags=["git"],
)
async def git_remote_sub(request: GitRemoteRequest) -> GitRemoteResponse:
    """Manage git remotes (sub-app endpoint)."""
    return await execute_tool(
        "git",
        "remote",
        request.model_dump(),
        lambda: git_tools.remote(
            repo_path=request.repo_path,
            action=request.action,
            name=request.name,
            url=request.url,
            workspace_dir=request.workspace_dir,
        ),
    )


# ============================================================================
# Memory Tools
# ============================================================================

_MEMORY_STORE_DESC = """Store a piece of knowledge as a node in the knowledge graph.

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
- note: Free-form note or observation"""

_MEMORY_GET_DESC = """Retrieve a memory node by its ID along with its relationships.

Returns the full node content and metadata, plus connected edges and neighbor summaries.

Required: id
Optional: include_relations (default: true), depth (default: 1 — immediate neighbors only)"""

_MEMORY_SEARCH_DESC = """Search the knowledge graph using full-text search and/or tag filtering.

Three search modes:
- fulltext: FTS5 BM25 full-text search on name, content, and tags (best for keyword queries)
- tags: Filter by exact tag values (best for category lookups)
- hybrid: Full-text + tag filter combined (default, most flexible)

Required: query
Optional: entity_type, tags, max_results (default: 10), search_mode, temporal_filter (ISO date)"""

_MEMORY_UPDATE_DESC = """Update a memory node's content or metadata.

Only provided fields are changed. Metadata is merged (patch semantics — existing keys preserved).
Tags replace the existing tag list entirely when provided.

Required: id
Optional: content, name, tags, metadata"""

_MEMORY_DELETE_DESC = """Delete a memory node and all its edges.

With cascade=false (default), lists nodes that would become orphaned (their only parent was this node)
but does not delete them. With cascade=true, also deletes those orphaned children.

IMPORTANT: This operation requires human approval by default.

Required: id
Optional: cascade (default: false)"""

_MEMORY_LINK_DESC = """Create or update a directed relationship between two nodes.

If an edge with the same source, target, and relation already exists, updates its weight and metadata.

Common relation types: related_to, depends_on, parent_of, contradicts, supersedes, derived_from

Required: source_id, target_id, relation
Optional: weight (default: 1.0), bidirectional (default: false), metadata, valid_from, valid_until"""

_MEMORY_CHILDREN_DESC = """Get the immediate child nodes connected via parent_of edges.

In the graph, "A parent_of B" means A→B where A is the parent.
This tool returns all B where A→B with relation='parent_of'.

Required: id"""

_MEMORY_ANCESTORS_DESC = """Traverse parent_of edges upward to find all ancestor nodes (recursive CTE).

Walks the graph from the given node toward root nodes by following parent_of edges in reverse.
Stops when max_depth is reached or no more ancestors exist.

Required: id
Optional: max_depth (default: 10)"""

_MEMORY_ROOTS_DESC = """Get all root nodes — nodes that have no incoming parent_of edges.

Root nodes are the top-level entries in the hierarchy: nothing is their parent."""

_MEMORY_RELATED_DESC = """Get all nodes connected to the given node by any edge type (or a specific type).

Traverses both outgoing and incoming edges (bidirectional single-hop).

Required: id
Optional: relation (filter to a specific relation type)"""

_MEMORY_SUBTREE_DESC = """Return the full subtree rooted at the given node using a recursive CTE.

Follows parent_of edges downward (from parent to children, then grandchildren, etc.).
The root node itself is NOT included in the results.

Required: id
Optional: max_depth (default: 10)"""

_MEMORY_STATS_DESC = """Return knowledge graph statistics and metrics.

Provides an overview of the entire graph: node/edge counts, type breakdown,
most connected nodes, orphaned nodes, recent activity, and tag frequency."""


@app.post(
    "/api/tools/memory/store",
    operation_id="memory_store",
    summary="Store Knowledge Node",
    description=_MEMORY_STORE_DESC,
    response_model=MemoryStoreResponse,
    tags=["memory"],
)
async def memory_store_root(request: MemoryStoreRequest) -> MemoryStoreResponse:
    """Store a knowledge node (root app endpoint)."""
    return await execute_tool(
        "memory", "store", request.model_dump(),
        lambda: memory_tools.store(request),
    )


@memory_app.post(
    "/store",
    operation_id="memory_store",
    summary="Store Knowledge Node",
    description=_MEMORY_STORE_DESC,
    response_model=MemoryStoreResponse,
    tags=["memory"],
)
async def memory_store_sub(request: MemoryStoreRequest) -> MemoryStoreResponse:
    """Store a knowledge node (sub-app endpoint)."""
    return await execute_tool(
        "memory", "store", request.model_dump(),
        lambda: memory_tools.store(request),
    )


@app.post(
    "/api/tools/memory/get",
    operation_id="memory_get",
    summary="Retrieve Knowledge Node",
    description=_MEMORY_GET_DESC,
    response_model=MemoryGetResponse,
    tags=["memory"],
)
async def memory_get_root(request: MemoryGetRequest) -> MemoryGetResponse:
    """Retrieve a memory node by ID (root app endpoint)."""
    return await execute_tool(
        "memory", "get", request.model_dump(),
        lambda: memory_tools.get(request),
    )


@memory_app.post(
    "/get",
    operation_id="memory_get",
    summary="Retrieve Knowledge Node",
    description=_MEMORY_GET_DESC,
    response_model=MemoryGetResponse,
    tags=["memory"],
)
async def memory_get_sub(request: MemoryGetRequest) -> MemoryGetResponse:
    """Retrieve a memory node by ID (sub-app endpoint)."""
    return await execute_tool(
        "memory", "get", request.model_dump(),
        lambda: memory_tools.get(request),
    )


@app.post(
    "/api/tools/memory/search",
    operation_id="memory_search",
    summary="Search Knowledge Graph",
    description=_MEMORY_SEARCH_DESC,
    response_model=MemorySearchResponse,
    tags=["memory"],
)
async def memory_search_root(request: MemorySearchRequest) -> MemorySearchResponse:
    """Search the knowledge graph (root app endpoint)."""
    return await execute_tool(
        "memory", "search", request.model_dump(),
        lambda: memory_tools.search(request),
    )


@memory_app.post(
    "/search",
    operation_id="memory_search",
    summary="Search Knowledge Graph",
    description=_MEMORY_SEARCH_DESC,
    response_model=MemorySearchResponse,
    tags=["memory"],
)
async def memory_search_sub(request: MemorySearchRequest) -> MemorySearchResponse:
    """Search the knowledge graph (sub-app endpoint)."""
    return await execute_tool(
        "memory", "search", request.model_dump(),
        lambda: memory_tools.search(request),
    )


@app.post(
    "/api/tools/memory/update",
    operation_id="memory_update",
    summary="Update Knowledge Node",
    description=_MEMORY_UPDATE_DESC,
    response_model=MemoryUpdateResponse,
    tags=["memory"],
)
async def memory_update_root(request: MemoryUpdateRequest) -> MemoryUpdateResponse:
    """Update a memory node (root app endpoint)."""
    return await execute_tool(
        "memory", "update", request.model_dump(),
        lambda: memory_tools.update(request),
    )


@memory_app.post(
    "/update",
    operation_id="memory_update",
    summary="Update Knowledge Node",
    description=_MEMORY_UPDATE_DESC,
    response_model=MemoryUpdateResponse,
    tags=["memory"],
)
async def memory_update_sub(request: MemoryUpdateRequest) -> MemoryUpdateResponse:
    """Update a memory node (sub-app endpoint)."""
    return await execute_tool(
        "memory", "update", request.model_dump(),
        lambda: memory_tools.update(request),
    )


@app.post(
    "/api/tools/memory/delete",
    operation_id="memory_delete",
    summary="Delete Knowledge Node",
    description=_MEMORY_DELETE_DESC,
    response_model=MemoryDeleteResponse,
    tags=["memory"],
)
async def memory_delete_root(request: MemoryDeleteRequest) -> MemoryDeleteResponse:
    """Delete a memory node (root app endpoint)."""
    return await execute_tool(
        "memory", "delete", request.model_dump(),
        lambda: memory_tools.delete(request),
        force_hitl=True,
        hitl_reason=f"Deleting memory node '{request.id}' requires approval",
    )


@memory_app.post(
    "/delete",
    operation_id="memory_delete",
    summary="Delete Knowledge Node",
    description=_MEMORY_DELETE_DESC,
    response_model=MemoryDeleteResponse,
    tags=["memory"],
)
async def memory_delete_sub(request: MemoryDeleteRequest) -> MemoryDeleteResponse:
    """Delete a memory node (sub-app endpoint)."""
    return await execute_tool(
        "memory", "delete", request.model_dump(),
        lambda: memory_tools.delete(request),
        force_hitl=True,
        hitl_reason=f"Deleting memory node '{request.id}' requires approval",
    )


@app.post(
    "/api/tools/memory/link",
    operation_id="memory_link",
    summary="Create Knowledge Relationship",
    description=_MEMORY_LINK_DESC,
    response_model=MemoryLinkResponse,
    tags=["memory"],
)
async def memory_link_root(request: MemoryLinkRequest) -> MemoryLinkResponse:
    """Create or update a relationship (root app endpoint)."""
    return await execute_tool(
        "memory", "link", request.model_dump(),
        lambda: memory_tools.link(request),
    )


@memory_app.post(
    "/link",
    operation_id="memory_link",
    summary="Create Knowledge Relationship",
    description=_MEMORY_LINK_DESC,
    response_model=MemoryLinkResponse,
    tags=["memory"],
)
async def memory_link_sub(request: MemoryLinkRequest) -> MemoryLinkResponse:
    """Create or update a relationship (sub-app endpoint)."""
    return await execute_tool(
        "memory", "link", request.model_dump(),
        lambda: memory_tools.link(request),
    )


@app.post(
    "/api/tools/memory/children",
    operation_id="memory_children",
    summary="Get Child Nodes",
    description=_MEMORY_CHILDREN_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_children_root(request: MemoryChildrenRequest) -> MemoryNodesResponse:
    """Get child nodes (root app endpoint)."""
    return await execute_tool(
        "memory", "children", request.model_dump(),
        lambda: memory_tools.children(request),
    )


@memory_app.post(
    "/children",
    operation_id="memory_children",
    summary="Get Child Nodes",
    description=_MEMORY_CHILDREN_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_children_sub(request: MemoryChildrenRequest) -> MemoryNodesResponse:
    """Get child nodes (sub-app endpoint)."""
    return await execute_tool(
        "memory", "children", request.model_dump(),
        lambda: memory_tools.children(request),
    )


@app.post(
    "/api/tools/memory/ancestors",
    operation_id="memory_ancestors",
    summary="Get Ancestor Nodes",
    description=_MEMORY_ANCESTORS_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_ancestors_root(request: MemoryAncestorsRequest) -> MemoryNodesResponse:
    """Traverse ancestors (root app endpoint)."""
    return await execute_tool(
        "memory", "ancestors", request.model_dump(),
        lambda: memory_tools.ancestors(request),
    )


@memory_app.post(
    "/ancestors",
    operation_id="memory_ancestors",
    summary="Get Ancestor Nodes",
    description=_MEMORY_ANCESTORS_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_ancestors_sub(request: MemoryAncestorsRequest) -> MemoryNodesResponse:
    """Traverse ancestors (sub-app endpoint)."""
    return await execute_tool(
        "memory", "ancestors", request.model_dump(),
        lambda: memory_tools.ancestors(request),
    )


@app.post(
    "/api/tools/memory/roots",
    operation_id="memory_roots",
    summary="Get Root Nodes",
    description=_MEMORY_ROOTS_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_roots_root() -> MemoryNodesResponse:
    """Get root nodes (root app endpoint)."""
    return await execute_tool(
        "memory", "roots", {},
        lambda: memory_tools.roots(),
    )


@memory_app.post(
    "/roots",
    operation_id="memory_roots",
    summary="Get Root Nodes",
    description=_MEMORY_ROOTS_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_roots_sub() -> MemoryNodesResponse:
    """Get root nodes (sub-app endpoint)."""
    return await execute_tool(
        "memory", "roots", {},
        lambda: memory_tools.roots(),
    )


@app.post(
    "/api/tools/memory/related",
    operation_id="memory_related",
    summary="Get Related Nodes",
    description=_MEMORY_RELATED_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_related_root(request: MemoryRelatedRequest) -> MemoryNodesResponse:
    """Get related nodes (root app endpoint)."""
    return await execute_tool(
        "memory", "related", request.model_dump(),
        lambda: memory_tools.related(request),
    )


@memory_app.post(
    "/related",
    operation_id="memory_related",
    summary="Get Related Nodes",
    description=_MEMORY_RELATED_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_related_sub(request: MemoryRelatedRequest) -> MemoryNodesResponse:
    """Get related nodes (sub-app endpoint)."""
    return await execute_tool(
        "memory", "related", request.model_dump(),
        lambda: memory_tools.related(request),
    )


@app.post(
    "/api/tools/memory/subtree",
    operation_id="memory_subtree",
    summary="Get Node Subtree",
    description=_MEMORY_SUBTREE_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_subtree_root(request: MemorySubtreeRequest) -> MemoryNodesResponse:
    """Get node subtree (root app endpoint)."""
    return await execute_tool(
        "memory", "subtree", request.model_dump(),
        lambda: memory_tools.subtree(request),
    )


@memory_app.post(
    "/subtree",
    operation_id="memory_subtree",
    summary="Get Node Subtree",
    description=_MEMORY_SUBTREE_DESC,
    response_model=MemoryNodesResponse,
    tags=["memory"],
)
async def memory_subtree_sub(request: MemorySubtreeRequest) -> MemoryNodesResponse:
    """Get node subtree (sub-app endpoint)."""
    return await execute_tool(
        "memory", "subtree", request.model_dump(),
        lambda: memory_tools.subtree(request),
    )


@app.post(
    "/api/tools/memory/stats",
    operation_id="memory_stats",
    summary="Knowledge Graph Statistics",
    description=_MEMORY_STATS_DESC,
    response_model=MemoryStatsResponse,
    tags=["memory"],
)
async def memory_stats_root() -> MemoryStatsResponse:
    """Get knowledge graph stats (root app endpoint)."""
    return await execute_tool(
        "memory", "stats", {},
        lambda: memory_tools.stats(),
    )


@memory_app.post(
    "/stats",
    operation_id="memory_stats",
    summary="Knowledge Graph Statistics",
    description=_MEMORY_STATS_DESC,
    response_model=MemoryStatsResponse,
    tags=["memory"],
)
async def memory_stats_sub() -> MemoryStatsResponse:
    """Get knowledge graph stats (sub-app endpoint)."""
    return await execute_tool(
        "memory", "stats", {},
        lambda: memory_tools.stats(),
    )


# ============================================================================
# Plan Tools
# ============================================================================

_PLAN_CREATE_DESC = """Create a new multi-step plan with a DAG of tasks.

Each task specifies a HostBridge tool to call (tool_category + tool_name + params).
Tasks may depend on other tasks via `depends_on` (list of task IDs).
Task params may contain `{{task:TASK_ID.field}}` references resolved at runtime.

Validates the DAG at creation time using Kahn's algorithm (cycle detection, missing refs).
Returns the execution order grouped by parallel level.
The response includes `plan_id`; pass that value to `plan_execute`, `plan_status`, and `plan_cancel`.

on_failure policies (plan-level default, overridable per-task):
- **stop**: abort all remaining tasks when any task fails (default)
- **skip_dependents**: skip only tasks that depend on the failed task
- **continue**: continue all tasks regardless of failures"""

_PLAN_EXECUTE_DESC = """Execute a plan synchronously, blocking until all tasks complete.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; if multiple plans share that name, execution fails with an ambiguity error.

Tasks at the same dependency level run **concurrently** via asyncio.gather.
Task outputs are stored and can be referenced in downstream params via `{{task:ID.field}}`.
Tasks with `require_hitl: true` block for human approval before executing.

Returns the final plan status and per-task counts."""

_PLAN_STATUS_DESC = """Get current status of a plan and all its tasks.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; ambiguous names return an error.

Shows per-task status (pending|running|completed|failed|skipped),
output, error messages, and timing information."""

_PLAN_LIST_DESC = """List all plans with summary information.

Returns plan ID, name, status, task count, and timestamps for all plans."""

_PLAN_CANCEL_DESC = """Cancel a plan, marking all pending and running tasks as skipped.

A cancelled plan cannot be re-executed — create a new plan to re-run.
Useful for aborting long-running plans.

Input `plan_id` should be the `plan_id` returned by `plan_create`.
For resilience, a unique plan name is also accepted; ambiguous names return an error."""


@app.post(
    "/api/tools/plan/create",
    operation_id="plan_create",
    summary="Create Plan",
    description=_PLAN_CREATE_DESC,
    response_model=PlanCreateResponse,
    tags=["plan"],
)
async def plan_create_root(request: PlanCreateRequest) -> PlanCreateResponse:
    """Create a new plan (root app endpoint)."""
    return await execute_tool(
        "plan", "create", request.model_dump(),
        lambda: plan_tools.create(request),
    )


@plan_app.post(
    "/create",
    operation_id="plan_create",
    summary="Create Plan",
    description=_PLAN_CREATE_DESC,
    response_model=PlanCreateResponse,
    tags=["plan"],
)
async def plan_create_sub(request: PlanCreateRequest) -> PlanCreateResponse:
    """Create a new plan (sub-app endpoint)."""
    return await execute_tool(
        "plan", "create", request.model_dump(),
        lambda: plan_tools.create(request),
    )


@app.post(
    "/api/tools/plan/execute",
    operation_id="plan_execute",
    summary="Execute Plan",
    description=_PLAN_EXECUTE_DESC,
    response_model=PlanExecuteResponse,
    tags=["plan"],
)
async def plan_execute_root(request: PlanExecuteRequest) -> PlanExecuteResponse:
    """Execute a plan synchronously (root app endpoint)."""
    return await execute_tool(
        "plan", "execute", request.model_dump(),
        lambda: plan_tools.execute(request),
    )


@plan_app.post(
    "/execute",
    operation_id="plan_execute",
    summary="Execute Plan",
    description=_PLAN_EXECUTE_DESC,
    response_model=PlanExecuteResponse,
    tags=["plan"],
)
async def plan_execute_sub(request: PlanExecuteRequest) -> PlanExecuteResponse:
    """Execute a plan synchronously (sub-app endpoint)."""
    return await execute_tool(
        "plan", "execute", request.model_dump(),
        lambda: plan_tools.execute(request),
    )


@app.post(
    "/api/tools/plan/status",
    operation_id="plan_status",
    summary="Get Plan Status",
    description=_PLAN_STATUS_DESC,
    response_model=PlanStatusResponse,
    tags=["plan"],
)
async def plan_status_root(request: PlanStatusRequest) -> PlanStatusResponse:
    """Get plan status (root app endpoint)."""
    return await execute_tool(
        "plan", "status", request.model_dump(),
        lambda: plan_tools.status(request),
    )


@plan_app.post(
    "/status",
    operation_id="plan_status",
    summary="Get Plan Status",
    description=_PLAN_STATUS_DESC,
    response_model=PlanStatusResponse,
    tags=["plan"],
)
async def plan_status_sub(request: PlanStatusRequest) -> PlanStatusResponse:
    """Get plan status (sub-app endpoint)."""
    return await execute_tool(
        "plan", "status", request.model_dump(),
        lambda: plan_tools.status(request),
    )


@app.post(
    "/api/tools/plan/list",
    operation_id="plan_list",
    summary="List Plans",
    description=_PLAN_LIST_DESC,
    response_model=PlanListResponse,
    tags=["plan"],
)
async def plan_list_root() -> PlanListResponse:
    """List all plans (root app endpoint)."""
    return await execute_tool(
        "plan", "list", {},
        lambda: plan_tools.list(),
    )


@plan_app.post(
    "/list",
    operation_id="plan_list",
    summary="List Plans",
    description=_PLAN_LIST_DESC,
    response_model=PlanListResponse,
    tags=["plan"],
)
async def plan_list_sub() -> PlanListResponse:
    """List all plans (sub-app endpoint)."""
    return await execute_tool(
        "plan", "list", {},
        lambda: plan_tools.list(),
    )


@app.post(
    "/api/tools/plan/cancel",
    operation_id="plan_cancel",
    summary="Cancel Plan",
    description=_PLAN_CANCEL_DESC,
    response_model=PlanCancelResponse,
    tags=["plan"],
)
async def plan_cancel_root(request: PlanCancelRequest) -> PlanCancelResponse:
    """Cancel a plan (root app endpoint)."""
    return await execute_tool(
        "plan", "cancel", request.model_dump(),
        lambda: plan_tools.cancel(request),
    )


@plan_app.post(
    "/cancel",
    operation_id="plan_cancel",
    summary="Cancel Plan",
    description=_PLAN_CANCEL_DESC,
    response_model=PlanCancelResponse,
    tags=["plan"],
)
async def plan_cancel_sub(request: PlanCancelRequest) -> PlanCancelResponse:
    """Cancel a plan (sub-app endpoint)."""
    return await execute_tool(
        "plan", "cancel", request.model_dump(),
        lambda: plan_tools.cancel(request),
    )


# ============================================================================
# Docker Tools
# ============================================================================

@app.post(
    "/api/tools/docker/list",
    operation_id="docker_list",
    summary="List Docker Containers",
    description="""List Docker containers on the host system.

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
- Filter by status: {"filter_status": "running"}""",
    tags=["docker"],
    response_model=DockerListResponse,
)
async def docker_list_root(request: DockerListRequest) -> DockerListResponse:
    """List Docker containers (root endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="list",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.list_containers(request),
        protocol="openapi",
    )


@docker_app.post(
    "/list",
    operation_id="docker_list_sub",
    summary="List Docker Containers",
    description="""List Docker containers on the host system.

This tool allows you to view all containers (running and stopped) managed by Docker.
You can filter by container name or status.

Use this tool when you need to:
- See what containers are running
- Check container status
- Find a specific container by name
- Monitor container health

The tool returns container ID, name, image, status, ports, and creation time.""",
    response_model=DockerListResponse,
)
async def docker_list_sub(request: DockerListRequest) -> DockerListResponse:
    """List Docker containers (sub-app endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="list",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.list_containers(request),
        protocol="openapi",
    )


@app.post(
    "/api/tools/docker/inspect",
    operation_id="docker_inspect",
    summary="Inspect Docker Container",
    description="""Get detailed information about a specific Docker container.

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

Example: {"container": "nginx"} or {"container": "a1b2c3d4"}""",
    tags=["docker"],
    response_model=DockerInspectResponse,
)
async def docker_inspect_root(request: DockerInspectRequest) -> DockerInspectResponse:
    """Inspect Docker container (root endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="inspect",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.inspect_container(request),
        protocol="openapi",
    )


@docker_app.post(
    "/inspect",
    operation_id="docker_inspect_sub",
    summary="Inspect Docker Container",
    description="""Get detailed information about a specific Docker container.

This tool provides comprehensive details about a container including configuration,
network settings, volume mounts, and container state.""",
    response_model=DockerInspectResponse,
)
async def docker_inspect_sub(request: DockerInspectRequest) -> DockerInspectResponse:
    """Inspect Docker container (sub-app endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="inspect",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.inspect_container(request),
        protocol="openapi",
    )


@app.post(
    "/api/tools/docker/logs",
    operation_id="docker_logs",
    summary="Get Docker Container Logs",
    description="""Retrieve logs from a Docker container.

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

Note: The 'follow' parameter is not recommended for API calls and defaults to false.""",
    tags=["docker"],
    response_model=DockerLogsResponse,
)
async def docker_logs_root(request: DockerLogsRequest) -> DockerLogsResponse:
    """Get Docker container logs (root endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="logs",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.get_logs(request),
        protocol="openapi",
    )


@docker_app.post(
    "/logs",
    operation_id="docker_logs_sub",
    summary="Get Docker Container Logs",
    description="""Retrieve logs from a Docker container.

This tool fetches stdout and stderr output from a container.""",
    response_model=DockerLogsResponse,
)
async def docker_logs_sub(request: DockerLogsRequest) -> DockerLogsResponse:
    """Get Docker container logs (sub-app endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="logs",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.get_logs(request),
        protocol="openapi",
    )


@app.post(
    "/api/tools/docker/action",
    operation_id="docker_action",
    summary="Control Docker Container",
    description="""Perform control actions on a Docker container.

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
- Pause container: {"container": "nginx", "action": "pause"}""",
    tags=["docker"],
    response_model=DockerActionResponse,
)
async def docker_action_root(request: DockerActionRequest) -> DockerActionResponse:
    """Control Docker container (root endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="action",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.container_action(request),
        protocol="openapi",
        force_hitl=True,
        hitl_reason=f"Container action '{request.action}' on '{request.container}' requires approval",
    )


@docker_app.post(
    "/action",
    operation_id="docker_action_sub",
    summary="Control Docker Container",
    description="""Perform control actions on a Docker container.

Available actions: start, stop, restart, pause, unpause.

IMPORTANT: This tool requires human approval (HITL) by default for safety.""",
    response_model=DockerActionResponse,
)
async def docker_action_sub(request: DockerActionRequest) -> DockerActionResponse:
    """Control Docker container (sub-app endpoint)."""
    return await execute_tool(
        tool_category="docker",
        tool_name="action",
        params=request.model_dump(),
        tool_func=lambda: docker_tools.container_action(request),
        protocol="openapi",
        force_hitl=True,
        hitl_reason=f"Container action '{request.action}' on '{request.container}' requires approval",
    )


# ============================================================================
# Mount Sub-apps (must be done before MCP mount)
# ============================================================================

app.mount("/tools/fs", fs_app)
app.mount("/tools/workspace", workspace_app)
app.mount("/tools/shell", shell_app)
app.mount("/tools/git", git_app)
app.mount("/tools/docker", docker_app)
app.mount("/tools/http", http_app)
app.mount("/tools/memory", memory_app)
app.mount("/tools/plan", plan_app)


# ============================================================================
# Initialize and mount MCP server (MUST be done AFTER all endpoints are defined)
# ============================================================================

# Restrict MCP to tool routes only by including only tool tags
# Tool endpoints use tags: filesystem, workspace, shell, git, docker, http, memory, plan
# This explicitly excludes admin/auth/system routes (health, admin SPA, etc.)
mcp = FastApiMCP(
    app,
    include_tags=["filesystem", "workspace", "shell", "git", "docker", "http", "memory", "plan"],
)
mcp.mount_http()
logger.info("mcp_server_mounted", path="/mcp", transport="streamable_http", included_tags=["filesystem", "workspace", "shell", "git", "docker", "http", "memory", "plan"])
