"""Main FastAPI application."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel

from anyide.core.audit import AuditLogger
from anyide.config import get_admin_password_source, load_config
from anyide.core.database import Database
from anyide.core.hitl import HITLManager
from anyide.core.llm_client import LLMClient
from anyide.logging_config import get_logger, setup_logging
from anyide.modules import ModuleContext, ModuleRegistry, ModuleResolutionError
from anyide.core.policy import PolicyEngine
from anyide.core.secrets import SecretManager, SecretNotFoundError
from anyide.modules.http.tools import DomainBlockedError, SSRFError
from anyide.modules.memory.tools import NodeNotFoundError
from anyide.modules.plan.tools import PlanNotFoundError, PlanValidationError
from anyide.core.workspace import SecurityError, WorkspaceManager
from anyide.models import ErrorResponse


# Global state/configuration
config = load_config()
setup_logging(config.audit.log_level)
logger = get_logger(__name__)

# Core components
db = Database(db_path=os.getenv("DB_PATH", "/data/hostbridge.db"))
workspace_manager = WorkspaceManager(config.workspace.base_dir)
audit_logger = AuditLogger(db)
policy_engine = PolicyEngine(config)
hitl_manager = HITLManager(db, config.hitl.default_ttl_seconds)
secret_manager = SecretManager(config.secrets.file)
llm_client = LLMClient(config.llm, secret_manager)

# Compatibility globals expected by admin API and tests.
fs_tools = None
workspace_tools = None
shell_tools = None
git_tools = None
docker_tools = None
http_tools = None
memory_tools = None
plan_tools = None
subagent_tools = None

module_context: ModuleContext | None = None
module_registry: ModuleRegistry | None = None
mcp: FastApiMCP | None = None


async def _tool_dispatch(category: str, name: str, params: dict) -> dict:
    """Dispatch a tool call for plan task execution."""
    if module_context is None:
        raise ValueError("Module context not initialized")

    tool_obj = module_context.tool_dispatch_targets.get(category)
    if tool_obj is None:
        available = sorted(module_context.tool_dispatch_targets.keys())
        raise ValueError(
            f"Unknown tool category '{category}'. Available: {available}"
        )

    method = getattr(tool_obj, name, None)
    if not method or not callable(method):
        raise ValueError(f"Unknown tool '{name}' in category '{category}'")

    sig = inspect.signature(method)
    params_no_self = [p for p in sig.parameters.values() if p.name != "self"]

    if not params_no_self:
        result = await method()
    elif (
        len(params_no_self) == 1
        and params_no_self[0].annotation is not inspect.Parameter.empty
        and isinstance(params_no_self[0].annotation, type)
        and issubclass(params_no_self[0].annotation, BaseModel)
    ):
        request_model = params_no_self[0].annotation
        request = request_model(**params)
        result = await method(request)
    else:
        result = await method(**params)

    if hasattr(result, "model_dump"):
        return result.model_dump()
    return dict(result) if result else {}


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
    """Execute a tool with policy enforcement and audit logging."""
    start_time = time.time()

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
            request_params=params,
            status="blocked",
            error_message=reason,
        )
        raise SecurityError(f"Operation blocked: {reason}")

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

        if decision_result == "expired":
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

    try:
        result = await tool_func()
        duration_ms = int((time.time() - start_time) * 1000)

        await audit_logger.log_execution(
            tool_name=tool_name,
            tool_category=tool_category,
            protocol=protocol,
            request_params=params,
            response_body=result.model_dump() if hasattr(result, "model_dump") else result,
            status="success" if decision != "hitl" else "hitl_approved",
            duration_ms=duration_ms,
            workspace_dir=workspace_manager.base_dir,
            hitl_request_id=hitl_request_id,
        )

        return result

    except (SecurityError, SecretNotFoundError, SSRFError, DomainBlockedError):
        raise
    except Exception as exc:
        duration_ms = int((time.time() - start_time) * 1000)
        safe_error = secret_manager.mask_value(str(exc))
        await audit_logger.log_execution(
            tool_name=tool_name,
            tool_category=tool_category,
            protocol=protocol,
            request_params=params,
            status="error",
            duration_ms=duration_ms,
            error_message=safe_error,
            hitl_request_id=hitl_request_id,
        )
        raise


def resolve_request_secrets(request):
    """Resolve {{secret:KEY}} templates in a pydantic request model."""
    if not secret_manager.has_templates(request.model_dump()):
        return request

    try:
        resolved_dict = secret_manager.resolve_params(request.model_dump())
        return type(request)(**resolved_dict)
    except SecretNotFoundError as exc:
        raise ValueError(str(exc)) from exc


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan manager."""
    logger.info("starting_hostbridge", version="0.1.0")
    logger.info("admin_password_source", source=get_admin_password_source(config))
    _app.state.start_time = time.time()

    await db.connect()
    await hitl_manager.start()

    logger.info("hostbridge_started")
    yield

    logger.info("shutting_down_hostbridge")
    await hitl_manager.stop()
    if module_registry is not None:
        await module_registry.shutdown_modules()
    await db.close()
    logger.info("hostbridge_stopped")


# Create FastAPI app
app = FastAPI(
    title="AnyIDE",
    description="Self-hosted tool server exposing host-machine capabilities to LLM clients via MCP and OpenAPI protocols",
    version="0.1.0",
    lifespan=lifespan,
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
    logger.warning("plan_not_found", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content=ErrorResponse(
            error_type="plan_not_found",
            message=str(exc),
            suggestion=(
                "Use the plan_id returned by plan_create, or call plan_list to look up available plan IDs."
            ),
            suggestion_tool="plan_list",
        ).model_dump(),
    )


@app.exception_handler(PlanValidationError)
async def plan_validation_error_handler(request: Request, exc: PlanValidationError):
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
    logger.error("unexpected_error", error=str(exc), path=request.url.path, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_type="internal_error",
            message="An unexpected error occurred. Please check the logs.",
        ).model_dump(),
    )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


# Include admin API
from anyide.admin_api import router as admin_router

app.include_router(admin_router)

# Serve admin dashboard static files with SPA fallback
static_dir = os.path.join(os.path.dirname(__file__), "..", "static", "admin")
if os.path.exists(static_dir):
    app.mount(
        "/admin/assets",
        StaticFiles(directory=os.path.join(static_dir, "assets")),
        name="admin-assets",
    )

    @app.get("/admin/{full_path:path}")
    async def serve_admin(full_path: str):
        """Serve admin dashboard with SPA fallback."""
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(static_dir, "index.html"))

    logger.info("admin_dashboard_mounted", path="/admin")
else:
    logger.warning("admin_dashboard_not_found", path=static_dir)


class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("websocket_connected", total_connections=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("websocket_disconnected", total_connections=len(self.active_connections))

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as exc:  # pragma: no cover - network/transient
                logger.error("websocket_send_error", error=str(exc))
                disconnected.append(connection)

        for connection in disconnected:
            if connection in self.active_connections:
                self.active_connections.remove(connection)


connection_manager = ConnectionManager()


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
        pending = hitl_manager.get_pending_requests()
        await websocket.send_json({
            "type": "pending_requests",
            "data": [req.to_dict() for req in pending],
        })

        while True:
            data = await websocket.receive_json()

            if data.get("type") == "request_pending":
                pending = hitl_manager.get_pending_requests()
                await websocket.send_json({
                    "type": "pending_requests",
                    "data": [req.to_dict() for req in pending],
                })
                continue

            if data.get("type") != "hitl_decision":
                continue

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
            except ValueError as exc:
                await websocket.send_json({
                    "type": "error",
                    "data": {"message": str(exc)},
                })

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as exc:  # pragma: no cover - network/transient
        logger.error("websocket_error", error=str(exc), exc_info=True)
        connection_manager.disconnect(websocket)


@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """WebSocket endpoint for streaming audit log events."""
    await websocket.accept()
    from anyide.admin_api import decrement_ws_connections, increment_ws_connections

    increment_ws_connections()

    try:
        recent_logs = await audit_logger.get_logs(limit=10)
        await websocket.send_json({"type": "initial_logs", "data": recent_logs})

        last_timestamp = None
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "subscribe":
                poll_interval = data.get("poll_interval", 2)

                while True:
                    try:
                        new_logs = await audit_logger.get_logs(limit=50)

                        if new_logs:
                            if last_timestamp:
                                filtered_logs = [
                                    log
                                    for log in new_logs
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

                        await asyncio.sleep(poll_interval)

                    except WebSocketDisconnect:
                        raise
                    except Exception as exc:  # pragma: no cover - network/transient
                        logger.error("log_stream_error", error=str(exc))
                        await websocket.send_json({
                            "type": "error",
                            "data": {"message": str(exc)},
                        })
                        break

            elif data.get("type") == "get_logs":
                limit = data.get("limit", 50)
                category = data.get("category")
                status_filter = data.get("status")

                logs = await audit_logger.get_logs(limit=limit)
                if category:
                    logs = [l for l in logs if l.get("tool_category") == category]
                if status_filter:
                    logs = [l for l in logs if l.get("status") == status_filter]

                await websocket.send_json({"type": "logs", "data": logs})

    except WebSocketDisconnect:
        logger.info("logs_websocket_disconnected")
    except Exception as exc:  # pragma: no cover - network/transient
        logger.error("logs_websocket_error", error=str(exc), exc_info=True)
    finally:
        decrement_ws_connections()


# Load module system and mount module sub-apps.
module_context = ModuleContext(
    config=config,
    db=db,
    workspace_manager=workspace_manager,
    audit_logger=audit_logger,
    policy_engine=policy_engine,
    hitl_manager=hitl_manager,
    secret_manager=secret_manager,
    logger=logger,
    execute_tool=execute_tool,
    resolve_request_secrets=resolve_request_secrets,
    tool_dispatch=_tool_dispatch,
    llm_client=llm_client,
)

module_registry = ModuleRegistry(module_context)
try:
    module_registry.load_modules(app)
except ModuleResolutionError as exc:
    logger.error("module_load_failed", error=str(exc))
    raise


# Export tool instances for compatibility with existing integrations/tests.
def _bind_compat_tool_globals() -> None:
    global fs_tools
    global workspace_tools
    global shell_tools
    global git_tools
    global docker_tools
    global http_tools
    global memory_tools
    global plan_tools
    global subagent_tools

    modules = module_registry.modules if module_registry is not None else {}
    fs_tools = getattr(modules.get("fs"), "fs_tools", None)
    workspace_tools = getattr(modules.get("workspace"), "workspace_tools", None)
    shell_tools = getattr(modules.get("shell"), "shell_tools", None)
    git_tools = getattr(modules.get("git"), "git_tools", None)
    docker_tools = getattr(modules.get("docker"), "docker_tools", None)
    http_tools = getattr(modules.get("http"), "http_tools", None)
    memory_tools = getattr(modules.get("memory"), "memory_tools", None)
    plan_tools = getattr(modules.get("plan"), "plan_tools", None)
    subagent_tools = getattr(modules.get("subagent"), "subagent_tools", None)


_bind_compat_tool_globals()


# Initialize and mount MCP server AFTER all endpoints are registered.
mcp_tags = module_registry.mcp_tags if module_registry is not None else []
mcp = FastApiMCP(app, include_tags=mcp_tags)
mcp.mount_http()
logger.info("mcp_server_mounted", path="/mcp", transport="streamable_http", included_tags=mcp_tags)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "anyide.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=True,
    )
