"""Tests for HttpTools — SSRF protection, domain filtering, and requests."""

import os
import tempfile

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from anyide.config import HttpConfig
from anyide.models import HttpRequestRequest
from anyide.modules.http.tools import (
    HttpTools,
    SSRFError,
    DomainBlockedError,
    _check_ssrf,
    _is_private_ip,
)


# ---------------------------------------------------------------------------
# Unit tests: SSRF / IP / domain helpers
# ---------------------------------------------------------------------------

class TestPrivateIpDetection:
    """Tests for _is_private_ip."""

    def test_loopback_ipv4(self):
        assert _is_private_ip("127.0.0.1") is True

    def test_private_class_a(self):
        assert _is_private_ip("10.0.0.1") is True

    def test_private_class_b(self):
        assert _is_private_ip("172.16.5.1") is True

    def test_private_class_c(self):
        assert _is_private_ip("192.168.1.100") is True

    def test_link_local(self):
        assert _is_private_ip("169.254.169.254") is True

    def test_public_ip(self):
        assert _is_private_ip("8.8.8.8") is False

    def test_another_public_ip(self):
        assert _is_private_ip("93.184.216.34") is False

    def test_hostname_is_not_ip(self):
        # Hostnames are not raw IPs — returns False (no DNS lookup)
        assert _is_private_ip("example.com") is False


class TestSsrfCheck:
    """Tests for _check_ssrf."""

    def _cfg(self, **kwargs) -> HttpConfig:
        defaults = dict(
            block_private_ips=True,
            block_metadata_endpoints=True,
            allow_domains=[],
            block_domains=[],
        )
        defaults.update(kwargs)
        return HttpConfig(**defaults)

    def test_public_url_allowed(self):
        _check_ssrf("https://example.com/api", self._cfg())  # should not raise

    def test_private_ip_blocked(self):
        with pytest.raises(SSRFError, match="private"):
            _check_ssrf("http://10.0.0.1/secret", self._cfg())

    def test_loopback_blocked(self):
        with pytest.raises(SSRFError, match="private"):
            _check_ssrf("http://127.0.0.1:8080/", self._cfg())

    def test_metadata_endpoint_blocked(self):
        with pytest.raises(SSRFError, match="metadata"):
            _check_ssrf("http://169.254.169.254/latest/meta-data/", self._cfg())

    def test_metadata_blocked_even_with_private_ips_allowed(self):
        """Metadata endpoint blocked independently of block_private_ips."""
        cfg = self._cfg(block_private_ips=False, block_metadata_endpoints=True)
        with pytest.raises(SSRFError, match="metadata"):
            _check_ssrf("http://169.254.169.254/", cfg)

    def test_private_ip_allowed_when_disabled(self):
        """Private IP check can be disabled (e.g., for internal tooling)."""
        cfg = self._cfg(block_private_ips=False, block_metadata_endpoints=False)
        _check_ssrf("http://192.168.1.1/", cfg)  # should not raise

    def test_unsupported_scheme_blocked(self):
        with pytest.raises(SSRFError, match="scheme"):
            _check_ssrf("ftp://example.com/file", self._cfg())

    def test_domain_allowlist_permits(self):
        cfg = self._cfg(allow_domains=["example.com"])
        _check_ssrf("https://example.com/api", cfg)  # should not raise

    def test_domain_allowlist_wildcard(self):
        cfg = self._cfg(allow_domains=["*.example.com"])
        _check_ssrf("https://api.example.com/v1", cfg)  # should not raise

    def test_domain_allowlist_blocks_unlisted(self):
        cfg = self._cfg(allow_domains=["example.com"])
        with pytest.raises(DomainBlockedError, match="not in the allowlist"):
            _check_ssrf("https://other.com/api", cfg)

    def test_domain_blocklist_blocks(self):
        cfg = self._cfg(block_domains=["evil.com"])
        with pytest.raises(DomainBlockedError, match="blocked by policy"):
            _check_ssrf("https://evil.com/api", cfg)

    def test_domain_blocklist_wildcard(self):
        cfg = self._cfg(block_domains=["*.evil.com"])
        with pytest.raises(DomainBlockedError):
            _check_ssrf("https://sub.evil.com/api", cfg)


# ---------------------------------------------------------------------------
# Integration tests: HttpTools.request (mocked httpx)
# ---------------------------------------------------------------------------

class TestHttpToolsRequest:
    """Tests for HttpTools.request using mocked HTTP client."""

    @pytest.fixture
    def http_tools(self):
        cfg = HttpConfig(
            block_private_ips=True,
            block_metadata_endpoints=True,
            allow_domains=[],
            block_domains=[],
            max_response_size_kb=1024,
            default_timeout=30,
            max_timeout=120,
        )
        return HttpTools(cfg)

    def _mock_response(self, status=200, text="OK", headers=None, url="https://example.com"):
        import httpx
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status
        resp.text = text
        resp.content = text.encode()
        resp.headers = httpx.Headers(headers or {"content-type": "text/plain"})
        resp.url = httpx.URL(url)
        return resp

    @pytest.mark.asyncio
    async def test_basic_get_request(self, http_tools):
        """GET request to a public URL succeeds."""
        mock_resp = self._mock_response(200, "Hello world")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            req = HttpRequestRequest(url="https://example.com", method="GET")
            result = await http_tools.request(req)

        assert result.status_code == 200
        assert result.body == "Hello world"

    @pytest.mark.asyncio
    async def test_post_with_json_body(self, http_tools):
        """POST request with JSON body."""
        mock_resp = self._mock_response(201, '{"id": 1}',
                                        headers={"content-type": "application/json"})

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            req = HttpRequestRequest(
                url="https://api.example.com/items",
                method="POST",
                json_body={"name": "test"},
            )
            result = await http_tools.request(req)

        assert result.status_code == 201
        assert result.content_type == "application/json"

    @pytest.mark.asyncio
    async def test_ssrf_blocked_before_request(self, http_tools):
        """SSRF check fires before any network call."""
        req = HttpRequestRequest(url="http://192.168.1.1/admin", method="GET")

        with patch("httpx.AsyncClient") as mock_client_cls:
            with pytest.raises(SSRFError):
                await http_tools.request(req)

        mock_client_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_method_rejected(self, http_tools):
        """Invalid HTTP method raises ValueError."""
        req = HttpRequestRequest(url="https://example.com", method="INVALID")
        with pytest.raises(ValueError, match="not allowed"):
            await http_tools.request(req)

    @pytest.mark.asyncio
    async def test_both_body_and_json_body_raises(self, http_tools):
        """Providing both body and json_body raises ValueError."""
        req = HttpRequestRequest(
            url="https://example.com",
            method="POST",
            body="raw body",
            json_body={"key": "val"},
        )
        with pytest.raises(ValueError, match="not both"):
            await http_tools.request(req)

    @pytest.mark.asyncio
    async def test_timeout_capped_at_max(self, http_tools):
        """Timeout is capped to max_timeout from config."""
        mock_resp = self._mock_response(200, "OK")

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            req = HttpRequestRequest(
                url="https://example.com",
                method="GET",
                timeout=9999,  # way over max_timeout=120
            )
            await http_tools.request(req)

        # Verify the client was created with timeout=120 (max_timeout)
        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["timeout"] == 120

    @pytest.mark.asyncio
    async def test_response_truncated_at_size_limit(self, http_tools):
        """Large responses are truncated to max_response_size_kb."""
        # Override max to 1 KB for test
        http_tools.http_config.max_response_size_kb = 1
        large_text = "X" * 2000  # 2 KB

        mock_resp = self._mock_response(200, large_text)
        # The content attribute is used for size check
        mock_resp.content = large_text.encode()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.request = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            req = HttpRequestRequest(url="https://example.com", method="GET")
            result = await http_tools.request(req)

        assert "TRUNCATED" in result.body


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------

# Set up temp paths for DB and workspace before importing app
_TEST_DB_DIR = tempfile.mkdtemp()
_TEST_DB_PATH = os.path.join(_TEST_DB_DIR, "test_http.db")
_TEST_WORKSPACE = tempfile.mkdtemp()
_TEST_SECRETS = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
_TEST_SECRETS.write("MY_TOKEN=resolved_value\nAPI_KEY=key123\nDB_PASS=pass456\n")
_TEST_SECRETS.close()

os.environ.setdefault("DB_PATH", _TEST_DB_PATH)


def _get_loaded_modules():
    """Get module instances from the live app bootstrap."""
    import anyide.main as main_module

    http_module = main_module.module_registry.modules.get("http")
    workspace_module = main_module.module_registry.modules.get("workspace")
    assert http_module is not None, "http module must be loaded for HTTP API tests"
    assert workspace_module is not None, "workspace module must be loaded for workspace API tests"
    return main_module, http_module, workspace_module


@pytest.fixture(autouse=True, scope="module")
def setup_app_env():
    """Set environment vars and patch DB/config before any app import in this module."""
    os.environ["DB_PATH"] = _TEST_DB_PATH
    os.environ["WORKSPACE_BASE_DIR"] = _TEST_WORKSPACE


@pytest.fixture
async def app_client():
    """Create an async test client with the app properly initialized."""
    os.environ["DB_PATH"] = _TEST_DB_PATH

    import anyide.config
    original_load = anyide.config.load_config

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = _TEST_WORKSPACE
        cfg.secrets.file = _TEST_SECRETS.name
        return cfg

    anyide.config.load_config = patched_load

    import anyide.core.database
    original_db_init = anyide.core.database.Database.__init__

    def patched_db_init(self, db_path=None):
        original_db_init(self, _TEST_DB_PATH)

    anyide.core.database.Database.__init__ = patched_db_init

    from httpx import AsyncClient, ASGITransport
    from anyide.main import app, db

    await db.connect()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    await db.close()
    anyide.config.load_config = original_load
    anyide.core.database.Database.__init__ = original_db_init


@pytest.mark.asyncio
async def test_http_request_endpoint_get(app_client):
    """Test /api/tools/http/request endpoint with a GET request."""
    from anyide.models import HttpRequestResponse

    main_module, http_module, _ = _get_loaded_modules()

    with patch.object(http_module, "http_tools") as mock_tools:
        original_global = main_module.http_tools
        main_module.http_tools = mock_tools
        mock_tools.request = AsyncMock(return_value=HttpRequestResponse(
            status_code=200,
            headers={"content-type": "text/plain"},
            body="Hello from external API",
            url="https://httpbin.org/get",
            duration_ms=50,
            content_type="text/plain",
        ))

        try:
            response = await app_client.post(
                "/api/tools/http/request",
                json={"url": "https://httpbin.org/get", "method": "GET"},
            )
        finally:
            main_module.http_tools = original_global

    assert response.status_code == 200
    data = response.json()
    assert data["status_code"] == 200
    assert data["body"] == "Hello from external API"


@pytest.mark.asyncio
async def test_workspace_secrets_list_endpoint(app_client):
    """Test /api/tools/workspace/secrets/list endpoint."""
    from pathlib import Path

    main_module, _, workspace_module = _get_loaded_modules()

    with patch("anyide.main.secret_manager") as mock_sm:
        mock_sm.list_keys.return_value = ["API_KEY", "DB_PASS"]
        mock_sm.count.return_value = 2
        mock_sm.has_templates.return_value = False
        mock_sm.secrets_file = Path("/secrets/secrets.env")

        original_global_sm = main_module.secret_manager
        original_ctx_sm = workspace_module.context.secret_manager
        original_ws_sm = workspace_module.workspace_tools.secret_manager
        main_module.secret_manager = mock_sm
        workspace_module.context.secret_manager = mock_sm
        workspace_module.workspace_tools.secret_manager = mock_sm
        try:
            response = await app_client.post("/api/tools/workspace/secrets/list")
        finally:
            main_module.secret_manager = original_global_sm
            workspace_module.context.secret_manager = original_ctx_sm
            workspace_module.workspace_tools.secret_manager = original_ws_sm

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert "API_KEY" in data["keys"]
    assert "DB_PASS" in data["keys"]


@pytest.mark.asyncio
async def test_secret_template_in_http_headers(app_client):
    """Test that {{secret:KEY}} templates in headers are resolved before request."""
    from anyide.models import HttpRequestResponse

    main_module, http_module, _ = _get_loaded_modules()

    with patch("anyide.main.secret_manager") as mock_sm:
        mock_sm.has_templates.return_value = True
        mock_sm.resolve_params.return_value = {
            "url": "https://api.example.com",
            "method": "GET",
            "headers": {"Authorization": "Bearer resolved_value"},
            "body": None,
            "json_body": None,
            "timeout": 30,
            "follow_redirects": True,
        }
        mock_sm.mask_value.side_effect = lambda x: x

        with patch.object(http_module, "http_tools") as mock_tools:
            original_global = main_module.http_tools
            main_module.http_tools = mock_tools
            mock_tools.request = AsyncMock(return_value=HttpRequestResponse(
                status_code=200,
                headers={},
                body="OK",
                url="https://api.example.com",
                duration_ms=10,
            ))

            try:
                response = await app_client.post(
                    "/api/tools/http/request",
                    json={
                        "url": "https://api.example.com",
                        "method": "GET",
                        "headers": {"Authorization": "Bearer {{secret:MY_TOKEN}}"},
                    },
                )
            finally:
                main_module.http_tools = original_global

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_missing_secret_key_returns_error(app_client):
    """Test that referencing a missing secret key returns a 400 error."""
    from anyide.core.secrets import SecretNotFoundError

    with patch("anyide.main.secret_manager") as mock_sm:
        mock_sm.has_templates.return_value = True
        mock_sm.resolve_params.side_effect = SecretNotFoundError(
            "Secret key 'MISSING' not found."
        )
        mock_sm.mask_value.side_effect = lambda x: x

        response = await app_client.post(
            "/api/tools/http/request",
            json={
                "url": "https://api.example.com",
                "method": "GET",
                "headers": {"Authorization": "Bearer {{secret:MISSING}}"},
            },
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"] is True
    assert "MISSING" in data["message"]


@pytest.mark.asyncio
async def test_audit_log_shows_templates_not_resolved_values(app_client):
    """Test that audit log records template strings, not resolved secret values."""
    from anyide.models import HttpRequestResponse
    from anyide.core.secrets import SecretManager
    from anyide.main import audit_logger

    real_sm = SecretManager(_TEST_SECRETS.name)

    # Use a unique URL so we can find exactly this request's audit record
    unique_url = "https://unique-audit-test.example.com/check-templates"

    main_module, http_module, _ = _get_loaded_modules()

    with patch("anyide.main.secret_manager", real_sm):
        with patch.object(http_module, "http_tools") as mock_tools:
            original_global = main_module.http_tools
            main_module.http_tools = mock_tools
            mock_tools.request = AsyncMock(return_value=HttpRequestResponse(
                status_code=200,
                headers={},
                body="OK",
                url=unique_url,
                duration_ms=10,
            ))

            try:
                response = await app_client.post(
                    "/api/tools/http/request",
                    json={
                        "url": unique_url,
                        "method": "GET",
                        "headers": {"Authorization": "Bearer {{secret:MY_TOKEN}}"},
                    },
                )
            finally:
                main_module.http_tools = original_global

    assert response.status_code == 200

    # Verify audit log has template string, not resolved value.
    # Search DB for the specific request using the unique URL.
    cursor = await audit_logger.db.connection.execute(
        """
        SELECT request_params FROM audit_log
        WHERE tool_name='request' AND tool_category='http'
          AND request_params LIKE ?
        ORDER BY timestamp DESC LIMIT 1
        """,
        (f"%{unique_url}%",),
    )
    row = await cursor.fetchone()
    assert row is not None, "No audit log found for the test request"
    params_str = row["request_params"]
    # Template should appear in the log, not the resolved value
    assert "{{secret:MY_TOKEN}}" in params_str, f"Template not found in params: {params_str}"
    assert "resolved_value" not in params_str, f"Resolved value leaked into audit log: {params_str}"
