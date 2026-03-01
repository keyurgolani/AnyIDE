"""Tests for HITL WebSocket roundtrip and client-disconnect resilience.

These tests verify:
1. HITL approve/reject decisions work via WebSocket
2. Client disconnect handling is robust
3. Pending requests are properly cleaned up

Note: WebSocket tests use starlette.testclient.TestClient for WebSocket support.
"""

import os
import sys
import tempfile
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.testclient import TestClient

# Set up test environment BEFORE any imports
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()


@pytest.fixture
async def test_app():
    """Create test app with proper database setup."""
    os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
    os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")

    import src.config
    original_load = src.config.load_config

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg

    src.config.load_config = patched_load

    from src.main import app, db
    from src.hitl import HITLManager
    from src import main as main_module

    # Connect database
    await db.connect()

    # Reinitialize hitl_manager with the connected database
    main_module.hitl_manager = HITLManager(db, main_module.config.hitl.default_ttl_seconds)
    await main_module.hitl_manager.start()

    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)

    yield app

    await main_module.hitl_manager.stop()
    await db.close()
    src.config.load_config = original_load


class TestHITLWebSocketRoundtrip:
    """Tests for HITL approve/reject via WebSocket."""

    @pytest.mark.asyncio
    async def test_websocket_hitl_approve_roundtrip(self, test_app):
        """Test approving a HITL request via WebSocket."""
        from src import main as main_module

        # Create a HITL request
        request = await main_module.hitl_manager.create_request(
            tool_name="write",
            tool_category="fs",
            request_params={"path": "test.conf", "content": "test"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )

        request_id = request.id

        with TestClient(test_app) as client:
            with client.websocket_connect("/ws/hitl") as websocket:
                # Receive initial pending_requests on connect
                initial = websocket.receive_json()
                assert initial["type"] == "pending_requests"

                # Request pending explicitly
                websocket.send_json({"type": "request_pending"})
                response = websocket.receive_json()
                assert response["type"] == "pending_requests"

                # The request should be in the pending list
                pending_ids = [r["id"] for r in response["data"]]
                assert request_id in pending_ids

                # Send approval
                websocket.send_json({
                    "type": "hitl_decision",
                    "data": {
                        "id": request_id,
                        "decision": "approve",
                        "note": "Test approval"
                    }
                })

                # Receive confirmation
                confirmation = websocket.receive_json()
                assert confirmation["type"] == "decision_accepted"
                assert confirmation["data"]["id"] == request_id
                assert confirmation["data"]["decision"] == "approved"

        # Verify the request was approved
        stored_request = main_module.hitl_manager.get_request(request_id)
        assert stored_request is not None
        assert stored_request.status == "approved"

    @pytest.mark.asyncio
    async def test_websocket_hitl_reject_roundtrip(self, test_app):
        """Test rejecting a HITL request via WebSocket."""
        from src import main as main_module

        # Create a HITL request
        request = await main_module.hitl_manager.create_request(
            tool_name="execute",
            tool_category="shell",
            request_params={"command": "rm -rf /"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="dangerous command",
        )

        request_id = request.id

        with TestClient(test_app) as client:
            with client.websocket_connect("/ws/hitl") as websocket:
                # Receive initial pending_requests on connect
                initial = websocket.receive_json()
                assert initial["type"] == "pending_requests"

                # Request pending explicitly
                websocket.send_json({"type": "request_pending"})
                websocket.receive_json()

                # Send rejection
                websocket.send_json({
                    "type": "hitl_decision",
                    "data": {
                        "id": request_id,
                        "decision": "reject",
                        "note": "Too dangerous"
                    }
                })

                # Receive confirmation
                confirmation = websocket.receive_json()
                assert confirmation["type"] == "decision_accepted"
                assert confirmation["data"]["decision"] == "rejected"

        # Verify rejection
        stored_request = main_module.hitl_manager.get_request(request_id)
        assert stored_request is not None
        assert stored_request.status == "rejected"


class TestHITLClientDisconnectResilience:
    """Tests for client-disconnect resilience."""

    @pytest.mark.asyncio
    async def test_pending_request_survives_disconnect(self, test_app):
        """Test that pending HITL requests survive WebSocket disconnect."""
        from src import main as main_module

        # Create a HITL request
        request = await main_module.hitl_manager.create_request(
            tool_name="write",
            tool_category="fs",
            request_params={"path": "test.conf", "content": "test"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )

        request_id = request.id

        # Connect and immediately disconnect
        with TestClient(test_app) as client:
            with client.websocket_connect("/ws/hitl") as websocket:
                # Receive initial pending_requests on connect
                websocket.receive_json()
                websocket.send_json({"type": "request_pending"})
                websocket.receive_json()
                # Disconnect here

        # Verify request is still pending
        stored_request = main_module.hitl_manager.get_request(request_id)
        assert stored_request is not None
        assert stored_request.status == "pending"

        # Should still be able to approve via new connection
        with TestClient(test_app) as client:
            with client.websocket_connect("/ws/hitl") as websocket:
                # Receive initial pending_requests on connect
                websocket.receive_json()
                websocket.send_json({"type": "request_pending"})
                websocket.receive_json()

                websocket.send_json({
                    "type": "hitl_decision",
                    "data": {
                        "id": request_id,
                        "decision": "approve",
                        "note": "Late approval"
                    }
                })

                confirmation = websocket.receive_json()
                assert confirmation["type"] == "decision_accepted"

    @pytest.mark.asyncio
    async def test_invalid_decision_format_handled(self, test_app):
        """Test that invalid decision formats are handled gracefully."""
        from src import main as main_module

        request = await main_module.hitl_manager.create_request(
            tool_name="write",
            tool_category="fs",
            request_params={"path": "test.conf", "content": "test"},
            request_context={"protocol": "openapi"},
            policy_rule_matched="config file pattern",
        )

        with TestClient(test_app) as client:
            with client.websocket_connect("/ws/hitl") as websocket:
                # Receive initial pending_requests on connect
                websocket.receive_json()
                websocket.send_json({"type": "request_pending"})
                websocket.receive_json()

                # Send invalid decision
                websocket.send_json({
                    "type": "hitl_decision",
                    "data": {
                        "id": request.id,
                        "decision": "invalid_decision",
                    }
                })

                # Should receive error
                response = websocket.receive_json()
                assert response["type"] == "error"

        # Request should still be pending
        stored_request = main_module.hitl_manager.get_request(request.id)
        assert stored_request.status == "pending"


class TestHITLConnectionTracking:
    """Tests for WebSocket connection tracking."""

    def test_increment_ws_connections(self):
        """Test incrementing WebSocket connection count."""
        from src.admin_api import increment_ws_connections, websocket_connections

        initial = websocket_connections
        increment_ws_connections()

        from src.admin_api import websocket_connections as new_count
        assert new_count == initial + 1

    def test_decrement_ws_connections(self):
        """Test decrementing WebSocket connection count."""
        from src.admin_api import decrement_ws_connections, websocket_connections

        initial = websocket_connections
        decrement_ws_connections()

        from src.admin_api import websocket_connections as new_count
        assert new_count == max(0, initial - 1)

    def test_decrement_does_not_go_negative(self):
        """Test that decrement doesn't go below zero."""
        from src.admin_api import decrement_ws_connections, websocket_connections

        # Decrement many times
        for _ in range(10):
            decrement_ws_connections()

        from src.admin_api import websocket_connections as new_count
        assert new_count >= 0
