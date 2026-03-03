"""Tests for HITL (Human-in-the-Loop) system."""

import pytest
import asyncio

from anyide.core.database import Database
from anyide.core.hitl import HITLManager


@pytest.fixture
async def db():
    """Create test database."""
    database = Database(":memory:")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
async def hitl_manager(db):
    """Create HITL manager."""
    manager = HITLManager(db, default_ttl=5)
    await manager.start()
    yield manager
    await manager.stop()


@pytest.mark.asyncio
async def test_create_hitl_request(hitl_manager):
    """Test creating a HITL request."""
    request = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test.conf", "content": "test"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    assert request.id is not None
    assert request.tool_name == "fs_write"
    assert request.tool_category == "fs"
    assert request.status == "pending"
    assert request.ttl_seconds == 5


@pytest.mark.asyncio
async def test_approve_hitl_request(hitl_manager):
    """Test approving a HITL request."""
    request = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test.conf", "content": "test"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    # Approve in background
    async def approve_later():
        await asyncio.sleep(0.1)
        await hitl_manager.approve(request.id, reviewer="test_admin", note="Looks good")
    
    asyncio.create_task(approve_later())
    
    # Wait for decision
    decision = await hitl_manager.wait_for_decision(request.id)
    
    assert decision == "approved"
    assert request.status == "approved"
    assert request.reviewed_by == "test_admin"
    assert request.reviewer_note == "Looks good"
    assert request.reviewed_at is not None


@pytest.mark.asyncio
async def test_reject_hitl_request(hitl_manager):
    """Test rejecting a HITL request."""
    request = await hitl_manager.create_request(
        tool_name="shell_execute",
        tool_category="shell",
        request_params={"command": "rm -rf /"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="dangerous command",
    )
    
    # Reject in background
    async def reject_later():
        await asyncio.sleep(0.1)
        await hitl_manager.reject(request.id, reviewer="test_admin", note="Too dangerous")
    
    asyncio.create_task(reject_later())
    
    # Wait for decision
    decision = await hitl_manager.wait_for_decision(request.id)
    
    assert decision == "rejected"
    assert request.status == "rejected"
    assert request.reviewed_by == "test_admin"
    assert request.reviewer_note == "Too dangerous"


@pytest.mark.asyncio
async def test_hitl_request_timeout(hitl_manager):
    """Test HITL request timeout."""
    request = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test.conf", "content": "test"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
        ttl_seconds=1,
    )
    
    # Wait for decision (should timeout)
    decision = await hitl_manager.wait_for_decision(request.id)
    
    assert decision == "expired"
    assert request.status == "expired"


@pytest.mark.asyncio
async def test_multiple_concurrent_hitl_requests(hitl_manager):
    """Test multiple concurrent HITL requests."""
    # Create multiple requests
    request1 = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test1.conf", "content": "test1"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    request2 = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test2.conf", "content": "test2"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    # Approve/reject in background
    async def handle_requests():
        await asyncio.sleep(0.1)
        await hitl_manager.approve(request1.id)
        await asyncio.sleep(0.1)
        await hitl_manager.reject(request2.id)
    
    asyncio.create_task(handle_requests())
    
    # Wait for both decisions concurrently
    decision1, decision2 = await asyncio.gather(
        hitl_manager.wait_for_decision(request1.id),
        hitl_manager.wait_for_decision(request2.id),
    )
    
    assert decision1 == "approved"
    assert decision2 == "rejected"
    assert request1.status == "approved"
    assert request2.status == "rejected"


@pytest.mark.asyncio
async def test_get_pending_requests(hitl_manager):
    """Test getting pending HITL requests."""
    # Create some requests
    await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test1.conf", "content": "test1"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    request2 = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test2.conf", "content": "test2"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    # Approve one
    await hitl_manager.approve(request2.id)
    
    # Get pending requests
    pending = hitl_manager.get_pending_requests()
    
    assert len(pending) == 1
    assert pending[0].request_params["path"] == "test1.conf"


@pytest.mark.asyncio
async def test_hitl_request_not_found(hitl_manager):
    """Test error when HITL request not found."""
    with pytest.raises(ValueError, match="not found"):
        await hitl_manager.wait_for_decision("nonexistent-id")


@pytest.mark.asyncio
async def test_approve_non_pending_request(hitl_manager):
    """Test error when approving non-pending request."""
    request = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test.conf", "content": "test"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    # Approve once
    await hitl_manager.approve(request.id)
    
    # Try to approve again
    with pytest.raises(ValueError, match="not pending"):
        await hitl_manager.approve(request.id)


@pytest.mark.asyncio
async def test_hitl_cleanup_task(hitl_manager):
    """Test HITL cleanup background task."""
    # Create a request with short TTL
    request = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test.conf", "content": "test"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
        ttl_seconds=1,
    )
    
    # Wait for cleanup task to run
    await asyncio.sleep(2)
    
    # Request should still be in memory but marked as expired
    stored_request = hitl_manager.get_request(request.id)
    assert stored_request is not None
    # Note: The cleanup task marks as expired but doesn't immediately remove from memory


@pytest.mark.asyncio
async def test_hitl_to_dict(hitl_manager):
    """Test converting HITL request to dictionary."""
    request = await hitl_manager.create_request(
        tool_name="fs_write",
        tool_category="fs",
        request_params={"path": "test.conf", "content": "test"},
        request_context={"protocol": "openapi"},
        policy_rule_matched="config file pattern",
    )
    
    data = request.to_dict()
    
    assert data["id"] == request.id
    assert data["tool_name"] == "fs_write"
    assert data["tool_category"] == "fs"
    assert data["status"] == "pending"
    assert "created_at" in data
    assert "_event" not in data  # Internal field should not be in dict
