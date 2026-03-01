"""Human-in-the-Loop (HITL) system for tool approval."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Literal
from dataclasses import dataclass, field

from anyide.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class HITLRequest:
    """HITL request object."""
    id: str
    created_at: datetime
    tool_name: str
    tool_category: str
    request_params: dict
    request_context: dict
    policy_rule_matched: str
    status: Literal["pending", "approved", "rejected", "expired"]
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_note: Optional[str] = None
    execution_result: Optional[dict] = None
    ttl_seconds: int = 300
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    
    def to_dict(self) -> dict:
        """Convert to dictionary (excluding internal event)."""
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "tool_name": self.tool_name,
            "tool_category": self.tool_category,
            "request_params": self.request_params,
            "request_context": self.request_context,
            "policy_rule_matched": self.policy_rule_matched,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer_note": self.reviewer_note,
            "execution_result": self.execution_result,
            "ttl_seconds": self.ttl_seconds,
        }


class HITLManager:
    """Manager for HITL requests."""
    
    def __init__(self, db, default_ttl: int = 300):
        """Initialize HITL manager.
        
        Args:
            db: Database instance
            default_ttl: Default TTL in seconds for HITL requests
        """
        self.db = db
        self.default_ttl = default_ttl
        self._pending_requests: Dict[str, HITLRequest] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._websocket_callbacks = []
        
    async def start(self):
        """Start HITL manager background tasks."""
        await self._init_db_schema()
        self._cleanup_task = asyncio.create_task(self._cleanup_expired())
        logger.info("hitl_manager_started", default_ttl=self.default_ttl)
    
    async def stop(self):
        """Stop HITL manager background tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("hitl_manager_stopped")
    
    async def _init_db_schema(self):
        """Initialize HITL database schema."""
        await self.db.connection.execute("""
            CREATE TABLE IF NOT EXISTS hitl_requests (
                id TEXT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL,
                tool_name TEXT NOT NULL,
                tool_category TEXT NOT NULL,
                request_params TEXT NOT NULL,
                request_context TEXT NOT NULL,
                policy_rule_matched TEXT NOT NULL,
                status TEXT NOT NULL,
                reviewed_by TEXT,
                reviewed_at TIMESTAMP,
                reviewer_note TEXT,
                execution_result TEXT,
                ttl_seconds INTEGER NOT NULL
            )
        """)
        
        await self.db.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_hitl_status 
            ON hitl_requests(status)
        """)
        
        await self.db.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_hitl_created 
            ON hitl_requests(created_at DESC)
        """)
        
        await self.db.connection.commit()
        logger.info("hitl_schema_initialized")
    
    async def create_request(
        self,
        tool_name: str,
        tool_category: str,
        request_params: dict,
        request_context: dict,
        policy_rule_matched: str,
        ttl_seconds: Optional[int] = None,
    ) -> HITLRequest:
        """Create a new HITL request.
        
        Args:
            tool_name: Name of the tool
            tool_category: Category of the tool
            request_params: Tool parameters
            request_context: Request context (protocol, client info, etc.)
            policy_rule_matched: Which policy rule triggered HITL
            ttl_seconds: TTL in seconds (uses default if not specified)
            
        Returns:
            HITLRequest object
        """
        request_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        ttl = ttl_seconds or self.default_ttl
        
        hitl_request = HITLRequest(
            id=request_id,
            created_at=created_at,
            tool_name=tool_name,
            tool_category=tool_category,
            request_params=request_params,
            request_context=request_context,
            policy_rule_matched=policy_rule_matched,
            status="pending",
            ttl_seconds=ttl,
        )
        
        # Store in memory
        self._pending_requests[request_id] = hitl_request
        
        # Persist to database
        import json
        await self.db.connection.execute(
            """
            INSERT INTO hitl_requests 
            (id, created_at, tool_name, tool_category, request_params, 
             request_context, policy_rule_matched, status, ttl_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                created_at,
                tool_name,
                tool_category,
                json.dumps(request_params),
                json.dumps(request_context),
                policy_rule_matched,
                "pending",
                ttl,
            ),
        )
        await self.db.connection.commit()
        
        logger.info(
            "hitl_request_created",
            request_id=request_id,
            tool=f"{tool_category}_{tool_name}",
            ttl=ttl,
        )
        
        # Notify WebSocket clients
        await self._notify_websockets("hitl_request", hitl_request.to_dict())
        
        return hitl_request
    
    async def wait_for_decision(
        self,
        request_id: str,
        timeout: Optional[float] = None,
    ) -> Literal["approved", "rejected", "expired"]:
        """Wait for HITL decision.
        
        Args:
            request_id: HITL request ID
            timeout: Timeout in seconds (uses request TTL if not specified)
            
        Returns:
            Decision: "approved", "rejected", or "expired"
        """
        hitl_request = self._pending_requests.get(request_id)
        if not hitl_request:
            raise ValueError(f"HITL request {request_id} not found")
        
        timeout_seconds = timeout or hitl_request.ttl_seconds
        
        try:
            await asyncio.wait_for(
                hitl_request._event.wait(),
                timeout=timeout_seconds,
            )
            
            # Event was set, check status
            if hitl_request.status == "approved":
                logger.info("hitl_approved", request_id=request_id)
                return "approved"
            elif hitl_request.status == "rejected":
                logger.info("hitl_rejected", request_id=request_id)
                return "rejected"
            else:
                # Shouldn't happen, but handle it
                logger.warning("hitl_unexpected_status", request_id=request_id, status=hitl_request.status)
                return "expired"
        
        except asyncio.TimeoutError:
            # TTL expired
            await self._expire_request(request_id)
            logger.info("hitl_expired", request_id=request_id)
            return "expired"
    
    async def approve(
        self,
        request_id: str,
        reviewer: str = "admin",
        note: Optional[str] = None,
    ):
        """Approve a HITL request.
        
        Args:
            request_id: HITL request ID
            reviewer: Who approved the request
            note: Optional reviewer note
        """
        hitl_request = self._pending_requests.get(request_id)
        if not hitl_request:
            raise ValueError(f"HITL request {request_id} not found")
        
        if hitl_request.status != "pending":
            raise ValueError(f"HITL request {request_id} is not pending (status: {hitl_request.status})")
        
        # Update request
        hitl_request.status = "approved"
        hitl_request.reviewed_by = reviewer
        hitl_request.reviewed_at = datetime.now(timezone.utc)
        hitl_request.reviewer_note = note
        
        # Update database
        await self._update_request_in_db(hitl_request)
        
        # Set event to unblock waiting handler
        hitl_request._event.set()
        
        logger.info("hitl_request_approved", request_id=request_id, reviewer=reviewer)
        
        # Notify WebSocket clients
        await self._notify_websockets("hitl_update", hitl_request.to_dict())
    
    async def reject(
        self,
        request_id: str,
        reviewer: str = "admin",
        note: Optional[str] = None,
    ):
        """Reject a HITL request.
        
        Args:
            request_id: HITL request ID
            reviewer: Who rejected the request
            note: Optional reviewer note
        """
        hitl_request = self._pending_requests.get(request_id)
        if not hitl_request:
            raise ValueError(f"HITL request {request_id} not found")
        
        if hitl_request.status != "pending":
            raise ValueError(f"HITL request {request_id} is not pending (status: {hitl_request.status})")
        
        # Update request
        hitl_request.status = "rejected"
        hitl_request.reviewed_by = reviewer
        hitl_request.reviewed_at = datetime.now(timezone.utc)
        hitl_request.reviewer_note = note
        
        # Update database
        await self._update_request_in_db(hitl_request)
        
        # Set event to unblock waiting handler
        hitl_request._event.set()
        
        logger.info("hitl_request_rejected", request_id=request_id, reviewer=reviewer)
        
        # Notify WebSocket clients
        await self._notify_websockets("hitl_update", hitl_request.to_dict())
    
    async def _expire_request(self, request_id: str):
        """Mark a request as expired.
        
        Args:
            request_id: HITL request ID
        """
        hitl_request = self._pending_requests.get(request_id)
        if not hitl_request:
            return
        
        hitl_request.status = "expired"
        
        # Update database
        await self._update_request_in_db(hitl_request)
        
        # Notify WebSocket clients
        await self._notify_websockets("hitl_update", hitl_request.to_dict())
    
    async def _update_request_in_db(self, hitl_request: HITLRequest):
        """Update HITL request in database.
        
        Args:
            hitl_request: HITL request to update
        """
        import json
        await self.db.connection.execute(
            """
            UPDATE hitl_requests
            SET status = ?, reviewed_by = ?, reviewed_at = ?, 
                reviewer_note = ?, execution_result = ?
            WHERE id = ?
            """,
            (
                hitl_request.status,
                hitl_request.reviewed_by,
                hitl_request.reviewed_at,
                hitl_request.reviewer_note,
                json.dumps(hitl_request.execution_result) if hitl_request.execution_result else None,
                hitl_request.id,
            ),
        )
        await self.db.connection.commit()
    
    async def _cleanup_expired(self):
        """Background task to clean up expired HITL requests."""
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                now = datetime.now(timezone.utc)
                expired_ids = []
                
                for request_id, hitl_request in self._pending_requests.items():
                    if hitl_request.status == "pending":
                        expires_at = hitl_request.created_at + timedelta(seconds=hitl_request.ttl_seconds)
                        if now >= expires_at:
                            expired_ids.append(request_id)
                
                # Clean up expired requests
                for request_id in expired_ids:
                    await self._expire_request(request_id)
                    # Remove from memory after a grace period
                    # (keep for a bit in case someone queries it)
                
                # Remove old completed/expired requests from memory (older than 1 hour)
                cutoff = now - timedelta(hours=1)
                to_remove = [
                    request_id
                    for request_id, req in self._pending_requests.items()
                    if req.status in ("approved", "rejected", "expired") and req.created_at < cutoff
                ]
                for request_id in to_remove:
                    del self._pending_requests[request_id]
                
                if expired_ids or to_remove:
                    logger.info(
                        "hitl_cleanup",
                        expired=len(expired_ids),
                        removed=len(to_remove),
                    )
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("hitl_cleanup_error", error=str(e), exc_info=True)
    
    def get_pending_requests(self) -> list[HITLRequest]:
        """Get all pending HITL requests.
        
        Returns:
            List of pending HITL requests
        """
        return [
            req for req in self._pending_requests.values()
            if req.status == "pending"
        ]
    
    def get_request(self, request_id: str) -> Optional[HITLRequest]:
        """Get a HITL request by ID.
        
        Args:
            request_id: HITL request ID
            
        Returns:
            HITLRequest or None if not found
        """
        return self._pending_requests.get(request_id)
    
    def register_websocket_callback(self, callback):
        """Register a callback for WebSocket notifications.
        
        Args:
            callback: Async function to call with (event_type, data)
        """
        self._websocket_callbacks.append(callback)
    
    async def _notify_websockets(self, event_type: str, data: dict):
        """Notify all registered WebSocket callbacks.
        
        Args:
            event_type: Type of event
            data: Event data
        """
        for callback in self._websocket_callbacks:
            try:
                await callback(event_type, data)
            except Exception as e:
                logger.error("websocket_notification_error", error=str(e), exc_info=True)
