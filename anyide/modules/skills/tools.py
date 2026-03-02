"""Skills module tool implementations."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from anyide.logging_config import get_logger
from anyide.modules.skills.schemas import (
    SkillsInstallRequest,
    SkillsInstallResponse,
    SkillsListItem,
    SkillsListResponse,
    SkillsReadFileRequest,
    SkillsReadFileResponse,
    SkillsReadRequest,
    SkillsReadResponse,
    SkillsSearchRequest,
    SkillsSearchResponse,
    SkillsSearchResult,
)

logger = get_logger(__name__)


class SkillsTools:
    """Tools for listing, reading, searching, and installing skills."""

    SECTION_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
    PLAIN_SEARCH_LINE_RE = re.compile(
        r"^(?P<repo_skill>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+@[A-Za-z0-9._-]+)\s+"
        r"(?P<installs>[0-9,]+)\s+installs?\b",
        flags=re.IGNORECASE,
    )

    def __init__(self, base_dir: str = "/skills", cli_timeout: int = 180):
        self.base_dir = str(Path(base_dir).resolve())
        self.cli_timeout = cli_timeout

    async def list(self) -> SkillsListResponse:
        """List installed skills from the dedicated skills directory."""
        base = Path(self.base_dir)
        if not base.exists():
            return SkillsListResponse(skills=[], total=0)

        skills: list[SkillsListItem] = []
        for entry in sorted(base.iterdir(), key=lambda item: item.name.lower()):
            if not entry.is_dir():
                continue
            skill_md = entry / "SKILL.md"
            if not skill_md.is_file():
                continue

            metadata, _ = self._read_skill_markdown(skill_md)
            description = str(metadata.get("description", "")) if isinstance(metadata, dict) else ""
            size_bytes = skill_md.stat().st_size
            installed_at = datetime.fromtimestamp(
                entry.stat().st_mtime,
                tz=timezone.utc,
            ).isoformat()

            skills.append(
                SkillsListItem(
                    name=entry.name,
                    path=str(entry),
                    description=description,
                    size_bytes=size_bytes,
                    installed_at=installed_at,
                )
            )

        return SkillsListResponse(skills=skills, total=len(skills))

    async def read(self, request: SkillsReadRequest) -> SkillsReadResponse:
        """Read SKILL.md for an installed skill."""
        skill_dir = self._resolve_skill_dir(request.name)
        metadata, body = self._read_skill_markdown(skill_dir / "SKILL.md")
        content = body
        if request.section:
            content = self._extract_section(body, request.section)

        scripts = self._list_relative_files(skill_dir / "scripts")
        references = self._list_relative_files(skill_dir / "references")

        return SkillsReadResponse(
            name=request.name,
            content=content,
            metadata=metadata,
            has_scripts=len(scripts) > 0,
            has_references=len(references) > 0,
            scripts=scripts,
            references=references,
        )

    async def read_file(self, request: SkillsReadFileRequest) -> SkillsReadFileResponse:
        """Read a file within a skill directory."""
        skill_dir = self._resolve_skill_dir(request.name)
        target = (skill_dir / request.file_path).resolve()

        if not self._is_within(target, skill_dir):
            raise ValueError("Requested file resolves outside skill directory")
        if not target.exists() or not target.is_file():
            raise FileNotFoundError(
                f"File not found in skill '{request.name}': {request.file_path}"
            )

        content = target.read_text(encoding="utf-8", errors="replace")
        return SkillsReadFileResponse(content=content, path=str(target))

    async def search(self, request: SkillsSearchRequest) -> SkillsSearchResponse:
        """Search remote skills registry via `npx skills find`."""
        stdout, stderr, exit_code = await self._run_skills_cli(
            ["skills", "find", request.query, "--json"]
        )

        if exit_code != 0:
            message = (stderr or stdout or "unknown error").strip()
            if self._is_network_error(message):
                raise ConnectionError(
                    f"skills search failed due to network/egress restrictions: {message}"
                )
            raise RuntimeError(f"skills search failed: {message}")

        entries: list[Any] | None = None
        try:
            payload = self._extract_json_payload(stdout)
            if isinstance(payload, dict):
                candidate_entries = payload.get("results")
            else:
                candidate_entries = payload
            if isinstance(candidate_entries, list):
                entries = candidate_entries
        except ValueError:
            entries = None

        if entries is None:
            # Recent versions of the `skills` CLI can ignore `--json` and return
            # ANSI-colored plaintext output. Parse that format as a fallback.
            entries = self._extract_plaintext_search_results(stdout)
        if not entries:
            raise ValueError("Failed to parse skills search output")

        results: list[SkillsSearchResult] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("skill") or item.get("slug") or "").strip()
            if not name:
                continue
            repo = str(item.get("repo") or item.get("repository") or "").strip()
            description = str(item.get("description") or "").strip()
            installs = self._to_int(item.get("installs") or item.get("downloads") or 0)
            results.append(
                SkillsSearchResult(
                    name=name,
                    repo=repo,
                    description=description,
                    installs=installs,
                )
            )

        results = results[: request.max_results]
        return SkillsSearchResponse(query=request.query, results=results, total=len(results))

    async def install(self, request: SkillsInstallRequest) -> SkillsInstallResponse:
        """Install a skill via `npx skills add`."""
        args = ["skills", "add", request.repo, "--global", "-y"]
        if request.skill_name:
            args.extend(["--skill", request.skill_name])

        stdout, stderr, exit_code = await self._run_skills_cli(args, timeout=300)
        if exit_code != 0:
            message = (stderr or stdout or "unknown error").strip()
            if self._is_network_error(message):
                raise ConnectionError(
                    f"skills install failed due to network/egress restrictions: {message}"
                )
            raise RuntimeError(f"skills install failed: {message}")

        skill_dir = self._resolve_installed_skill_dir(request.skill_name)
        skill_md = skill_dir / "SKILL.md"
        preview = skill_md.read_text(encoding="utf-8", errors="replace")[:500]

        return SkillsInstallResponse(
            installed=True,
            skill_name=skill_dir.name,
            path=str(skill_dir),
            skill_md_preview=preview,
        )

    def _resolve_skill_dir(self, skill_name: str) -> Path:
        normalized = skill_name.strip()
        if not normalized:
            raise ValueError("Skill name cannot be empty")

        skill_dir = (Path(self.base_dir) / normalized).resolve()
        if not self._is_within(skill_dir, Path(self.base_dir)):
            raise ValueError("Skill path resolves outside skills directory")
        if not skill_dir.exists() or not skill_dir.is_dir():
            raise FileNotFoundError(f"Skill not found: {normalized}")
        if not (skill_dir / "SKILL.md").is_file():
            raise FileNotFoundError(f"SKILL.md not found for skill '{normalized}'")
        return skill_dir

    def _resolve_installed_skill_dir(self, requested_skill_name: str | None) -> Path:
        base = Path(self.base_dir)
        if requested_skill_name:
            candidate = (base / requested_skill_name).resolve()
            if self._is_within(candidate, base) and (candidate / "SKILL.md").is_file():
                return candidate

        if not base.exists() or not base.is_dir():
            raise FileNotFoundError(
                f"skills base directory does not exist or is not readable: {self.base_dir}"
            )

        candidates = [
            item
            for item in base.iterdir()
            if item.is_dir() and (item / "SKILL.md").is_file()
        ]
        if not candidates:
            raise FileNotFoundError(
                "skills install completed but no installed SKILL.md was found under /skills"
            )

        # Choose most recently touched skill directory after installation.
        return max(candidates, key=lambda item: item.stat().st_mtime)

    async def _run_skills_cli(
        self,
        args: list[str],
        timeout: int | None = None,
    ) -> tuple[str, str, int]:
        cmd = ["npx", "-y", *args]
        command_timeout = timeout or self.cli_timeout
        logger.info("running_skills_cli", command=" ".join(cmd), timeout=command_timeout)

        cwd = self.base_dir if Path(self.base_dir).exists() else None
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "skills CLI unavailable: `npx` was not found in PATH"
            ) from exc

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=command_timeout,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise TimeoutError(
                f"skills CLI command timed out after {command_timeout} seconds"
            ) from exc

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        return_code = process.returncode or 0
        logger.info(
            "skills_cli_completed",
            return_code=return_code,
            stdout_lines=len(stdout.splitlines()),
            stderr_lines=len(stderr.splitlines()),
        )
        return stdout, stderr, return_code

    def _read_skill_markdown(self, path: Path) -> tuple[dict[str, Any], str]:
        content = path.read_text(encoding="utf-8", errors="replace")
        return self._split_frontmatter(content)

    def _split_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        if not content.startswith("---\n"):
            return {}, content

        end_marker = "\n---\n"
        end_index = content.find(end_marker, 4)
        if end_index == -1:
            return {}, content

        metadata_raw = content[4:end_index]
        body = content[end_index + len(end_marker) :]

        try:
            loaded = yaml.safe_load(metadata_raw) or {}
        except yaml.YAMLError:
            loaded = {}
        metadata = loaded if isinstance(loaded, dict) else {}
        return metadata, body

    def _extract_section(self, markdown: str, section_name: str) -> str:
        target = section_name.strip().lstrip("#").strip().lower()
        if not target:
            raise ValueError("Section name cannot be empty")

        lines = markdown.splitlines()
        start_index: int | None = None
        start_level: int | None = None
        for index, line in enumerate(lines):
            match = self.SECTION_HEADER_RE.match(line)
            if not match:
                continue
            heading_text = match.group(2).strip().lower()
            if heading_text == target:
                start_index = index + 1
                start_level = len(match.group(1))
                break

        if start_index is None or start_level is None:
            raise ValueError(f"Section '{section_name}' not found in SKILL.md")

        collected: list[str] = []
        for line in lines[start_index:]:
            match = self.SECTION_HEADER_RE.match(line)
            if match and len(match.group(1)) <= start_level:
                break
            collected.append(line)

        section = "\n".join(collected).strip()
        return f"{section}\n" if section else ""

    def _list_relative_files(self, directory: Path) -> list[str]:
        if not directory.exists() or not directory.is_dir():
            return []
        return sorted(
            path.relative_to(directory).as_posix()
            for path in directory.rglob("*")
            if path.is_file()
        )

    def _extract_json_payload(self, raw_output: str) -> Any:
        stripped = raw_output.strip()
        if not stripped:
            raise ValueError("Failed to parse skills CLI JSON output: empty stdout")

        candidates = [stripped]
        bracket_start = stripped.find("[")
        bracket_end = stripped.rfind("]")
        if bracket_start != -1 and bracket_end > bracket_start:
            candidates.append(stripped[bracket_start : bracket_end + 1])

        brace_start = stripped.find("{")
        brace_end = stripped.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            candidates.append(stripped[brace_start : brace_end + 1])

        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        raise ValueError("Failed to parse skills CLI JSON output")

    def _extract_plaintext_search_results(self, raw_output: str) -> list[dict[str, Any]]:
        cleaned = self._strip_ansi(raw_output)
        entries: list[dict[str, Any]] = []

        for line in cleaned.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            match = self.PLAIN_SEARCH_LINE_RE.match(candidate)
            if not match:
                continue

            repo_skill = match.group("repo_skill")
            if "@" not in repo_skill:
                continue
            repo, name = repo_skill.rsplit("@", 1)
            if not repo or not name:
                continue

            installs = self._to_int(match.group("installs").replace(",", ""))
            entries.append(
                {
                    "name": name,
                    "repo": repo,
                    "description": "",
                    "installs": installs,
                }
            )

        return entries

    def _strip_ansi(self, text: str) -> str:
        return self.ANSI_ESCAPE_RE.sub("", text)

    def _is_within(self, target: Path, base: Path) -> bool:
        try:
            target.relative_to(base.resolve())
            return True
        except ValueError:
            return False

    def _is_network_error(self, message: str) -> bool:
        lowered = message.lower()
        markers = [
            "econnrefused",
            "econnreset",
            "enotfound",
            "network",
            "timed out",
            "timeout",
            "fetch failed",
            "unable to reach",
            "getaddrinfo",
            "egress",
        ]
        return any(marker in lowered for marker in markers)

    def _to_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
