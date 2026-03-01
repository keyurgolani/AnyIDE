"""Tests for policy enforcement."""

import pytest
from anyide.config import Config, ToolPolicyConfig
from anyide.core.policy import PolicyEngine


@pytest.fixture
def config():
    """Create a test configuration."""
    config = Config()
    
    # Configure fs_read policy
    config.tools.fs = {
        "read": ToolPolicyConfig(
            policy="allow",
            workspace_override="allow",
        ),
        "write": ToolPolicyConfig(
            policy="allow",
            hitl_patterns=["*.conf", "*.env"],
            block_patterns=["*.exe", "*.bin"],
            workspace_override="hitl",
        ),
    }
    
    return config


@pytest.fixture
def policy_engine(config):
    """Create a policy engine for testing."""
    return PolicyEngine(config)


class TestPolicyEvaluation:
    """Test policy evaluation."""
    
    def test_allow_policy(self, policy_engine):
        """Test tool with allow policy."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "read",
            {"path": "test.txt"},
        )
        assert decision == "allow"
        assert reason is None
    
    def test_block_pattern_match(self, policy_engine):
        """Test blocking based on pattern match."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "write",
            {"path": "malware.exe"},
        )
        assert decision == "block"
        assert "block pattern" in reason.lower()
    
    def test_hitl_pattern_match(self, policy_engine):
        """Test HITL based on pattern match."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "write",
            {"path": "app.conf"},
        )
        assert decision == "hitl"
        assert "hitl pattern" in reason.lower()
    
    def test_workspace_override_allow(self, policy_engine):
        """Test workspace override with allow policy."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "read",
            {"path": "test.txt", "workspace_dir": "/workspace/projects"},
        )
        assert decision == "allow"
    
    def test_workspace_override_hitl(self, policy_engine):
        """Test workspace override with HITL policy."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "write",
            {"path": "test.txt", "workspace_dir": "/workspace/projects"},
        )
        assert decision == "hitl"
        assert "workspace override" in reason.lower()
    
    def test_default_policy_for_unknown_tool(self, policy_engine):
        """Test default policy for unknown tool."""
        decision, reason = policy_engine.evaluate(
            "unknown",
            "tool",
            {},
        )
        # Should use default policy (allow)
        assert decision == "allow"
    
    def test_block_pattern_wildcard(self, policy_engine):
        """Test block pattern with wildcard."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "write",
            {"path": "subdir/file.exe"},
        )
        assert decision == "block"
    
    def test_hitl_pattern_wildcard(self, policy_engine):
        """Test HITL pattern with wildcard."""
        decision, reason = policy_engine.evaluate(
            "fs",
            "write",
            {"path": "config/database.env"},
        )
        assert decision == "hitl"
    
    def test_no_path_parameter(self, policy_engine):
        """Test evaluation with no path parameter."""
        decision, reason = policy_engine.evaluate(
            "workspace",
            "info",
            {},
        )
        # Should not match any patterns, use base policy
        assert decision == "allow"
