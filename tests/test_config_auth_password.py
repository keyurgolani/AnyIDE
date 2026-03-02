"""Tests for admin password source precedence in config loading."""

from pathlib import Path

from anyide.config import load_config


def _write_config(tmp_path: Path, password: str) -> str:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"auth:\n  admin_password: \"{password}\"\n",
        encoding="utf-8",
    )
    return str(config_path)


def test_load_config_prefers_anyide_admin_password(monkeypatch, tmp_path):
    config_path = _write_config(tmp_path, "config-password")
    monkeypatch.setenv("ANYIDE_ADMIN_PASSWORD", "secret-anyide")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-legacy")

    config = load_config(config_path)

    assert config.auth.admin_password == "secret-anyide"


def test_load_config_falls_back_to_legacy_admin_password(monkeypatch, tmp_path):
    config_path = _write_config(tmp_path, "config-password")
    monkeypatch.delenv("ANYIDE_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-legacy")

    config = load_config(config_path)

    assert config.auth.admin_password == "secret-legacy"


def test_load_config_falls_back_to_config_when_env_unset(monkeypatch, tmp_path):
    config_path = _write_config(tmp_path, "config-password")
    monkeypatch.delenv("ANYIDE_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)

    config = load_config(config_path)

    assert config.auth.admin_password == "config-password"


def test_load_config_ignores_empty_env_passwords(monkeypatch, tmp_path):
    config_path = _write_config(tmp_path, "config-password")
    monkeypatch.setenv("ANYIDE_ADMIN_PASSWORD", "")
    monkeypatch.setenv("ADMIN_PASSWORD", "   ")

    config = load_config(config_path)

    assert config.auth.admin_password == "config-password"
