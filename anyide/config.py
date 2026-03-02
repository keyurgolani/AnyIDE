"""Configuration management for AnyIDE."""

import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class ServerConfig(BaseModel):
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])


class WorkspaceConfig(BaseModel):
    """Workspace configuration."""
    base_dir: str = "/workspace"


class SecretsConfig(BaseModel):
    """Secrets configuration."""
    file: str = "/secrets/secrets.env"


class AuthConfig(BaseModel):
    """Authentication configuration."""
    admin_password: str = "admin"
    session_timeout_hours: int = 24


class HITLConfig(BaseModel):
    """HITL configuration."""
    default_ttl_seconds: int = 300
    notification_sound: bool = True
    auto_reject_on_expiry: bool = True


class AuditConfig(BaseModel):
    """Audit configuration."""
    retention_days: int = 30
    log_level: str = "INFO"


class ToolPolicyConfig(BaseModel):
    """Tool policy configuration."""
    policy: str = "allow"  # "allow", "block", or "hitl"
    workspace_override: str = "allow"  # "allow", "block", or "hitl"
    hitl_patterns: List[str] = Field(default_factory=list)
    block_patterns: List[str] = Field(default_factory=list)
    allow_commands: List[str] = Field(default_factory=list)
    block_commands: List[str] = Field(default_factory=list)
    allow_safe_commands: bool = False  # For shell: allow safe commands without HITL


class HttpConfig(BaseModel):
    """HTTP client configuration."""
    allow_domains: List[str] = Field(default_factory=list, description="Allowlist of domains (empty = allow all non-blocked)")
    block_domains: List[str] = Field(default_factory=list, description="Blocklist of domains")
    block_private_ips: bool = Field(True, description="Block requests to private/loopback/link-local IP ranges (SSRF protection)")
    block_metadata_endpoints: bool = Field(True, description="Block cloud metadata endpoints (e.g. 169.254.169.254)")
    max_response_size_kb: int = Field(1024, description="Maximum response body size in KB")
    default_timeout: int = Field(30, description="Default request timeout in seconds")
    max_timeout: int = Field(120, description="Maximum allowed timeout in seconds")


class ModulesConfig(BaseModel):
    """Module enable/disable configuration."""
    enabled: List[str] = Field(default_factory=list)
    disabled: List[str] = Field(default_factory=list)


class LanguageConfig(BaseModel):
    """Language module configuration."""

    linters: Dict[str, str] = Field(
        default_factory=lambda: {
            "python": "ruff",
            "javascript": "biome",
            "typescript": "biome",
            "go": "golangci-lint",
        }
    )
    lsp_servers: Dict[str, str] = Field(
        default_factory=lambda: {
            "python": "pyright",
            "typescript": "typescript-language-server",
            "go": "gopls",
        }
    )


class LLMEndpointConfig(BaseModel):
    """LLM endpoint configuration."""

    id: str = Field(..., description="Unique endpoint identifier")
    provider: Literal[
        "openai",
        "openai_compatible",
        "ollama",
        "anthropic",
        "google",
    ] = Field(..., description="LLM provider type")
    base_url: str = Field(..., description="Provider API base URL")
    api_key_secret: Optional[str] = Field(
        None,
        description="Secret key name containing API key (required except for ollama)",
    )
    default_model: str = Field(..., description="Default model for the endpoint")
    max_tokens: Optional[int] = Field(
        None,
        ge=1,
        description="Default max output tokens",
    )
    temperature: Optional[float] = Field(
        None,
        ge=0,
        le=2,
        description="Default sampling temperature",
    )
    timeout: int = Field(60, gt=0, description="Request timeout in seconds")

    @field_validator("id", "default_model", "base_url")
    @classmethod
    def _must_not_be_blank(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("must not be blank")
        return trimmed

    @field_validator("api_key_secret")
    @classmethod
    def _normalize_api_key_secret(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def _validate_provider_requirements(self) -> "LLMEndpointConfig":
        if self.provider != "ollama" and not self.api_key_secret:
            raise ValueError(
                f"api_key_secret is required for provider '{self.provider}'"
            )
        return self


class LLMConfig(BaseModel):
    """LLM configuration."""

    endpoints: List[LLMEndpointConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_unique_endpoint_ids(self) -> "LLMConfig":
        ids = [endpoint.id for endpoint in self.endpoints]
        duplicates = sorted({endpoint_id for endpoint_id in ids if ids.count(endpoint_id) > 1})
        if duplicates:
            raise ValueError(f"Duplicate llm endpoint id(s): {duplicates}")
        return self


class ToolsConfig(BaseModel):
    """Tools configuration."""
    defaults: ToolPolicyConfig = Field(default_factory=lambda: ToolPolicyConfig(workspace_override="hitl"))
    fs: Dict[str, ToolPolicyConfig] = Field(default_factory=dict)
    workspace: Dict[str, ToolPolicyConfig] = Field(default_factory=dict)
    shell: Dict[str, ToolPolicyConfig] = Field(default_factory=dict)
    http: Dict[str, ToolPolicyConfig] = Field(default_factory=dict)
    language: Dict[str, ToolPolicyConfig] = Field(default_factory=dict)


class Config(BaseModel):
    """Main configuration."""
    server: ServerConfig = Field(default_factory=ServerConfig)
    workspace: WorkspaceConfig = Field(default_factory=WorkspaceConfig)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    hitl: HITLConfig = Field(default_factory=HITLConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    modules: ModulesConfig = Field(default_factory=ModulesConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    language: LanguageConfig = Field(default_factory=LanguageConfig)


def get_admin_password_override() -> tuple[Optional[str], Optional[str]]:
    """Return the first non-empty admin password env override and its source key.

    Precedence:
    1. ANYIDE_ADMIN_PASSWORD
    2. ADMIN_PASSWORD (legacy)
    """
    for env_key in ("ANYIDE_ADMIN_PASSWORD", "ADMIN_PASSWORD"):
        value = os.getenv(env_key)
        if value is None:
            continue
        # Treat empty/whitespace-only values as unset to avoid accidental lockout.
        if value.strip() == "":
            continue
        return value, env_key
    return None, None


def get_admin_password_source(config: Config) -> str:
    """Return effective admin password source label for safe observability."""
    _, source_key = get_admin_password_override()
    if source_key:
        return f"env:{source_key.lower()}"
    # Config includes both file-provided and default model value fallback.
    return "config"


def load_config(config_path: str = "config.yaml") -> Config:
    """Load configuration from YAML file with environment variable substitution."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        config = Config()
    else:
        with open(config_file, "r") as f:
            config_data = yaml.safe_load(f)
        
        # Substitute environment variables
        config_data = _substitute_env_vars(config_data)
        
        config = Config(**config_data)

    # Apply explicit admin password env override precedence.
    env_admin_password, _ = get_admin_password_override()
    if env_admin_password is not None:
        config.auth.admin_password = env_admin_password

    return config


def _substitute_env_vars(data: Any) -> Any:
    """Recursively substitute environment variables in config data."""
    if isinstance(data, dict):
        return {k: _substitute_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_substitute_env_vars(item) for item in data]
    elif isinstance(data, str):
        # Handle ${VAR:-default} syntax
        if data.startswith("${") and data.endswith("}"):
            var_expr = data[2:-1]
            if ":-" in var_expr:
                var_name, default = var_expr.split(":-", 1)
                return os.getenv(var_name, default)
            else:
                return os.getenv(var_expr, data)
        return data
    return data
