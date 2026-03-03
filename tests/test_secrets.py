"""Tests for SecretManager — loading, template resolution, and masking."""

import tempfile

import pytest

from anyide.core.secrets import SecretManager, SecretNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_secrets_file(content: str) -> str:
    """Write *content* to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False)
    tmp.write(content)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------

class TestSecretManagerLoading:
    """Tests for .env file loading."""

    def test_load_basic_key_value(self, tmp_path):
        """Load a simple KEY=VALUE pair."""
        f = tmp_path / "secrets.env"
        f.write_text("TOKEN=abc123\n")
        sm = SecretManager(str(f))
        assert sm.count() == 1
        assert sm.list_keys() == ["TOKEN"]

    def test_load_multiple_secrets(self, tmp_path):
        """Load multiple KEY=VALUE pairs."""
        f = tmp_path / "secrets.env"
        f.write_text("API_KEY=key1\nDB_PASS=pass2\n")
        sm = SecretManager(str(f))
        assert sm.count() == 2
        assert sorted(sm.list_keys()) == ["API_KEY", "DB_PASS"]

    def test_skip_comments_and_blank_lines(self, tmp_path):
        """Comments and blank lines are ignored."""
        f = tmp_path / "secrets.env"
        f.write_text("# This is a comment\n\nTOKEN=secret\n\n")
        sm = SecretManager(str(f))
        assert sm.count() == 1

    def test_strip_quoted_values(self, tmp_path):
        """Double-quoted and single-quoted values are stripped."""
        f = tmp_path / "secrets.env"
        f.write_text('A="double"\nB=\'single\'\n')
        sm = SecretManager(str(f))
        # list_keys only, we test resolution below
        assert sm.count() == 2

    def test_value_with_equals(self, tmp_path):
        """Values that contain '=' are handled correctly."""
        f = tmp_path / "secrets.env"
        f.write_text("CONN=host=localhost;port=5432\n")
        sm = SecretManager(str(f))
        resolved = sm.resolve_value("{{secret:CONN}}")
        assert resolved == "host=localhost;port=5432"

    def test_missing_file_is_silent(self, tmp_path):
        """A missing file produces 0 secrets (no exception)."""
        sm = SecretManager(str(tmp_path / "nonexistent.env"))
        assert sm.count() == 0

    def test_reload_picks_up_changes(self, tmp_path):
        """Reload re-reads the file."""
        f = tmp_path / "secrets.env"
        f.write_text("TOKEN=first\n")
        sm = SecretManager(str(f))
        assert sm.count() == 1

        f.write_text("TOKEN=first\nEXTRA=second\n")
        count = sm.reload()
        assert count == 2
        assert sm.count() == 2


# ---------------------------------------------------------------------------
# Template resolution tests
# ---------------------------------------------------------------------------

class TestSecretTemplateResolution:
    """Tests for {{secret:KEY}} template resolution."""

    @pytest.fixture
    def sm(self, tmp_path):
        f = tmp_path / "secrets.env"
        f.write_text("TOKEN=mytoken\nPASS=s3cr3t\n")
        return SecretManager(str(f))

    def test_resolve_simple_template(self, sm):
        """Single template in a string resolves correctly."""
        result = sm.resolve_value("Bearer {{secret:TOKEN}}")
        assert result == "Bearer mytoken"

    def test_resolve_multiple_templates_in_one_string(self, sm):
        """Multiple templates in one string are all resolved."""
        result = sm.resolve_value("{{secret:TOKEN}}:{{secret:PASS}}")
        assert result == "mytoken:s3cr3t"

    def test_resolve_string_without_template(self, sm):
        """A plain string (no templates) is returned unchanged."""
        assert sm.resolve_value("plain string") == "plain string"

    def test_missing_key_raises_error(self, sm):
        """Referencing a missing key raises SecretNotFoundError."""
        with pytest.raises(SecretNotFoundError, match="MISSING_KEY"):
            sm.resolve_value("{{secret:MISSING_KEY}}")

    def test_resolve_params_dict(self, sm):
        """resolve_params replaces templates in a flat dict."""
        params = {"Authorization": "Bearer {{secret:TOKEN}}"}
        result = sm.resolve_params(params)
        assert result["Authorization"] == "Bearer mytoken"

    def test_resolve_params_nested_dict(self, sm):
        """resolve_params recurses into nested dicts."""
        params = {"headers": {"X-Pass": "{{secret:PASS}}"}}
        result = sm.resolve_params(params)
        assert result["headers"]["X-Pass"] == "s3cr3t"

    def test_resolve_params_list(self, sm):
        """resolve_params recurses into lists."""
        params = {"values": ["{{secret:TOKEN}}", "plain"]}
        result = sm.resolve_params(params)
        assert result["values"][0] == "mytoken"
        assert result["values"][1] == "plain"

    def test_resolve_params_preserves_originals(self, sm):
        """resolve_params deep-copies — original dict is not mutated."""
        params = {"Authorization": "Bearer {{secret:TOKEN}}"}
        sm.resolve_params(params)
        # Original must still have the template string
        assert params["Authorization"] == "Bearer {{secret:TOKEN}}"

    def test_has_templates_true(self, sm):
        """has_templates returns True when templates are present."""
        assert sm.has_templates({"key": "{{secret:TOKEN}}"}) is True

    def test_has_templates_false(self, sm):
        """has_templates returns False when no templates present."""
        assert sm.has_templates({"key": "plain"}) is False


# ---------------------------------------------------------------------------
# Masking tests
# ---------------------------------------------------------------------------

class TestSecretMasking:
    """Tests for secret value masking in logs/errors."""

    @pytest.fixture
    def sm(self, tmp_path):
        f = tmp_path / "secrets.env"
        f.write_text("TOKEN=supersecret\nPASS=hunter2\n")
        return SecretManager(str(f))

    def test_mask_value_replaces_secret(self, sm):
        """Literal secret values in text are replaced with [REDACTED]."""
        text = "Error: bad token supersecret in request"
        result = sm.mask_value(text)
        assert "supersecret" not in result
        assert "[REDACTED]" in result

    def test_mask_value_multiple_secrets(self, sm):
        """Multiple different secrets are all masked."""
        text = "supersecret and hunter2"
        result = sm.mask_value(text)
        assert "supersecret" not in result
        assert "hunter2" not in result

    def test_mask_value_no_secret_present(self, sm):
        """Text without secrets is returned unchanged."""
        text = "Nothing sensitive here"
        assert sm.mask_value(text) == text

    def test_mask_params_dict(self, sm):
        """mask_params replaces secret values in a dict."""
        params = {"token": "supersecret"}
        result = sm.mask_params(params)
        assert result["token"] == "[REDACTED]"

    def test_mask_params_preserves_originals(self, sm):
        """mask_params deep-copies — original dict is not mutated."""
        params = {"token": "supersecret"}
        sm.mask_params(params)
        assert params["token"] == "supersecret"
