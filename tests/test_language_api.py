"""API tests for language module route registration."""

from __future__ import annotations

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

# Set up test environment before app import.
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()


@pytest.fixture
async def client():
    os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
    os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")

    import anyide.config

    original_load = anyide.config.load_config

    def patched_load(config_path: str = "config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg

    anyide.config.load_config = patched_load

    from anyide.main import app, db

    await db.connect()
    from anyide import main as main_module

    main_module.config.workspace.base_dir = TEST_WORKSPACE
    main_module.workspace_manager.base_dir = os.path.realpath(TEST_WORKSPACE)

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as ac:
        yield ac

    await db.close()
    anyide.config.load_config = original_load


class TestLanguageAPI:
    @pytest.mark.asyncio
    async def test_language_endpoints_exist_in_openapi(self, client):
        response = await client.get("/openapi.json")
        assert response.status_code == 200

        paths = response.json()["paths"]
        assert "/api/tools/language/read_file" in paths
        assert "/api/tools/language/skeleton" in paths
        assert "/api/tools/language/diff" in paths
        assert "/api/tools/language/apply_patch" in paths
        assert "/api/tools/language/create_file" in paths
        assert "/api/tools/language/index" in paths
        assert "/api/tools/language/search_symbols" in paths
        assert "/api/tools/language/reference_graph" in paths
        assert "/api/tools/language/validate" in paths

    @pytest.mark.asyncio
    async def test_language_subapp_openapi_exists(self, client):
        response = await client.get("/tools/language/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert "Language" in spec["info"]["title"]
        assert "/read_file" in spec["paths"]
