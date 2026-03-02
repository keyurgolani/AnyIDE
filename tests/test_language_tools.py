"""Tests for language module tools (tree-sitter-first phase)."""

from __future__ import annotations

from pathlib import Path

import pytest

from anyide.config import Config
from anyide.core.database import Database
from anyide.core.workspace import WorkspaceManager
from anyide.modules.language.schemas import (
    LangApplyPatchHunk,
    LangApplyPatchRequest,
    LangCreateFileRequest,
    LangDiffRequest,
    LangIndexRequest,
    LangReadFileRequest,
    LangReferenceGraphRequest,
    LangSearchSymbolsRequest,
    LangSkeletonRequest,
    LangValidateRequest,
)
from anyide.modules.language.tools import LanguageTools


@pytest.fixture
def temp_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    (workspace / "sample.py").write_text(
        "\n".join(
            [
                "import os",
                "from math import sqrt",
                "",
                "class Greeter:",
                "    def hello(self, name: str) -> str:",
                "        return build_message(name)",
                "",
                "def build_message(name: str) -> str:",
                "    return f'Hello {name}'",
                "",
                "def caller() -> str:",
                "    return build_message('team')",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "broken.py").write_text("def nope(:\n    pass\n", encoding="utf-8")
    return workspace


@pytest.fixture
async def language_tools(temp_workspace: Path, tmp_path: Path) -> LanguageTools:
    db = Database(str(tmp_path / "lang.db"))
    await db.connect()

    cfg = Config()
    cfg.workspace.base_dir = str(temp_workspace)

    tools = LanguageTools(
        workspace=WorkspaceManager(str(temp_workspace)),
        db=db,
        config=cfg,
    )
    tools.on_startup()

    try:
        yield tools
    finally:
        await db.close()


class TestLanguageReadAndSkeleton:
    async def test_lang_skeleton_signatures(self, language_tools: LanguageTools):
        response = await language_tools.skeleton(
            LangSkeletonRequest(paths=["sample.py"])
        )

        assert len(response.files) == 1
        symbol_names = {symbol.name for symbol in response.files[0].symbols}
        assert "Greeter" in symbol_names
        assert "build_message" in symbol_names

    async def test_lang_read_file_structural_window(self, language_tools: LanguageTools):
        response = await language_tools.read_file(
            LangReadFileRequest(
                path="sample.py",
                window="function:build_message",
                format="numbered",
            )
        )

        assert "build_message" in response.content
        assert "caller" not in response.content
        assert response.window_applied == "function:build_message"

    async def test_lang_read_import_window(self, language_tools: LanguageTools):
        response = await language_tools.read_file(
            LangReadFileRequest(path="sample.py", window="import:*", format="raw")
        )
        assert "import os" in response.content
        assert "from math import sqrt" in response.content
        assert "class Greeter" not in response.content


class TestLanguageEditFlow:
    async def test_lang_diff_function_anchored(self, language_tools: LanguageTools):
        new_content = (
            "import os\n"
            "from math import sqrt\n\n"
            "class Greeter:\n"
            "    def hello(self, name: str) -> str:\n"
            "        return build_message(name)\n\n"
            "def build_message(name: str) -> str:\n"
            "    return f'Hi {name}'\n\n"
            "def caller() -> str:\n"
            "    return build_message('team')\n"
        )

        response = await language_tools.diff(
            LangDiffRequest(path="sample.py", new_content=new_content)
        )

        assert response.hunks
        assert any(hunk.anchor == "function:build_message" for hunk in response.hunks)
        assert response.validation.syntax_valid is True

    async def test_lang_apply_patch_creates_backup(self, language_tools: LanguageTools):
        response = await language_tools.apply_patch(
            LangApplyPatchRequest(
                path="sample.py",
                hunks=[
                    LangApplyPatchHunk(
                        anchor="function:build_message",
                        old_content="return f'Hello {name}'",
                        new_content="return f'Welcome {name}'",
                    )
                ],
                validate=True,
                create_backup=True,
            )
        )

        assert response.applied_hunks == 1
        assert response.failed_hunks == []
        assert response.backup_path is not None
        assert Path(response.backup_path).exists()

    async def test_lang_create_file(self, language_tools: LanguageTools, temp_workspace: Path):
        response = await language_tools.create_file(
            LangCreateFileRequest(
                path="new_module.py",
                content="def add(a: int, b: int) -> int:\n    return a + b\n",
                validate=True,
            )
        )

        assert response.language == "python"
        assert response.validation.syntax_valid is True
        assert any(symbol.name == "add" for symbol in response.symbols_created)
        assert (temp_workspace / "new_module.py").exists()


class TestLanguageIndexAndValidation:
    async def test_lang_index_and_search(self, language_tools: LanguageTools):
        index_response = await language_tools.index(
            LangIndexRequest(force_reindex=True)
        )
        assert index_response.files_indexed >= 1
        assert index_response.symbols_indexed >= 1

        search_response = await language_tools.search_symbols(
            LangSearchSymbolsRequest(query="build_*", language="python")
        )
        assert search_response.results
        assert any(result.name == "build_message" for result in search_response.results)

    async def test_lang_reference_graph(self, language_tools: LanguageTools):
        response = await language_tools.reference_graph(
            LangReferenceGraphRequest(path="sample.py", scope="file")
        )
        assert any(node.name == "caller" for node in response.nodes)
        assert any(edge.target.endswith("build_message") for edge in response.edges)

    async def test_lang_validate_syntax_and_lint(self, language_tools: LanguageTools):
        syntax_ok = await language_tools.validate(
            LangValidateRequest(path="sample.py", checks=["syntax", "lint"])
        )
        assert syntax_ok.syntax.valid is True
        assert syntax_ok.lint.tool is not None

        syntax_bad = await language_tools.validate(
            LangValidateRequest(path="broken.py", checks=["syntax"])
        )
        assert syntax_bad.syntax.valid is False
        assert syntax_bad.syntax.errors
