"""Minimal JSON-RPC LSP process manager for language module enrichments."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

from anyide.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_LSP_COMMANDS: dict[str, list[str]] = {
    "pyright": ["pyright-langserver", "--stdio"],
    "pyright-langserver": ["pyright-langserver", "--stdio"],
    "typescript-language-server": ["typescript-language-server", "--stdio"],
    "gopls": ["gopls"],
}

LANGUAGE_ID_MAP: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "csharp",
    "bash": "shellscript",
}

DIAGNOSTIC_SEVERITY_MAP = {
    1: "error",
    2: "warning",
    3: "info",
    4: "hint",
}


class LSPProtocolError(RuntimeError):
    """Raised when an LSP request fails with JSON-RPC protocol error."""


class LSPUnavailableError(RuntimeError):
    """Raised when the language-server process is unavailable."""


@dataclass(frozen=True)
class LSPDiagnostic:
    """Normalized diagnostic payload from LSP."""

    line: int
    col: int
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class LSPLocation:
    """Normalized LSP location."""

    path: str
    line: int
    col: int


@dataclass
class _DocumentState:
    version: int
    text: str


class _LSPServer:
    """Single LSP server subprocess with request/response wiring."""

    def __init__(
        self,
        language: str,
        command: list[str],
        process: asyncio.subprocess.Process,
        on_exit: Callable[["_LSPServer"], None],
    ):
        self.language = language
        self.command = command
        self.process = process
        self.capabilities: dict = {}
        self._next_id = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._write_lock = asyncio.Lock()
        self._documents: dict[str, _DocumentState] = {}
        self._published_diagnostics: dict[str, list[dict]] = {}
        self._closed = False
        self._on_exit = on_exit

        self._stdout_task = asyncio.create_task(self._stdout_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())
        self._wait_task = asyncio.create_task(self._wait_loop())

    def is_running(self) -> bool:
        return not self._closed and self.process.returncode is None

    def get_published_diagnostics(self, uri: str) -> list[dict]:
        return list(self._published_diagnostics.get(uri, []))

    async def sync_document(self, file_path: str, language: str, text: str) -> str:
        if not self.is_running():
            raise LSPUnavailableError(f"LSP server for '{self.language}' is not running")

        uri = Path(file_path).resolve().as_uri()
        state = self._documents.get(uri)
        language_id = LANGUAGE_ID_MAP.get(language, language)

        if state is None:
            self._documents[uri] = _DocumentState(version=1, text=text)
            await self.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": language_id,
                        "version": 1,
                        "text": text,
                    }
                },
            )
            return uri

        if state.text != text:
            next_version = state.version + 1
            self._documents[uri] = _DocumentState(version=next_version, text=text)
            await self.notify(
                "textDocument/didChange",
                {
                    "textDocument": {
                        "uri": uri,
                        "version": next_version,
                    },
                    "contentChanges": [{"text": text}],
                },
            )

        return uri

    async def request(self, method: str, params: dict, timeout: float) -> dict | list | None:
        if not self.is_running():
            raise LSPUnavailableError(f"LSP server for '{self.language}' is not running")

        request_id = self._next_id
        self._next_id += 1

        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        try:
            await self._send_payload(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise TimeoutError(f"LSP request timed out: {method}") from exc
        finally:
            self._pending.pop(request_id, None)

    async def notify(self, method: str, params: dict) -> None:
        if not self.is_running():
            raise LSPUnavailableError(f"LSP server for '{self.language}' is not running")
        await self._send_payload(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )

    async def close(self) -> None:
        self._closed = True
        self._fail_pending(LSPUnavailableError("LSP server closed"))

        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                self.process.kill()
                await self.process.wait()

        for task in (self._stdout_task, self._stderr_task, self._wait_task):
            task.cancel()
        await asyncio.gather(
            self._stdout_task,
            self._stderr_task,
            self._wait_task,
            return_exceptions=True,
        )

    async def _send_payload(self, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")

        stdin = self.process.stdin
        if stdin is None:
            raise LSPUnavailableError("LSP stdin is unavailable")

        async with self._write_lock:
            stdin.write(header + raw)
            await stdin.drain()

    async def _stdout_loop(self) -> None:
        try:
            while True:
                message = await self._read_message()
                if message is None:
                    break
                await self._handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("lsp_stdout_loop_error", language=self.language, error=str(exc))
        finally:
            if not self._closed:
                self._fail_pending(LSPUnavailableError("LSP stdout closed"))

    async def _stderr_loop(self) -> None:
        stderr = self.process.stderr
        if stderr is None:
            return

        try:
            while True:
                line = await stderr.readline()
                if not line:
                    return
                message = line.decode("utf-8", errors="replace").rstrip()
                if message:
                    logger.debug("lsp_stderr", language=self.language, message=message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive path
            logger.debug("lsp_stderr_loop_error", language=self.language, error=str(exc))

    async def _wait_loop(self) -> None:
        try:
            return_code = await self.process.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("lsp_wait_failed", language=self.language, error=str(exc))
            return

        if self._closed:
            return

        self._closed = True
        self._fail_pending(LSPUnavailableError("LSP process exited"))
        logger.warning(
            "lsp_process_exited",
            language=self.language,
            return_code=return_code,
            command=self.command,
        )
        self._on_exit(self)

    async def _read_message(self) -> Optional[dict]:
        stdout = self.process.stdout
        if stdout is None:
            return None

        headers: dict[str, str] = {}
        while True:
            line = await stdout.readline()
            if not line:
                return None
            if line in (b"\r\n", b"\n"):
                break
            decoded = line.decode("utf-8", errors="replace").strip()
            if ":" not in decoded:
                continue
            key, value = decoded.split(":", 1)
            headers[key.strip().lower()] = value.strip()

        length_raw = headers.get("content-length")
        if not length_raw:
            return None

        try:
            length = int(length_raw)
        except ValueError:
            return None
        if length <= 0:
            return None

        try:
            payload = await stdout.readexactly(length)
        except asyncio.IncompleteReadError:
            return None

        try:
            return json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    async def _handle_message(self, message: dict) -> None:
        if "id" in message:
            request_id = message.get("id")
            if not isinstance(request_id, int):
                return
            future = self._pending.get(request_id)
            if future is None or future.done():
                return
            if "error" in message and message["error"]:
                error_obj = message["error"] if isinstance(message["error"], dict) else {}
                future.set_exception(
                    LSPProtocolError(error_obj.get("message", "LSP request failed"))
                )
                return
            future.set_result(message.get("result"))
            return

        method = message.get("method")
        if method != "textDocument/publishDiagnostics":
            return

        params = message.get("params")
        if not isinstance(params, dict):
            return

        uri = params.get("uri")
        diagnostics = params.get("diagnostics")
        if isinstance(uri, str) and isinstance(diagnostics, list):
            self._published_diagnostics[uri] = diagnostics

    def _fail_pending(self, error: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()


class LSPManager:
    """LSP process lifecycle manager with lazy startup and crash recovery."""

    def __init__(
        self,
        workspace_root: str,
        lsp_servers: Optional[dict[str, str]] = None,
        initialize_timeout_seconds: float = 5.0,
        request_timeout_seconds: float = 5.0,
        published_diagnostics_wait_seconds: float = 1.0,
    ):
        self.workspace_root = os.path.realpath(workspace_root)
        self._lsp_servers = dict(lsp_servers or {})
        self._initialize_timeout_seconds = initialize_timeout_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._published_diagnostics_wait_seconds = max(0.0, published_diagnostics_wait_seconds)

        self._servers: dict[str, _LSPServer] = {}
        self._startup_locks: dict[str, asyncio.Lock] = {}
        self._unavailable_languages: set[str] = set()

    def get_server_name(self, language: str) -> Optional[str]:
        value = self._lsp_servers.get(language)
        if value is None:
            return None
        trimmed = value.strip()
        return trimmed or None

    def is_unavailable(self, language: str) -> bool:
        return language in self._unavailable_languages

    def active_languages(self) -> list[str]:
        return sorted(
            language
            for language, server in self._servers.items()
            if server.is_running()
        )

    async def shutdown(self) -> None:
        languages = list(self._servers.keys())
        for language in languages:
            await self._reset_server(language)

    async def diagnostics(
        self,
        language: str,
        file_path: str,
        content: str,
    ) -> list[LSPDiagnostic]:
        server = await self._ensure_server(language)
        if server is None:
            return []

        try:
            uri = await server.sync_document(file_path, language, content)
            result = await server.request(
                "textDocument/diagnostic",
                {"textDocument": {"uri": uri}},
                timeout=self._request_timeout_seconds,
            )
            diagnostics = self._parse_diagnostics(result)
            if diagnostics:
                return diagnostics
            return await self._await_published_diagnostics(server, uri)
        except LSPProtocolError:
            uri = Path(file_path).resolve().as_uri()
            return await self._await_published_diagnostics(server, uri)
        except TimeoutError:
            logger.warning("lsp_request_timeout", language=language, method="textDocument/diagnostic")
            await self._reset_server(language)
            return []
        except (LSPUnavailableError, ConnectionResetError, BrokenPipeError):
            await self._reset_server(language)
            return []

    async def _await_published_diagnostics(
        self, server: _LSPServer, uri: str
    ) -> list[LSPDiagnostic]:
        diagnostics = self._parse_diagnostics(server.get_published_diagnostics(uri))
        if diagnostics:
            return diagnostics
        if self._published_diagnostics_wait_seconds <= 0:
            return diagnostics

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._published_diagnostics_wait_seconds

        while loop.time() < deadline:
            await asyncio.sleep(0.05)
            diagnostics = self._parse_diagnostics(server.get_published_diagnostics(uri))
            if diagnostics:
                return diagnostics

        return diagnostics

    async def references(
        self,
        language: str,
        file_path: str,
        content: str,
        line: int,
        col: int,
    ) -> list[LSPLocation]:
        return await self._location_request(
            language=language,
            file_path=file_path,
            content=content,
            method="textDocument/references",
            params_builder=lambda uri: {
                "textDocument": {"uri": uri},
                "position": {
                    "line": max(0, line - 1),
                    "character": max(0, col - 1),
                },
                "context": {"includeDeclaration": False},
            },
        )

    async def definitions(
        self,
        language: str,
        file_path: str,
        content: str,
        line: int,
        col: int,
    ) -> list[LSPLocation]:
        return await self._location_request(
            language=language,
            file_path=file_path,
            content=content,
            method="textDocument/definition",
            params_builder=lambda uri: {
                "textDocument": {"uri": uri},
                "position": {
                    "line": max(0, line - 1),
                    "character": max(0, col - 1),
                },
            },
        )

    async def hover(
        self,
        language: str,
        file_path: str,
        content: str,
        line: int,
        col: int,
    ) -> Optional[str]:
        server = await self._ensure_server(language)
        if server is None:
            return None

        try:
            uri = await server.sync_document(file_path, language, content)
            result = await server.request(
                "textDocument/hover",
                {
                    "textDocument": {"uri": uri},
                    "position": {
                        "line": max(0, line - 1),
                        "character": max(0, col - 1),
                    },
                },
                timeout=self._request_timeout_seconds,
            )
            return self._parse_hover(result)
        except LSPProtocolError:
            return None
        except TimeoutError:
            logger.warning("lsp_request_timeout", language=language, method="textDocument/hover")
            await self._reset_server(language)
            return None
        except (LSPUnavailableError, ConnectionResetError, BrokenPipeError):
            await self._reset_server(language)
            return None

    async def _location_request(
        self,
        language: str,
        file_path: str,
        content: str,
        method: str,
        params_builder: Callable[[str], dict],
    ) -> list[LSPLocation]:
        server = await self._ensure_server(language)
        if server is None:
            return []

        try:
            uri = await server.sync_document(file_path, language, content)
            result = await server.request(
                method,
                params_builder(uri),
                timeout=self._request_timeout_seconds,
            )
            return self._parse_locations(result)
        except LSPProtocolError:
            return []
        except TimeoutError:
            logger.warning("lsp_request_timeout", language=language, method=method)
            await self._reset_server(language)
            return []
        except (LSPUnavailableError, ConnectionResetError, BrokenPipeError):
            await self._reset_server(language)
            return []

    async def _ensure_server(self, language: str) -> Optional[_LSPServer]:
        server_name = self.get_server_name(language)
        if server_name is None:
            return None
        if language in self._unavailable_languages:
            return None

        existing = self._servers.get(language)
        if existing is not None and existing.is_running():
            return existing
        if existing is not None:
            await self._reset_server(language)

        lock = self._startup_locks.setdefault(language, asyncio.Lock())
        async with lock:
            existing = self._servers.get(language)
            if existing is not None and existing.is_running():
                return existing
            if language in self._unavailable_languages:
                return None

            command = self._resolve_command(server_name)
            if not command:
                self._unavailable_languages.add(language)
                return None

            try:
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError:
                logger.warning(
                    "lsp_binary_not_found",
                    language=language,
                    server=server_name,
                    command=command,
                )
                self._unavailable_languages.add(language)
                return None
            except Exception as exc:  # pragma: no cover - defensive path
                logger.warning(
                    "lsp_start_failed",
                    language=language,
                    server=server_name,
                    error=str(exc),
                )
                self._unavailable_languages.add(language)
                return None

            server = _LSPServer(
                language=language,
                command=command,
                process=process,
                on_exit=self._on_server_exit,
            )
            self._servers[language] = server

            if not await self._initialize_server(language, server):
                self._unavailable_languages.add(language)
                return None

            return server

    async def _initialize_server(self, language: str, server: _LSPServer) -> bool:
        initialize_params = {
            "processId": os.getpid(),
            "clientInfo": {"name": "AnyIDE", "version": "0.1.0"},
            "rootUri": Path(self.workspace_root).resolve().as_uri(),
            "workspaceFolders": [
                {
                    "uri": Path(self.workspace_root).resolve().as_uri(),
                    "name": Path(self.workspace_root).name or "workspace",
                }
            ],
            "capabilities": {
                "workspace": {
                    "workspaceFolders": True,
                },
                "textDocument": {
                    "hover": {
                        "contentFormat": ["markdown", "plaintext"],
                    },
                    "references": {
                        "dynamicRegistration": False,
                    },
                    "definition": {
                        "linkSupport": True,
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True,
                    },
                    "diagnostic": {
                        "dynamicRegistration": False,
                    },
                    "synchronization": {
                        "didSave": False,
                        "willSave": False,
                        "dynamicRegistration": False,
                    },
                },
            },
        }

        try:
            result = await server.request(
                "initialize",
                initialize_params,
                timeout=self._initialize_timeout_seconds,
            )
            if isinstance(result, dict):
                capabilities = result.get("capabilities", {})
                if isinstance(capabilities, dict):
                    server.capabilities = capabilities
            await server.notify("initialized", {})
            return True
        except Exception as exc:
            logger.warning(
                "lsp_initialize_failed",
                language=language,
                error=str(exc),
                command=server.command,
            )
            await self._reset_server(language)
            return False

    def _on_server_exit(self, server: _LSPServer) -> None:
        current = self._servers.get(server.language)
        if current is server:
            self._servers.pop(server.language, None)

    async def _reset_server(self, language: str) -> None:
        server = self._servers.pop(language, None)
        if server is None:
            return
        await server.close()

    @staticmethod
    def _resolve_command(server_name: str) -> list[str]:
        if server_name in DEFAULT_LSP_COMMANDS:
            return list(DEFAULT_LSP_COMMANDS[server_name])

        split = shlex.split(server_name)
        if not split:
            return []
        if len(split) == 1 and split[0] in DEFAULT_LSP_COMMANDS:
            return list(DEFAULT_LSP_COMMANDS[split[0]])
        return split

    @staticmethod
    def _parse_diagnostics(raw: dict | list | None) -> list[LSPDiagnostic]:
        if raw is None:
            return []
        if isinstance(raw, dict) and isinstance(raw.get("items"), list):
            items = raw["items"]
        elif isinstance(raw, dict) and isinstance(raw.get("diagnostics"), list):
            items = raw["diagnostics"]
        elif isinstance(raw, list):
            items = raw
        else:
            items = []

        diagnostics: list[LSPDiagnostic] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            range_obj = item.get("range")
            if not isinstance(range_obj, dict):
                continue
            start = range_obj.get("start")
            if not isinstance(start, dict):
                continue

            line = int(start.get("line", 0)) + 1
            col = int(start.get("character", 0)) + 1
            message = str(item.get("message", "type issue"))
            severity_no = int(item.get("severity", 1))
            severity = DIAGNOSTIC_SEVERITY_MAP.get(severity_no, "error")
            diagnostics.append(
                LSPDiagnostic(
                    line=line,
                    col=col,
                    message=message,
                    severity=severity,
                )
            )

        return diagnostics

    @staticmethod
    def _parse_locations(raw: dict | list | None) -> list[LSPLocation]:
        if raw is None:
            return []
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = [raw]
        else:
            return []

        locations: list[LSPLocation] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            uri = item.get("uri") or item.get("targetUri")
            if not isinstance(uri, str):
                continue
            range_obj = (
                item.get("range")
                or item.get("targetSelectionRange")
                or item.get("targetRange")
            )
            if not isinstance(range_obj, dict):
                continue
            start = range_obj.get("start")
            if not isinstance(start, dict):
                continue

            line = int(start.get("line", 0)) + 1
            col = int(start.get("character", 0)) + 1
            locations.append(
                LSPLocation(
                    path=_file_uri_to_path(uri),
                    line=line,
                    col=col,
                )
            )

        return locations

    @classmethod
    def _parse_hover(cls, raw: dict | list | str | None) -> Optional[str]:
        if raw is None:
            return None
        if isinstance(raw, str):
            return raw.strip() or None
        if isinstance(raw, list):
            parts = [cls._parse_hover(item) for item in raw]
            joined = "\n".join(part for part in parts if part)
            return joined.strip() or None
        if not isinstance(raw, dict):
            return None

        contents = raw.get("contents")
        if isinstance(contents, str):
            return contents.strip() or None
        if isinstance(contents, list):
            parts = [cls._parse_hover(part) for part in contents]
            joined = "\n".join(part for part in parts if part)
            return joined.strip() or None
        if isinstance(contents, dict):
            value = contents.get("value")
            if isinstance(value, str):
                return value.strip() or None
            language = contents.get("language")
            if isinstance(language, str):
                return language.strip() or None
        return None


def _file_uri_to_path(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return uri

    path = unquote(parsed.path)
    if os.name == "nt" and path.startswith("/"):
        path = path[1:]
    if parsed.netloc:
        path = f"//{parsed.netloc}{path}"
    return os.path.realpath(path)
