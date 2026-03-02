"""Skills module registration."""

from __future__ import annotations

from fastapi import FastAPI

from anyide.modules.base import ToolModule
from anyide.modules.skills.schemas import (
    SkillsInstallRequest,
    SkillsInstallResponse,
    SkillsListResponse,
    SkillsReadFileRequest,
    SkillsReadFileResponse,
    SkillsReadRequest,
    SkillsReadResponse,
    SkillsSearchRequest,
    SkillsSearchResponse,
)
from anyide.modules.skills.tools import SkillsTools


_LIST_DESC = """List all installed skills from the isolated /skills directory.

This tool is offline-capable and only reads local files.
No workspace path resolution is used.

Use `skills_list` first before `skills_read` or `skills_read_file` so the model has a valid skill name."""

_READ_DESC = """Read a skill's SKILL.md content.

Use `skills_list` first, then call `skills_read` with `name`.
Compatibility aliases are accepted: `skill_id`, `skill_name`.

Optional `section` allows extracting a specific markdown section by header text."""

_READ_FILE_DESC = """Read a specific file inside an installed skill directory.

Use `skills_list` first and pass the selected skill as `name`
(compatibility aliases: `skill_id`, `skill_name`).

The provided `file_path` must be a relative path and resolve within the selected skill directory."""

_SEARCH_DESC = """Search available skills using the skills CLI registry.

Runs `npx skills find <query> --json` and parses structured results.
Requires outbound network access.

If remote search is unavailable, fall back to local workflows:
`skills_list` -> `skills_read` -> `skills_read_file`."""

_INSTALL_DESC = """Install a skill from a remote repository using the skills CLI.

Runs `npx skills add <repo> [--skill <name>] --global -y`.
Request body fields:
- `repo`: source repository (for example `vercel-labs/agent-skills`)
- `skill_name` (or alias `skill_id`): optional skill within that repo

This operation is HITL-gated by default because it downloads and executes external code."""


class SkillsModule(ToolModule):
    """Skill management tools."""

    MODULE_NAME = "skills"

    @property
    def name(self) -> str:
        return self.MODULE_NAME

    @property
    def display_name(self) -> str:
        return "Skills Tools"

    @property
    def description(self) -> str:
        return "Skill discovery, installation, and reading for AnyIDE"

    def __init__(self, context):
        super().__init__(context)
        self.skills_tools = SkillsTools(base_dir=context.config.skills.base_dir)
        self.context.register_dispatch_target("skills", self.skills_tools)

    def register_tools(self, app: FastAPI, sub_app: FastAPI) -> None:
        @app.post(
            "/api/tools/skills/list",
            operation_id="skills_list",
            summary="List Installed Skills",
            description=_LIST_DESC,
            response_model=SkillsListResponse,
            tags=["skills"],
        )
        async def skills_list_root() -> SkillsListResponse:
            return await self.context.execute_tool(
                "skills",
                "list",
                {},
                lambda: self.skills_tools.list(),
            )

        @sub_app.post(
            "/list",
            operation_id="skills_list",
            summary="List Installed Skills",
            description=_LIST_DESC,
            response_model=SkillsListResponse,
            tags=["skills"],
        )
        async def skills_list_sub() -> SkillsListResponse:
            return await self.context.execute_tool(
                "skills",
                "list",
                {},
                lambda: self.skills_tools.list(),
            )

        @app.post(
            "/api/tools/skills/read",
            operation_id="skills_read",
            summary="Read Skill File",
            description=_READ_DESC,
            response_model=SkillsReadResponse,
            tags=["skills"],
        )
        async def skills_read_root(request: SkillsReadRequest) -> SkillsReadResponse:
            return await self.context.execute_tool(
                "skills",
                "read",
                request.model_dump(),
                lambda: self.skills_tools.read(request),
            )

        @sub_app.post(
            "/read",
            operation_id="skills_read",
            summary="Read Skill File",
            description=_READ_DESC,
            response_model=SkillsReadResponse,
            tags=["skills"],
        )
        async def skills_read_sub(request: SkillsReadRequest) -> SkillsReadResponse:
            return await self.context.execute_tool(
                "skills",
                "read",
                request.model_dump(),
                lambda: self.skills_tools.read(request),
            )

        @app.post(
            "/api/tools/skills/read_file",
            operation_id="skills_read_file",
            summary="Read Skill Nested File",
            description=_READ_FILE_DESC,
            response_model=SkillsReadFileResponse,
            tags=["skills"],
        )
        async def skills_read_file_root(
            request: SkillsReadFileRequest,
        ) -> SkillsReadFileResponse:
            return await self.context.execute_tool(
                "skills",
                "read_file",
                request.model_dump(),
                lambda: self.skills_tools.read_file(request),
            )

        @sub_app.post(
            "/read_file",
            operation_id="skills_read_file",
            summary="Read Skill Nested File",
            description=_READ_FILE_DESC,
            response_model=SkillsReadFileResponse,
            tags=["skills"],
        )
        async def skills_read_file_sub(
            request: SkillsReadFileRequest,
        ) -> SkillsReadFileResponse:
            return await self.context.execute_tool(
                "skills",
                "read_file",
                request.model_dump(),
                lambda: self.skills_tools.read_file(request),
            )

        @app.post(
            "/api/tools/skills/search",
            operation_id="skills_search",
            summary="Search Skills Registry",
            description=_SEARCH_DESC,
            response_model=SkillsSearchResponse,
            tags=["skills"],
        )
        async def skills_search_root(request: SkillsSearchRequest) -> SkillsSearchResponse:
            return await self.context.execute_tool(
                "skills",
                "search",
                request.model_dump(),
                lambda: self.skills_tools.search(request),
            )

        @sub_app.post(
            "/search",
            operation_id="skills_search",
            summary="Search Skills Registry",
            description=_SEARCH_DESC,
            response_model=SkillsSearchResponse,
            tags=["skills"],
        )
        async def skills_search_sub(request: SkillsSearchRequest) -> SkillsSearchResponse:
            return await self.context.execute_tool(
                "skills",
                "search",
                request.model_dump(),
                lambda: self.skills_tools.search(request),
            )

        @app.post(
            "/api/tools/skills/install",
            operation_id="skills_install",
            summary="Install Skill",
            description=_INSTALL_DESC,
            response_model=SkillsInstallResponse,
            tags=["skills"],
        )
        async def skills_install_root(
            request: SkillsInstallRequest,
        ) -> SkillsInstallResponse:
            return await self.context.execute_tool(
                "skills",
                "install",
                request.model_dump(),
                lambda: self.skills_tools.install(request),
                force_hitl=True,
                hitl_reason="skills_install requires approval (downloads and executes code from the internet)",
            )

        @sub_app.post(
            "/install",
            operation_id="skills_install",
            summary="Install Skill",
            description=_INSTALL_DESC,
            response_model=SkillsInstallResponse,
            tags=["skills"],
        )
        async def skills_install_sub(
            request: SkillsInstallRequest,
        ) -> SkillsInstallResponse:
            return await self.context.execute_tool(
                "skills",
                "install",
                request.model_dump(),
                lambda: self.skills_tools.install(request),
                force_hitl=True,
                hitl_reason="skills_install requires approval (downloads and executes code from the internet)",
            )
