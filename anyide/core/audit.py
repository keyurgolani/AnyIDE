"""Audit logging for tool executions."""

import json
import uuid
from typing import Any, Dict, Optional

from anyide.core.database import Database
from anyide.logging_config import get_logger

logger = get_logger(__name__)


class AuditLogger:
    """Audit logger for tool executions."""
    
    def __init__(self, db: Database):
        """Initialize audit logger.
        
        Args:
            db: Database instance
        """
        self.db = db
    
    async def log_execution(
        self,
        tool_name: str,
        tool_category: str,
        protocol: str,
        request_params: Dict[str, Any],
        response_body: Optional[Dict[str, Any]] = None,
        status: str = "success",
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        hitl_request_id: Optional[str] = None,
        container_logs: Optional[str] = None,
        workspace_dir: Optional[str] = None,
        client_info: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Log a tool execution.
        
        Args:
            tool_name: Name of the tool
            tool_category: Category of the tool
            protocol: Protocol used (openapi or mcp)
            request_params: Request parameters
            response_body: Response body
            status: Execution status
            duration_ms: Execution duration in milliseconds
            error_message: Error message if failed
            hitl_request_id: HITL request ID if applicable
            container_logs: Container logs
            workspace_dir: Workspace directory used
            client_info: Client information
            
        Returns:
            Audit record ID
        """
        record_id = str(uuid.uuid4())
        
        await self.db.connection.execute(
            """
            INSERT INTO audit_log (
                id, tool_name, tool_category, protocol,
                request_params, response_body, status, duration_ms,
                error_message, hitl_request_id, container_logs,
                workspace_dir, client_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                tool_name,
                tool_category,
                protocol,
                json.dumps(request_params),
                json.dumps(response_body) if response_body else None,
                status,
                duration_ms,
                error_message,
                hitl_request_id,
                container_logs,
                workspace_dir,
                json.dumps(client_info) if client_info else None,
            ),
        )
        
        await self.db.connection.commit()
        
        logger.info(
            "audit_logged",
            record_id=record_id,
            tool=f"{tool_category}_{tool_name}",
            status=status,
        )
        
        return record_id
    
    async def get_recent_logs(self, limit: int = 100) -> list:
        """Get recent audit logs.
        
        Args:
            limit: Maximum number of logs to return
            
        Returns:
            List of audit log records
        """
        cursor = await self.db.connection.execute(
            """
            SELECT * FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
        
        rows = await cursor.fetchall()
        
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "tool_name": row["tool_name"],
                "tool_category": row["tool_category"],
                "protocol": row["protocol"],
                "status": row["status"],
                "duration_ms": row["duration_ms"],
                "error_message": row["error_message"],
            }
            for row in rows
        ]
