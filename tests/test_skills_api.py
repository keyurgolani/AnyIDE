"""API tests for skills module endpoints and HITL behavior."""

from __future__ import annotations

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

# Set up test environment before app import.
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_SKILLS = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()


@pytest.fixture
def seeded_skills_dir():
    sample = os.path.join(TEST_SKILLS, "sample-skill")
    os.makedirs(sample, exist_ok=True)
    with open(os.path.join(sample, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(
            "\n".join(
                [
                    "---",
                    "name: sample-skill",
                    "description: Sample skill for API tests",
                    "---",
                    "",
                    "# Sample Skill",
                    "",
                    "## API",
                    "Skill API content.",
                    "",
                ]
            )
        )

    scripts_dir = os.path.join(sample, "scripts")
    os.makedirs(scripts_dir, exist_ok=True)
    with open(os.path.join(scripts_dir, "helper.sh"), "w", encoding="utf-8") as f:
        f.write("echo helper\n")

    return TEST_SKILLS


@pytest.fixture
async def client(seeded_skills_dir):
    os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
    os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")

    import anyide.config

    original_load = anyide.config.load_config

    def patched_load(config_path: str = "config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        cfg.skills.base_dir = seeded_skills_dir
        return cfg

    anyide.config.load_config = patched_load

    from anyide.main import app, db

    await db.connect()
    from anyide import main as main_module

    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)
    main_module.config.skills.base_dir = seeded_skills_dir
    skills_module = main_module.module_registry.modules.get("skills")
    if skills_module is not None:
        skills_module.skills_tools.base_dir = os.path.realpath(seeded_skills_dir)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac

    await db.close()
    anyide.config.load_config = original_load


class TestSkillsAPI:
    @pytest.mark.asyncio
    async def test_skills_endpoints_exist_in_openapi(self, client):
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/api/tools/skills/list" in paths
        assert "/api/tools/skills/read" in paths
        assert "/api/tools/skills/read_file" in paths
        assert "/api/tools/skills/search" in paths
        assert "/api/tools/skills/install" in paths

    @pytest.mark.asyncio
    async def test_skills_list_read_and_read_file_work_offline(self, client):
        list_resp = await client.post("/api/tools/skills/list")
        assert list_resp.status_code == 200
        listed = list_resp.json()["skills"]
        assert any(item["name"] == "sample-skill" for item in listed)

        read_resp = await client.post(
            "/api/tools/skills/read",
            json={"name": "sample-skill"},
        )
        assert read_resp.status_code == 200
        assert "Sample Skill" in read_resp.json()["content"]

        read_file_resp = await client.post(
            "/api/tools/skills/read_file",
            json={"name": "sample-skill", "file_path": "scripts/helper.sh"},
        )
        assert read_file_resp.status_code == 200
        assert "helper" in read_file_resp.json()["content"]

    @pytest.mark.asyncio
    async def test_skills_search_uses_cli_parsing(self, client, monkeypatch):
        from anyide import main as main_module

        module = main_module.module_registry.modules["skills"]

        async def fake_run(*_args, **_kwargs):
            return (
                '[{"name":"react-modernization","repo":"acme/skills","description":"React upgrade","installs":42}]',
                "",
                0,
            )

        monkeypatch.setattr(module.skills_tools, "_run_skills_cli", fake_run)

        response = await client.post(
            "/api/tools/skills/search",
            json={"query": "react", "max_results": 10},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["results"][0]["name"] == "react-modernization"
        assert payload["results"][0]["installs"] == 42

    @pytest.mark.asyncio
    async def test_skills_search_accepts_plaintext_cli_output(self, client, monkeypatch):
        from anyide import main as main_module

        module = main_module.module_registry.modules["skills"]

        async def fake_run(*_args, **_kwargs):
            return (
                "\n".join(
                    [
                        "\u001b[38;5;145mpproenca/dot-skills@vitest\u001b[0m \u001b[36m247 installs\u001b[0m",
                        "\u001b[38;5;102m└ https://skills.sh/pproenca/dot-skills/vitest\u001b[0m",
                    ]
                ),
                "",
                0,
            )

        monkeypatch.setattr(module.skills_tools, "_run_skills_cli", fake_run)

        response = await client.post(
            "/api/tools/skills/search",
            json={"query": "vitest", "max_results": 10},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["results"][0]["name"] == "vitest"
        assert payload["results"][0]["repo"] == "pproenca/dot-skills"
        assert payload["results"][0]["installs"] == 247

    @pytest.mark.asyncio
    async def test_skills_install_is_hitl_gated(self, client, monkeypatch):
        from anyide import main as main_module

        monkeypatch.setattr(
            main_module.hitl_manager,
            "create_request",
            AsyncMock(return_value=SimpleNamespace(id="req-1")),
        )
        monkeypatch.setattr(
            main_module.hitl_manager,
            "wait_for_decision",
            AsyncMock(return_value="rejected"),
        )

        response = await client.post(
            "/api/tools/skills/install",
            json={"repo": "vercel-labs/agent-skills", "skill_name": "sample-skill"},
        )
        assert response.status_code == 403
        payload = response.json()
        assert payload["error"] is True
        assert payload["error_type"] == "security_error"
