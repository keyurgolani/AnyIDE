"""Policy enforcement for tool executions."""

import fnmatch
from typing import Any, Dict, Literal, Optional

from anyide.config import Config, ToolPolicyConfig
from anyide.logging_config import get_logger

logger = get_logger(__name__)

PolicyDecision = Literal["allow", "block", "hitl"]


class PolicyEngine:
    """Policy engine for tool execution control."""
    
    def __init__(self, config: Config):
        """Initialize policy engine.
        
        Args:
            config: Application configuration
        """
        self.config = config
    
    def evaluate(
        self,
        tool_category: str,
        tool_name: str,
        params: Dict[str, Any],
    ) -> tuple[PolicyDecision, Optional[str]]:
        """Evaluate policy for a tool execution.
        
        Args:
            tool_category: Tool category (e.g., "fs", "git")
            tool_name: Tool name (e.g., "read", "write")
            params: Tool parameters
            
        Returns:
            Tuple of (decision, reason)
            - decision: "allow", "block", or "hitl"
            - reason: Human-readable reason for the decision
        """
        # Get tool policy
        policy = self._get_tool_policy(tool_category, tool_name)
        
        # Check block patterns first
        if self._matches_block_patterns(policy, params):
            reason = "Matches block pattern"
            logger.info(
                "policy_blocked",
                tool=f"{tool_category}_{tool_name}",
                reason=reason,
            )
            return "block", reason
        
        # Check HITL patterns
        if self._matches_hitl_patterns(policy, params):
            reason = "Matches HITL pattern"
            logger.info(
                "policy_hitl",
                tool=f"{tool_category}_{tool_name}",
                reason=reason,
            )
            return "hitl", reason
        
        # Check workspace override
        if "workspace_dir" in params and params["workspace_dir"]:
            override_policy = policy.workspace_override
            if override_policy == "block":
                reason = "Workspace override not allowed"
                logger.info(
                    "policy_blocked",
                    tool=f"{tool_category}_{tool_name}",
                    reason=reason,
                )
                return "block", reason
            elif override_policy == "hitl":
                reason = "Workspace override requires approval"
                logger.info(
                    "policy_hitl",
                    tool=f"{tool_category}_{tool_name}",
                    reason=reason,
                )
                return "hitl", reason
        
        # Check base policy
        if policy.policy == "block":
            reason = "Tool is blocked by policy"
            logger.info(
                "policy_blocked",
                tool=f"{tool_category}_{tool_name}",
                reason=reason,
            )
            return "block", reason
        elif policy.policy == "hitl":
            reason = "Tool requires approval by policy"
            logger.info(
                "policy_hitl",
                tool=f"{tool_category}_{tool_name}",
                reason=reason,
            )
            return "hitl", reason
        
        # Default: allow
        logger.debug(
            "policy_allowed",
            tool=f"{tool_category}_{tool_name}",
        )
        return "allow", None
    
    def _get_tool_policy(self, category: str, tool: str) -> ToolPolicyConfig:
        """Get policy for a specific tool.
        
        Args:
            category: Tool category
            tool: Tool name
            
        Returns:
            Tool policy configuration
        """
        # Get category config
        category_config = getattr(self.config.tools, category, {})
        
        if isinstance(category_config, dict) and tool in category_config:
            return category_config[tool]
        
        # Return default policy
        return self.config.tools.defaults
    
    def _matches_block_patterns(
        self,
        policy: ToolPolicyConfig,
        params: Dict[str, Any],
    ) -> bool:
        """Check if parameters match any block patterns.
        
        Args:
            policy: Tool policy
            params: Tool parameters
            
        Returns:
            True if matches block pattern
        """
        if not policy.block_patterns:
            return False
        
        # Check path parameter against patterns
        path = params.get("path", "")
        if path:
            for pattern in policy.block_patterns:
                if fnmatch.fnmatch(path, pattern):
                    logger.debug(
                        "block_pattern_matched",
                        path=path,
                        pattern=pattern,
                    )
                    return True
        
        return False
    
    def _matches_hitl_patterns(
        self,
        policy: ToolPolicyConfig,
        params: Dict[str, Any],
    ) -> bool:
        """Check if parameters match any HITL patterns.
        
        Args:
            policy: Tool policy
            params: Tool parameters
            
        Returns:
            True if matches HITL pattern
        """
        if not policy.hitl_patterns:
            return False
        
        # Check path parameter against patterns
        path = params.get("path", "")
        if path:
            for pattern in policy.hitl_patterns:
                if fnmatch.fnmatch(path, pattern):
                    logger.debug(
                        "hitl_pattern_matched",
                        path=path,
                        pattern=pattern,
                    )
                    return True
        
        return False

    def evaluate_shell_command(
        self,
        command: str,
        is_safe: bool,
        safety_reason: str,
    ) -> tuple[PolicyDecision, Optional[str]]:
        """Evaluate policy for shell command execution.
        
        Args:
            command: Shell command
            is_safe: Whether command is considered safe
            safety_reason: Reason for safety determination
            
        Returns:
            Tuple of (decision, reason)
        """
        # Get shell execute policy
        policy = self._get_tool_policy("shell", "execute")
        
        # If policy is block, always block
        if policy.policy == "block":
            return "block", "Shell execution is blocked by policy"
        
        # If policy is hitl, always require approval
        if policy.policy == "hitl":
            # Check if safe commands are allowed
            allow_safe = getattr(policy, "allow_safe_commands", False)
            if allow_safe and is_safe:
                return "allow", None
            return "hitl", safety_reason if not is_safe else "Shell command requires approval"
        
        # Policy is allow
        return "allow", None
