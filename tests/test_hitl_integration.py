"""Integration tests for HITL + fs_write workflow."""

import pytest
import asyncio
import os
import tempfile
import shutil
from fastapi.testclient import TestClient

# Note: These tests would normally use the actual FastAPI app
# For now, we'll test the components in isolation


@pytest.fixture
def workspace_dir():
    """Create temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.mark.asyncio
async def test_fs_write_config_file_requires_hitl():
    """Test that writing to config files requires HITL approval."""
    from anyide.config import load_config
    from anyide.core.policy import PolicyEngine
    
    config = load_config()
    policy_engine = PolicyEngine(config)
    
    # Test .conf file
    decision, reason = policy_engine.evaluate(
        "fs",
        "write",
        {"path": "test.conf", "content": "test"},
    )
    
    assert decision == "hitl"
    assert "pattern" in reason.lower() or "conf" in reason.lower()


@pytest.mark.asyncio
async def test_fs_write_env_file_requires_hitl():
    """Test that writing to .env files requires HITL approval."""
    from anyide.config import load_config
    from anyide.core.policy import PolicyEngine
    
    config = load_config()
    policy_engine = PolicyEngine(config)
    
    # Test .env file
    decision, reason = policy_engine.evaluate(
        "fs",
        "write",
        {"path": ".env", "content": "SECRET=value"},
    )
    
    assert decision == "hitl"


@pytest.mark.asyncio
async def test_fs_write_yaml_file_requires_hitl():
    """Test that writing to YAML files requires HITL approval."""
    from anyide.config import load_config
    from anyide.core.policy import PolicyEngine
    
    config = load_config()
    policy_engine = PolicyEngine(config)
    
    # Test .yaml file
    decision, reason = policy_engine.evaluate(
        "fs",
        "write",
        {"path": "config.yaml", "content": "key: value"},
    )
    
    assert decision == "hitl"


@pytest.mark.asyncio
async def test_fs_write_regular_file_allowed():
    """Test that writing to regular files is allowed."""
    from anyide.config import load_config
    from anyide.core.policy import PolicyEngine
    
    config = load_config()
    policy_engine = PolicyEngine(config)
    
    # Test regular .txt file
    decision, reason = policy_engine.evaluate(
        "fs",
        "write",
        {"path": "test.txt", "content": "test"},
    )
    
    assert decision == "allow"


@pytest.mark.asyncio
async def test_fs_write_binary_file_blocked():
    """Test that writing to binary files is blocked."""
    from anyide.config import load_config
    from anyide.core.policy import PolicyEngine
    
    config = load_config()
    policy_engine = PolicyEngine(config)
    
    # Test .exe file
    decision, reason = policy_engine.evaluate(
        "fs",
        "write",
        {"path": "malware.exe", "content": "binary"},
    )
    
    assert decision == "block"


@pytest.mark.asyncio
async def test_hitl_workflow_approve(workspace_dir):
    """Test complete HITL workflow with approval."""
    from anyide.core.database import Database
    from anyide.core.hitl import HITLManager
    from anyide.core.workspace import WorkspaceManager
    from anyide.modules.fs.tools import FilesystemTools
    from anyide.models import FsWriteRequest
    
    # Setup
    db = Database(":memory:")
    await db.connect()
    
    hitl_manager = HITLManager(db, default_ttl=10)
    await hitl_manager.start()
    
    workspace_manager = WorkspaceManager(workspace_dir)
    fs_tools = FilesystemTools(workspace_manager)
    
    try:
        # Create HITL request
        hitl_request = await hitl_manager.create_request(
            tool_name="fs_write",
            tool_category="fs",
            request_params={"path": "test.conf", "content": "test config"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )
        
        # Simulate approval in background
        async def approve_later():
            await asyncio.sleep(0.1)
            await hitl_manager.approve(hitl_request.id)
        
        asyncio.create_task(approve_later())
        
        # Wait for approval
        decision = await hitl_manager.wait_for_decision(hitl_request.id)
        
        assert decision == "approved"
        
        # Now execute the tool
        request = FsWriteRequest(
            path="test.conf",
            content="test config",
            mode="create",
        )
        
        response = await fs_tools.write(request)
        
        assert response.created is True
        assert os.path.exists(os.path.join(workspace_dir, "test.conf"))
    
    finally:
        await hitl_manager.stop()
        await db.close()


@pytest.mark.asyncio
async def test_hitl_workflow_reject(workspace_dir):
    """Test complete HITL workflow with rejection."""
    from anyide.core.database import Database
    from anyide.core.hitl import HITLManager
    
    # Setup
    db = Database(":memory:")
    await db.connect()
    
    hitl_manager = HITLManager(db, default_ttl=10)
    await hitl_manager.start()
    
    try:
        # Create HITL request
        hitl_request = await hitl_manager.create_request(
            tool_name="fs_write",
            tool_category="fs",
            request_params={"path": "dangerous.conf", "content": "rm -rf /"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )
        
        # Simulate rejection in background
        async def reject_later():
            await asyncio.sleep(0.1)
            await hitl_manager.reject(hitl_request.id, note="Too dangerous")
        
        asyncio.create_task(reject_later())
        
        # Wait for decision
        decision = await hitl_manager.wait_for_decision(hitl_request.id)
        
        assert decision == "rejected"
        
        # Tool should not be executed after rejection
        # (in real workflow, this would be handled by execute_tool function)
    
    finally:
        await hitl_manager.stop()
        await db.close()


@pytest.mark.asyncio
async def test_hitl_workflow_timeout(workspace_dir):
    """Test HITL workflow with timeout."""
    from anyide.core.database import Database
    from anyide.core.hitl import HITLManager
    
    # Setup
    db = Database(":memory:")
    await db.connect()
    
    hitl_manager = HITLManager(db, default_ttl=1)
    await hitl_manager.start()
    
    try:
        # Create HITL request with short TTL
        hitl_request = await hitl_manager.create_request(
            tool_name="fs_write",
            tool_category="fs",
            request_params={"path": "test.conf", "content": "test"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
            ttl_seconds=1,
        )
        
        # Wait for timeout (don't approve or reject)
        decision = await hitl_manager.wait_for_decision(hitl_request.id)
        
        assert decision == "expired"
    
    finally:
        await hitl_manager.stop()
        await db.close()


@pytest.mark.asyncio
async def test_multiple_hitl_requests_independent():
    """Test that multiple HITL requests work independently."""
    from anyide.core.database import Database
    from anyide.core.hitl import HITLManager
    
    # Setup
    db = Database(":memory:")
    await db.connect()
    
    hitl_manager = HITLManager(db, default_ttl=10)
    await hitl_manager.start()
    
    try:
        # Create multiple requests
        request1 = await hitl_manager.create_request(
            tool_name="fs_write",
            tool_category="fs",
            request_params={"path": "file1.conf", "content": "content1"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )
        
        request2 = await hitl_manager.create_request(
            tool_name="fs_write",
            tool_category="fs",
            request_params={"path": "file2.conf", "content": "content2"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )
        
        request3 = await hitl_manager.create_request(
            tool_name="fs_write",
            tool_category="fs",
            request_params={"path": "file3.conf", "content": "content3"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )
        
        # Handle requests differently
        async def handle_requests():
            await asyncio.sleep(0.1)
            await hitl_manager.approve(request1.id)
            await asyncio.sleep(0.1)
            await hitl_manager.reject(request2.id)
            # request3 will timeout
        
        asyncio.create_task(handle_requests())
        
        # Wait for all decisions with different timeouts
        decision1_task = asyncio.create_task(hitl_manager.wait_for_decision(request1.id))
        decision2_task = asyncio.create_task(hitl_manager.wait_for_decision(request2.id))
        decision3_task = asyncio.create_task(hitl_manager.wait_for_decision(request3.id, timeout=1))
        
        decision1, decision2, decision3 = await asyncio.gather(
            decision1_task,
            decision2_task,
            decision3_task,
        )
        
        assert decision1 == "approved"
        assert decision2 == "rejected"
        assert decision3 == "expired"
    
    finally:
        await hitl_manager.stop()
        await db.close()
