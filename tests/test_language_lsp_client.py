"""Resilience tests for language-module LSP process manager."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from anyide.modules.language.lsp_client import LSPManager


def _write_mock_lsp_server(tmp_path: Path) -> Path:
    server = tmp_path / "mock_lsp_server.py"
    server.write_text(
        """
import json
import sys
import time
from pathlib import Path


def send(payload):
    raw = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(raw)}\\r\\n\\r\\n".encode("ascii")
    sys.stdout.buffer.write(header + raw)
    sys.stdout.buffer.flush()


def read_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\\r\\n", b"\\n"):
            break
        if b":" not in line:
            continue
        key, value = line.decode("utf-8", errors="replace").split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def main():
    mode = sys.argv[1]
    marker_path = Path(sys.argv[2])
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(marker_path.read_text() + "start\\n" if marker_path.exists() else "start\\n")

    while True:
        message = read_message()
        if message is None:
            return

        method = message.get("method")
        req_id = message.get("id")

        if method == "initialize":
            if mode == "init-timeout":
                time.sleep(60)
                continue
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"capabilities": {"diagnosticProvider": True}},
                }
            )
            continue

        if method == "initialized":
            continue

        if method in {"textDocument/didOpen", "textDocument/didChange"}:
            if mode == "push-diagnostics":
                params = message.get("params") or {}
                text_document = params.get("textDocument") or {}
                uri = text_document.get("uri")
                if isinstance(uri, str):
                    time.sleep(0.1)
                    send(
                        {
                            "jsonrpc": "2.0",
                            "method": "textDocument/publishDiagnostics",
                            "params": {
                                "uri": uri,
                                "diagnostics": [
                                    {
                                        "range": {
                                            "start": {"line": 0, "character": 0},
                                            "end": {"line": 0, "character": 1},
                                        },
                                        "severity": 1,
                                        "message": "mock push diagnostic",
                                    }
                                ],
                            },
                        }
                    )
            continue

        if method == "textDocument/diagnostic":
            if mode == "push-diagnostics":
                send(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": "Method not found"},
                    }
                )
                continue
            if mode == "diagnostic-timeout":
                time.sleep(60)
                continue
            send(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "kind": "full",
                        "items": [
                            {
                                "range": {
                                    "start": {"line": 0, "character": 0},
                                    "end": {"line": 0, "character": 1},
                                },
                                "severity": 1,
                                "message": "mock diagnostic",
                            }
                        ],
                    },
                }
            )
            if mode == "crash-after-diagnostic":
                sys.exit(1)


if __name__ == "__main__":
    main()
        """.strip()
        + "\n",
        encoding="utf-8",
    )
    return server


def _read_start_count(marker_path: Path) -> int:
    if not marker_path.exists():
        return 0
    return len([line for line in marker_path.read_text(encoding="utf-8").splitlines() if line == "start"])


@pytest.mark.asyncio
async def test_lsp_manager_lazy_start_and_initialize(tmp_path: Path):
    script = _write_mock_lsp_server(tmp_path)
    marker = tmp_path / "normal-starts.log"
    manager = LSPManager(
        workspace_root=str(tmp_path),
        lsp_servers={
            "python": f"{sys.executable} {script} normal {marker}",
        },
        initialize_timeout_seconds=1.0,
        request_timeout_seconds=1.0,
    )

    source_path = tmp_path / "sample.py"
    source_path.write_text("def x() -> int:\n    return 1\n", encoding="utf-8")

    assert manager.active_languages() == []

    diagnostics = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )

    assert diagnostics
    assert diagnostics[0].message == "mock diagnostic"
    assert manager.active_languages() == ["python"]

    await manager.shutdown()


@pytest.mark.asyncio
async def test_lsp_manager_marks_language_unavailable_after_init_timeout(tmp_path: Path):
    script = _write_mock_lsp_server(tmp_path)
    marker = tmp_path / "init-timeout-starts.log"
    manager = LSPManager(
        workspace_root=str(tmp_path),
        lsp_servers={
            "python": f"{sys.executable} {script} init-timeout {marker}",
        },
        initialize_timeout_seconds=0.2,
        request_timeout_seconds=0.2,
    )

    source_path = tmp_path / "sample.py"
    source_path.write_text("def x() -> int:\n    return 1\n", encoding="utf-8")

    first = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )
    second = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )

    assert first == []
    assert second == []
    assert manager.is_unavailable("python")
    assert _read_start_count(marker) == 1

    await manager.shutdown()


@pytest.mark.asyncio
async def test_lsp_manager_resets_server_when_request_times_out(tmp_path: Path):
    script = _write_mock_lsp_server(tmp_path)
    marker = tmp_path / "diagnostic-timeout-starts.log"
    manager = LSPManager(
        workspace_root=str(tmp_path),
        lsp_servers={
            "python": f"{sys.executable} {script} diagnostic-timeout {marker}",
        },
        initialize_timeout_seconds=1.0,
        request_timeout_seconds=0.2,
    )

    source_path = tmp_path / "sample.py"
    source_path.write_text("def x() -> int:\n    return 1\n", encoding="utf-8")

    diagnostics = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )

    assert diagnostics == []
    assert manager.active_languages() == []
    assert not manager.is_unavailable("python")

    await manager.shutdown()


@pytest.mark.asyncio
async def test_lsp_manager_uses_publish_diagnostics_fallback(tmp_path: Path):
    script = _write_mock_lsp_server(tmp_path)
    marker = tmp_path / "push-diagnostics-starts.log"
    manager = LSPManager(
        workspace_root=str(tmp_path),
        lsp_servers={
            "python": f"{sys.executable} {script} push-diagnostics {marker}",
        },
        initialize_timeout_seconds=1.0,
        request_timeout_seconds=1.0,
        published_diagnostics_wait_seconds=0.4,
    )

    source_path = tmp_path / "sample.py"
    source_path.write_text("def x() -> int:\n    return 1\n", encoding="utf-8")

    diagnostics = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )

    assert diagnostics
    assert diagnostics[0].message == "mock push diagnostic"

    await manager.shutdown()


@pytest.mark.asyncio
async def test_lsp_manager_restarts_after_crash_on_next_request(tmp_path: Path):
    script = _write_mock_lsp_server(tmp_path)
    marker = tmp_path / "crash-starts.log"
    manager = LSPManager(
        workspace_root=str(tmp_path),
        lsp_servers={
            "python": f"{sys.executable} {script} crash-after-diagnostic {marker}",
        },
        initialize_timeout_seconds=1.0,
        request_timeout_seconds=1.0,
    )

    source_path = tmp_path / "sample.py"
    source_path.write_text("def x() -> int:\n    return 1\n", encoding="utf-8")

    first = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )
    await asyncio.sleep(0.2)
    second = await manager.diagnostics(
        language="python",
        file_path=str(source_path),
        content=source_path.read_text(encoding="utf-8"),
    )

    assert first
    assert second
    assert _read_start_count(marker) >= 2

    await manager.shutdown()
