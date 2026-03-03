"""
Load testing for HostBridge - Tests for concurrent access and performance.

These tests verify the system can handle:
- Multiple concurrent tool calls
- High volume of requests
"""

import asyncio
import os
import tempfile
import time
from statistics import mean

import pytest
from httpx import AsyncClient, ASGITransport

# Set up test environment BEFORE any imports
TEST_WORKSPACE = tempfile.mkdtemp()
TEST_DATA_DIR = tempfile.mkdtemp()

# Set environment variables BEFORE importing any src modules
os.environ["WORKSPACE_BASE_DIR"] = TEST_WORKSPACE
os.environ["DB_PATH"] = os.path.join(TEST_DATA_DIR, "hostbridge.db")


@pytest.fixture
async def client():
    """Create test client."""
    import anyide.config
    original_load = anyide.config.load_config

    def patched_load(config_path="config.yaml"):
        cfg = original_load(config_path)
        cfg.workspace.base_dir = TEST_WORKSPACE
        return cfg

    anyide.config.load_config = patched_load

    from anyide.main import app, db
    await db.connect()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await db.close()
    anyide.config.load_config = original_load


class TestConcurrentAccess:
    """Tests for concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_file_writes(self, client):
        """Test multiple concurrent file write operations."""
        async def write_file(i):
            response = await client.post(
                "/api/tools/fs/write",
                json={"path": f"concurrent_{i}.txt", "content": f"content_{i}"}
            )
            return response.status_code

        # Execute 10 concurrent writes
        tasks = [write_file(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        success_count = sum(1 for r in results if r == 200)
        assert success_count >= 8, f"Only {success_count}/10 succeeded"

    @pytest.mark.asyncio
    async def test_concurrent_file_reads(self, client):
        """Test multiple concurrent file read operations."""
        # First create a file
        await client.post(
            "/api/tools/fs/write",
            json={"path": "read_test.txt", "content": "test content"}
        )

        async def read_file():
            response = await client.post(
                "/api/tools/fs/read",
                json={"path": "read_test.txt"}
            )
            return response.status_code

        # Execute 20 concurrent reads
        tasks = [read_file() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r == 200 for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_directory_listings(self, client):
        """Test multiple concurrent directory listing operations."""
        async def list_dir():
            response = await client.post(
                "/api/tools/fs/list",
                json={"path": ".", "recursive": False}
            )
            return response.status_code

        # Execute 15 concurrent listings
        tasks = [list_dir() for _ in range(15)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r == 200 for r in results)


class TestResponseTimes:
    """Tests for response time requirements."""

    @pytest.mark.asyncio
    async def test_response_times(self, client):
        """Test that response times are reasonable."""
        response_times = []

        for i in range(10):
            start = time.time()
            response = await client.post(
                "/api/tools/fs/write",
                json={"path": f"timing_{i}.txt", "content": f"content_{i}"}
            )
            response_times.append(time.time() - start)
            assert response.status_code == 200

        avg_time = mean(response_times)
        max_time = max(response_times)

        print("\nResponse Time Stats:")
        print(f"  Avg: {avg_time*1000:.2f}ms")
        print(f"  Max: {max_time*1000:.2f}ms")

        # Response times should be reasonable (under 1 second)
        assert max_time < 1.0, f"Max response time too high: {max_time*1000:.2f}ms"
