"""Secret management for AnyIDE.

Loads secrets from a .env-format file and provides:
- Secret key listing (without values)
- Template resolution: {{secret:KEY}} in any string value
- Secret masking in audit logs and error messages
"""

import copy
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from anyide.logging_config import get_logger

logger = get_logger(__name__)

# Regex to find {{secret:KEY}} templates
_SECRET_TEMPLATE_RE = re.compile(r"\{\{secret:([A-Za-z0-9_]+)\}\}")


class SecretNotFoundError(ValueError):
    """Raised when a referenced secret key does not exist."""
    pass


class SecretManager:
    """Manages secrets loaded from a .env-format file."""

    def __init__(self, secrets_file: str):
        """Initialize secret manager.

        Args:
            secrets_file: Path to the .env-format secrets file
        """
        self.secrets_file = Path(secrets_file)
        self._secrets: Dict[str, str] = {}
        self._load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load secrets from file.  Silent if file does not exist."""
        if not self.secrets_file.exists():
            logger.warning("secrets_file_not_found", path=str(self.secrets_file))
            return

        secrets: Dict[str, str] = {}
        try:
            with open(self.secrets_file, "r") as f:
                for lineno, raw_line in enumerate(f, 1):
                    line = raw_line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        logger.warning(
                            "secrets_malformed_line",
                            path=str(self.secrets_file),
                            line=lineno,
                        )
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    # Strip optional surrounding quotes from value
                    if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                        value = value[1:-1]
                    if key:
                        secrets[key] = value

            self._secrets = secrets
            logger.info("secrets_loaded", count=len(secrets), path=str(self.secrets_file))
        except OSError as exc:
            logger.error("secrets_load_error", path=str(self.secrets_file), error=str(exc))

    def reload(self) -> int:
        """Reload secrets from file.

        Returns:
            Number of secrets loaded
        """
        self._secrets = {}
        self._load()
        return len(self._secrets)

    # ------------------------------------------------------------------
    # Introspection (no values exposed)
    # ------------------------------------------------------------------

    def list_keys(self) -> List[str]:
        """Return sorted list of secret key names (values not included)."""
        return sorted(self._secrets.keys())

    def count(self) -> int:
        """Return number of loaded secrets."""
        return len(self._secrets)

    def get(self, key: str) -> str:
        """Return the raw secret value for a key.

        This is intended for internal execution-time integrations only.
        Callers must never expose returned values in API responses/logs.
        """
        if key not in self._secrets:
            raise SecretNotFoundError(
                f"Secret key '{key}' not found. "
                f"Available keys: {', '.join(self.list_keys()) or '(none)'}"
            )
        return self._secrets[key]

    # ------------------------------------------------------------------
    # Template resolution
    # ------------------------------------------------------------------

    def resolve_value(self, value: str) -> str:
        """Resolve all {{secret:KEY}} templates in a single string.

        Args:
            value: String that may contain template placeholders

        Returns:
            String with all placeholders replaced by their secret values

        Raises:
            SecretNotFoundError: If a referenced key does not exist
        """
        def _replace(match: re.Match) -> str:
            key = match.group(1)
            if key not in self._secrets:
                raise SecretNotFoundError(
                    f"Secret key '{key}' not found. "
                    f"Available keys: {', '.join(self.list_keys()) or '(none)'}"
                )
            return self._secrets[key]

        return _SECRET_TEMPLATE_RE.sub(_replace, value)

    def resolve_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively resolve {{secret:KEY}} templates in a parameter dict.

        Creates a deep copy so the originals are preserved for audit logging.

        Args:
            params: Tool parameter dictionary (may be nested)

        Returns:
            New dict with all secret templates resolved

        Raises:
            SecretNotFoundError: If a referenced key does not exist
        """
        resolved = copy.deepcopy(params)
        return self._resolve_any(resolved)

    def _resolve_any(self, value: Any) -> Any:
        """Recursively resolve templates in any value."""
        if isinstance(value, str):
            return self.resolve_value(value)
        elif isinstance(value, dict):
            return {k: self._resolve_any(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_any(item) for item in value]
        return value

    # ------------------------------------------------------------------
    # Masking (for audit logs / error messages)
    # ------------------------------------------------------------------

    def mask_value(self, text: str) -> str:
        """Replace any literal secret values in *text* with [REDACTED].

        Args:
            text: String that may contain secret values

        Returns:
            String with secret values replaced by [REDACTED]
        """
        result = text
        for secret_value in self._secrets.values():
            if secret_value and secret_value in result:
                result = result.replace(secret_value, "[REDACTED]")
        return result

    def mask_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a deep-copy of params with all secret values replaced by [REDACTED].

        Also strips any already-resolved secret values that may have leaked
        into nested dicts/lists.

        Args:
            params: Parameter dictionary

        Returns:
            Deep-copied dict with secrets masked
        """
        masked = copy.deepcopy(params)
        return self._mask_any(masked)

    def _mask_any(self, value: Any) -> Any:
        """Recursively mask secret values in any value."""
        if isinstance(value, str):
            return self.mask_value(value)
        elif isinstance(value, dict):
            return {k: self._mask_any(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._mask_any(item) for item in value]
        return value

    def has_templates(self, params: Dict[str, Any]) -> bool:
        """Return True if any parameter value contains a {{secret:KEY}} template."""
        return self._has_templates_any(params)

    def _has_templates_any(self, value: Any) -> bool:
        """Recursively check for secret templates."""
        if isinstance(value, str):
            return bool(_SECRET_TEMPLATE_RE.search(value))
        elif isinstance(value, dict):
            return any(self._has_templates_any(v) for v in value.values())
        elif isinstance(value, list):
            return any(self._has_templates_any(item) for item in value)
        return False
