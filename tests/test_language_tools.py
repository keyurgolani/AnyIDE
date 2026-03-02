"""Tests for language module tools (tree-sitter-first phase)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from anyide.config import Config
from anyide.core.database import Database
from anyide.core.workspace import WorkspaceManager
from anyide.modules.language.lsp_client import LSPDiagnostic, LSPLocation
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
    (workspace / "util.ts").write_text(
        "\n".join(
            [
                "export function helper(name: string): string {",
                "  return name.toUpperCase();",
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "app.ts").write_text(
        "\n".join(
            [
                'import { helper as utilHelper } from "./util";',
                "",
                "export function run(): string {",
                '  return utilHelper("team");',
                "}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return workspace


@pytest.fixture
async def language_tools(temp_workspace: Path, tmp_path: Path) -> LanguageTools:
    db = Database(str(tmp_path / "lang.db"))
    await db.connect()

    cfg = Config()
    cfg.workspace.base_dir = str(temp_workspace)
    cfg.language.lsp_servers = {}

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

    async def test_lang_validate_type_uses_lsp_for_python_and_typescript(
        self,
        language_tools: LanguageTools,
    ):
        class FakeLSPManager:
            def get_server_name(self, language: str) -> Optional[str]:
                return {
                    "python": "pyright",
                    "typescript": "typescript-language-server",
                }.get(language)

            async def diagnostics(
                self,
                language: str,
                file_path: str,
                content: str,
            ) -> list[LSPDiagnostic]:
                if language == "python":
                    return [
                        LSPDiagnostic(
                            line=8,
                            col=12,
                            message="Incompatible return type",
                            severity="error",
                        )
                    ]
                if language == "typescript":
                    return [
                        LSPDiagnostic(
                            line=4,
                            col=21,
                            message="Argument of type 'number' is not assignable to parameter of type 'string'",
                            severity="error",
                        )
                    ]
                return []

            async def references(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                return []

            async def hover(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> Optional[str]:
                return None

            async def definitions(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                return []

            async def shutdown(self) -> None:
                return None

        language_tools.lsp_manager = FakeLSPManager()

        python_result = await language_tools.validate(
            LangValidateRequest(path="sample.py", checks=["type"])
        )
        assert python_result.type_check.tool == "pyright"
        assert python_result.type_check.errors
        assert python_result.type_check.errors[0].message == "Incompatible return type"

        ts_result = await language_tools.validate(
            LangValidateRequest(path="app.ts", checks=["type"])
        )
        assert ts_result.type_check.tool == "typescript-language-server"
        assert ts_result.type_check.errors
        assert "not assignable" in ts_result.type_check.errors[0].message

    async def test_lang_reference_graph_adds_lsp_semantic_cross_file_edge(
        self,
        language_tools: LanguageTools,
        temp_workspace: Path,
    ):
        class FakeLSPManager:
            def get_server_name(self, language: str) -> Optional[str]:
                return {"typescript": "typescript-language-server"}.get(language)

            async def diagnostics(
                self,
                language: str,
                file_path: str,
                content: str,
            ) -> list[LSPDiagnostic]:
                return []

            async def references(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                if language == "typescript" and file_path.endswith("util.ts") and line == 1:
                    return [LSPLocation(path=str(temp_workspace / "app.ts"), line=4, col=10)]
                return []

            async def hover(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> Optional[str]:
                return None

            async def definitions(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                return []

            async def shutdown(self) -> None:
                return None

        language_tools.lsp_manager = FakeLSPManager()

        response = await language_tools.reference_graph(
            LangReferenceGraphRequest(path="app.ts", scope="workspace")
        )
        assert any(edge.source == "app.ts::run" and edge.target == "util.ts::helper" for edge in response.edges)

    async def test_lang_reference_graph_uses_definition_fallback_for_alias_call(
        self,
        language_tools: LanguageTools,
        temp_workspace: Path,
    ):
        class FakeLSPManager:
            def get_server_name(self, language: str) -> Optional[str]:
                return {"typescript": "typescript-language-server"}.get(language)

            async def diagnostics(
                self,
                language: str,
                file_path: str,
                content: str,
            ) -> list[LSPDiagnostic]:
                return []

            async def references(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                return []

            async def hover(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> Optional[str]:
                return None

            async def definitions(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                if language == "typescript" and file_path.endswith("app.ts") and line == 4:
                    return [LSPLocation(path=str(temp_workspace / "util.ts"), line=1, col=17)]
                return []

            async def shutdown(self) -> None:
                return None

        language_tools.lsp_manager = FakeLSPManager()

        response = await language_tools.reference_graph(
            LangReferenceGraphRequest(path="app.ts", scope="workspace")
        )
        assert any(edge.source == "app.ts::run" and edge.target == "util.ts::helper" for edge in response.edges)

    async def test_lang_read_file_returns_lsp_hover_and_definition_enrichment(
        self,
        language_tools: LanguageTools,
        temp_workspace: Path,
    ):
        class FakeLSPManager:
            def get_server_name(self, language: str) -> Optional[str]:
                return {"python": "pyright"}.get(language)

            async def diagnostics(
                self,
                language: str,
                file_path: str,
                content: str,
            ) -> list[LSPDiagnostic]:
                return []

            async def references(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                return []

            async def hover(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> Optional[str]:
                if language == "python" and line == 8:
                    return "def build_message(name: str) -> str"
                return None

            async def definitions(
                self,
                language: str,
                file_path: str,
                content: str,
                line: int,
                col: int,
            ) -> list[LSPLocation]:
                if language == "python" and line == 8:
                    return [LSPLocation(path=str(temp_workspace / "sample.py"), line=8, col=1)]
                return []

            async def shutdown(self) -> None:
                return None

        language_tools.lsp_manager = FakeLSPManager()

        response = await language_tools.read_file(
            LangReadFileRequest(path="sample.py", window="function:build_message", format="raw")
        )

        assert response.lsp_enrichments
        enrichment = response.lsp_enrichments[0]
        assert enrichment.symbol == "build_message"
        assert enrichment.hover == "def build_message(name: str) -> str"
        assert enrichment.definitions
        assert enrichment.definitions[0].file == "sample.py"
