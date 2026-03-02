"""Language-aware tooling (tree-sitter-first implementation)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Iterable, Optional

from anyide.config import Config
from anyide.core.database import Database
from anyide.core.workspace import WorkspaceManager
from anyide.logging_config import get_logger
from anyide.modules.language.schemas import (
    LangApplyPatchRequest,
    LangApplyPatchResponse,
    LangCreateFileRequest,
    LangCreateFileResponse,
    LangCreateFileValidation,
    LangDiffHunk,
    LangDiffRequest,
    LangDiffResponse,
    LangDiffValidation,
    LangIndexRequest,
    LangIndexResponse,
    LangLintIssue,
    LangParseError,
    LangPatchFailedHunk,
    LangPatchValidation,
    LangReadFileRequest,
    LangReadLspDefinition,
    LangReadLspEnrichment,
    LangReadFileResponse,
    LangReferenceCallSite,
    LangReferenceEdge,
    LangReferenceGraphRequest,
    LangReferenceGraphResponse,
    LangReferenceNode,
    LangSearchSymbolResult,
    LangSearchSymbolsRequest,
    LangSearchSymbolsResponse,
    LangSkeletonFile,
    LangSkeletonRequest,
    LangSkeletonResponse,
    LangSymbol,
    LangSymbolRef,
    LangTypeIssue,
    LangValidateLint,
    LangValidateRequest,
    LangValidateResponse,
    LangValidateSyntax,
    LangValidateTypeCheck,
)
from anyide.modules.language.lsp_client import LSPManager
from anyide.modules.language.treesitter import (
    EXTENSION_TO_LANGUAGE,
    ExtractedSymbol,
    ParseIssue,
    TreeSitterService,
)

logger = get_logger(__name__)

SKIP_INDEX_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    ".next",
    "target",
}


class LanguageTools:
    """Language-aware read/edit/index/validation tools."""

    def __init__(
        self,
        workspace: WorkspaceManager,
        db: Database,
        config: Config,
        tree_sitter: Optional[TreeSitterService] = None,
        lsp_manager: Optional[LSPManager] = None,
    ):
        self.workspace = workspace
        self.db = db
        self.config = config
        self.tree_sitter = tree_sitter or TreeSitterService()
        self.lsp_manager = lsp_manager or LSPManager(
            workspace_root=self.workspace.base_dir,
            lsp_servers=self._language_lsp_config(),
        )

    def on_startup(self) -> None:
        """Warm parser cache for common languages."""
        self.tree_sitter.on_startup()

    async def on_shutdown(self) -> None:
        """Lifecycle hook for symmetry with module contract."""
        await self.lsp_manager.shutdown()

    async def skeleton(self, request: LangSkeletonRequest) -> LangSkeletonResponse:
        """Return structural skeleton for one or more files."""
        workspace_root = self._resolve_workspace_root(request.workspace_dir)
        files: list[LangSkeletonFile] = []

        for resolved_path in self._expand_paths(
            patterns=request.paths,
            workspace_root=workspace_root,
            workspace_dir=request.workspace_dir,
        ):
            content = self._read_file(resolved_path)
            language = self._detect_language(resolved_path)
            symbols = self.tree_sitter.extract_symbols(
                content=content,
                language=language,
                depth=request.depth,
            )
            files.append(
                LangSkeletonFile(
                    path=resolved_path,
                    language=language,
                    symbols=[self._to_symbol_model(symbol) for symbol in symbols],
                )
            )

        return LangSkeletonResponse(files=files)

    async def read_file(self, request: LangReadFileRequest) -> LangReadFileResponse:
        """Read a source file with structure-aware windows and output formats."""
        workspace_root = self._resolve_workspace_root(request.workspace_dir)
        resolved_path = self._resolve_file(request.path, request.workspace_dir)
        language = self._detect_language(resolved_path)
        content = self._read_file(resolved_path)
        lines = content.splitlines(keepends=True)
        symbols = self.tree_sitter.extract_symbols(
            content=content,
            language=language,
            depth="full",
        )

        selected_text, applied_window, start_line, selected_symbols = self._apply_window(
            lines=lines,
            symbols=symbols,
            window=request.window,
            language=language,
        )

        if request.format == "skeleton":
            selected_content = self.tree_sitter.render_skeleton(selected_symbols)
            if selected_content:
                selected_content += "\n"
        elif request.format == "numbered":
            selected_content = self._number_lines(selected_text, start_line=start_line)
        else:
            selected_content = selected_text

        flat_symbols = self.tree_sitter.flatten_symbols(selected_symbols)
        lsp_enrichments = await self._build_read_file_lsp_enrichments(
            language=language,
            file_path=resolved_path,
            workspace_root=workspace_root,
            content=content,
            symbols=flat_symbols,
        )

        return LangReadFileResponse(
            path=resolved_path,
            language=language,
            total_lines=len(lines),
            content=selected_content,
            window_applied=applied_window,
            symbols_in_view=[
                self._to_symbol_ref(symbol)
                for symbol in flat_symbols
            ],
            lsp_enrichments=lsp_enrichments,
        )

    async def diff(self, request: LangDiffRequest) -> LangDiffResponse:
        """Generate function-anchored structural diffs with syntax validation."""
        resolved_path = self._resolve_file(request.path, request.workspace_dir)
        original = self._read_file(resolved_path)
        language = self._detect_language(resolved_path)

        parse_tree = self.tree_sitter.parse(request.new_content, language)
        issues = self.tree_sitter.collect_parse_issues(parse_tree)
        validation = LangDiffValidation(
            syntax_valid=len(issues) == 0,
            errors=[f"line {issue.line}:{issue.col} {issue.message}" for issue in issues],
        )

        hunks = self._build_function_anchored_hunks(
            original=original,
            proposed=request.new_content,
            language=language,
            requested_format=request.format,
        )
        summary = (
            f"{len(hunks)} hunk(s) generated in {request.format} format."
            if hunks
            else "No structural changes detected."
        )

        return LangDiffResponse(hunks=hunks, summary=summary, validation=validation)

    async def apply_patch(self, request: LangApplyPatchRequest) -> LangApplyPatchResponse:
        """Apply function-anchored patch hunks to a file."""
        resolved_path = self._resolve_file(request.path, request.workspace_dir)
        language = self._detect_language(resolved_path)
        original_content = self._read_file(resolved_path)
        updated_content = original_content

        backup_path: Optional[str] = None
        if request.create_backup:
            backup_path = f"{resolved_path}.bak.{int(time.time() * 1000)}"
            with open(backup_path, "w", encoding="utf-8") as handle:
                handle.write(original_content)

        applied_hunks = 0
        failed_hunks: list[LangPatchFailedHunk] = []

        for hunk in request.hunks:
            updated_content, applied, reason = self._apply_single_hunk(
                content=updated_content,
                language=language,
                anchor=hunk.anchor,
                old_content=hunk.old_content,
                new_content=hunk.new_content,
            )
            if applied:
                applied_hunks += 1
            else:
                failed_hunks.append(LangPatchFailedHunk(anchor=hunk.anchor, reason=reason))

        with open(resolved_path, "w", encoding="utf-8") as handle:
            handle.write(updated_content)

        if request.run_validation:
            validate_result = await self.validate(
                LangValidateRequest(
                    path=request.path,
                    workspace_dir=request.workspace_dir,
                    checks=["syntax", "lint", "type"],
                )
            )
            validation = LangPatchValidation(
                syntax_valid=validate_result.syntax.valid,
                lint_errors=validate_result.lint.errors,
                type_errors=validate_result.type_check.errors,
            )
        else:
            issues = self.tree_sitter.collect_parse_issues(
                self.tree_sitter.parse(updated_content, language)
            )
            validation = LangPatchValidation(
                syntax_valid=len(issues) == 0,
                lint_errors=[],
                type_errors=[],
            )

        return LangApplyPatchResponse(
            path=resolved_path,
            applied_hunks=applied_hunks,
            failed_hunks=failed_hunks,
            backup_path=backup_path,
            validation=validation,
        )

    async def create_file(self, request: LangCreateFileRequest) -> LangCreateFileResponse:
        """Create a code file with syntax/lint validation and symbol extraction."""
        resolved_path = self.workspace.resolve_path(request.path, request.workspace_dir)
        if os.path.exists(resolved_path):
            raise ValueError(f"File already exists: {request.path}")

        os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
        with open(resolved_path, "w", encoding="utf-8") as handle:
            handle.write(request.content)

        language = self._detect_language(resolved_path)
        symbols = self.tree_sitter.extract_symbols(request.content, language, depth="full")
        flat_symbols = self.tree_sitter.flatten_symbols(symbols)

        validation = LangCreateFileValidation(
            syntax_valid=True,
            parse_errors=[],
            lint_errors=[],
        )
        if request.run_validation:
            validate_result = await self.validate(
                LangValidateRequest(
                    path=request.path,
                    workspace_dir=request.workspace_dir,
                    checks=["syntax", "lint"],
                )
            )
            validation = LangCreateFileValidation(
                syntax_valid=validate_result.syntax.valid,
                parse_errors=[
                    LangParseError(line=issue.line, col=issue.col, message=issue.message)
                    for issue in validate_result.syntax.errors
                ],
                lint_errors=validate_result.lint.errors,
            )

        return LangCreateFileResponse(
            path=resolved_path,
            language=language,
            validation=validation,
            symbols_created=[self._to_symbol_ref(symbol) for symbol in flat_symbols],
        )

    async def index(self, request: LangIndexRequest) -> LangIndexResponse:
        """Index workspace files into persistent SQLite symbol tables."""
        start = time.time()
        workspace_root = self._resolve_workspace_root(request.workspace_dir)
        language_filter = set(request.languages or [])
        conn = self.db.connection

        if request.force_reindex:
            await conn.execute(
                "DELETE FROM language_index_symbols WHERE workspace_dir = ?",
                (workspace_root,),
            )
            await conn.execute(
                "DELETE FROM language_index_files WHERE workspace_dir = ?",
                (workspace_root,),
            )

        candidates = list(
            self._scan_source_files(
                workspace_root=workspace_root,
                language_filter=language_filter if language_filter else None,
            )
        )
        current_paths = {relative_path for _, relative_path, _ in candidates}

        cursor = await conn.execute(
            "SELECT path, mtime, size FROM language_index_files WHERE workspace_dir = ?",
            (workspace_root,),
        )
        rows = await cursor.fetchall()
        existing = {row["path"]: (row["mtime"], row["size"]) for row in rows}

        files_indexed = 0
        symbols_indexed = 0
        languages_detected: set[str] = set()

        for absolute_path, relative_path, language in candidates:
            stat = os.stat(absolute_path)
            mtime = float(stat.st_mtime)
            size = int(stat.st_size)
            previous = existing.get(relative_path)

            languages_detected.add(language)
            if (
                previous is not None
                and not request.force_reindex
                and abs(float(previous[0]) - mtime) < 1e-9
                and int(previous[1]) == size
            ):
                continue

            content = self._read_file(absolute_path)
            symbols = self.tree_sitter.extract_symbols(content, language, depth="full")
            flattened = self.tree_sitter.flatten_symbols(symbols)

            await conn.execute(
                """
                INSERT INTO language_index_files
                    (workspace_dir, path, language, mtime, size, indexed_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(workspace_dir, path) DO UPDATE SET
                    language = excluded.language,
                    mtime = excluded.mtime,
                    size = excluded.size,
                    indexed_at = excluded.indexed_at
                """,
                (workspace_root, relative_path, language, mtime, size),
            )
            await conn.execute(
                "DELETE FROM language_index_symbols WHERE workspace_dir = ? AND file_path = ?",
                (workspace_root, relative_path),
            )
            for symbol, parent_name in self._flatten_with_parent(symbols):
                await conn.execute(
                    """
                    INSERT INTO language_index_symbols
                        (workspace_dir, file_path, language, name, kind, signature, start_line, end_line, parent_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        workspace_root,
                        relative_path,
                        language,
                        symbol.name,
                        symbol.kind,
                        symbol.signature,
                        symbol.start_line,
                        symbol.end_line,
                        parent_name,
                    ),
                )

            files_indexed += 1
            symbols_indexed += len(flattened)

        stale_paths = [path for path in existing.keys() if path not in current_paths]
        for stale in stale_paths:
            await conn.execute(
                "DELETE FROM language_index_symbols WHERE workspace_dir = ? AND file_path = ?",
                (workspace_root, stale),
            )
            await conn.execute(
                "DELETE FROM language_index_files WHERE workspace_dir = ? AND path = ?",
                (workspace_root, stale),
            )

        await conn.commit()

        cursor = await conn.execute(
            """
            SELECT COALESCE(SUM(LENGTH(name) + LENGTH(signature) + 24), 0) AS bytes
            FROM language_index_symbols
            WHERE workspace_dir = ?
            """,
            (workspace_root,),
        )
        row = await cursor.fetchone()
        index_size = int(row["bytes"]) if row and row["bytes"] is not None else 0

        return LangIndexResponse(
            files_indexed=files_indexed,
            symbols_indexed=symbols_indexed,
            languages_detected=sorted(languages_detected),
            index_time_ms=int((time.time() - start) * 1000),
            index_size_bytes=index_size,
        )

    async def search_symbols(self, request: LangSearchSymbolsRequest) -> LangSearchSymbolsResponse:
        """Search indexed symbols."""
        workspace_root = self._resolve_workspace_root(request.workspace_dir)
        conn = self.db.connection

        pattern = request.query.replace("*", "%")
        if "%" not in pattern:
            pattern = f"%{pattern}%"

        where = ["workspace_dir = ?", "name LIKE ?"]
        params: list[object] = [workspace_root, pattern]

        if request.kind:
            where.append("kind = ?")
            params.append(request.kind)
        if request.language:
            where.append("language = ?")
            params.append(request.language)

        params.append(request.max_results)
        cursor = await conn.execute(
            f"""
            SELECT name, kind, file_path, start_line, end_line, signature, language
            FROM language_index_symbols
            WHERE {" AND ".join(where)}
            ORDER BY name ASC, file_path ASC
            LIMIT ?
            """,
            tuple(params),
        )
        rows = await cursor.fetchall()

        return LangSearchSymbolsResponse(
            results=[
                LangSearchSymbolResult(
                    name=row["name"],
                    kind=row["kind"],
                    file=row["file_path"],
                    start_line=row["start_line"],
                    end_line=row["end_line"],
                    signature=row["signature"],
                    language=row["language"],
                )
                for row in rows
            ]
        )

    async def reference_graph(
        self, request: LangReferenceGraphRequest
    ) -> LangReferenceGraphResponse:
        """Build a call reference graph with tree-sitter baseline and LSP enrichment."""
        workspace_root = self._resolve_workspace_root(request.workspace_dir)

        if request.scope == "file":
            target_path = self._resolve_file(request.path, request.workspace_dir)
            files = [(target_path, os.path.relpath(target_path, workspace_root))]
        else:
            files = [
                (absolute_path, relative_path)
                for absolute_path, relative_path, _ in self._scan_source_files(
                    workspace_root=workspace_root
                )
            ]

        nodes: dict[str, LangReferenceNode] = {}
        name_to_node_ids: dict[str, list[str]] = {}
        call_records: list[tuple[str, str, list[tuple[str, int, int]]]] = []
        symbol_positions: dict[str, tuple[str, int, int, str, str]] = {}
        node_spans_by_file: dict[str, list[tuple[int, int, str]]] = {}
        file_context: dict[str, tuple[str, str, str]] = {}

        for absolute_path, relative_path in files:
            content = self._read_file(absolute_path)
            language = self._detect_language(absolute_path)
            file_context[relative_path] = (absolute_path, content, language)
            symbols = self.tree_sitter.extract_symbols(content, language, depth="full")

            for symbol, parent_name in self._flatten_with_parent(symbols):
                if symbol.kind not in {"function", "method", "class"}:
                    continue
                qualified_name = (
                    f"{parent_name}.{symbol.name}"
                    if symbol.kind == "method" and parent_name
                    else symbol.name
                )
                node_id = f"{relative_path}::{qualified_name}"
                node = LangReferenceNode(
                    id=node_id,
                    name=qualified_name if symbol.kind == "method" else symbol.name,
                    kind=symbol.kind,
                    file=relative_path,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )
                nodes[node_id] = node
                name_to_node_ids.setdefault(symbol.name, []).append(node_id)
                node_spans_by_file.setdefault(relative_path, []).append(
                    (symbol.start_line, symbol.end_line, node_id)
                )
                symbol_positions[node_id] = (
                    absolute_path,
                    symbol.start_line,
                    symbol.start_col,
                    content,
                    language,
                )

                calls = self.tree_sitter.extract_calls(
                    content=content,
                    language=language,
                    start_line=symbol.start_line,
                    end_line=symbol.end_line,
                )
                call_records.append(
                    (
                        node_id,
                        relative_path,
                        [(call.name, call.line, call.col) for call in calls],
                    )
                )

        edge_index: dict[tuple[str, str], set[tuple[str, int]]] = {}
        for source_id, source_file, calls in call_records:
            for called_name, line_number, _col_number in calls:
                target_ids = name_to_node_ids.get(called_name, [])
                for target_id in target_ids:
                    if target_id == source_id:
                        continue
                    edge_index.setdefault((source_id, target_id), set()).add(
                        (source_file, line_number)
                    )

        await self._collect_lsp_reference_edges(
            edge_index=edge_index,
            symbol_positions=symbol_positions,
            node_spans_by_file=node_spans_by_file,
            call_records=call_records,
            file_context=file_context,
            workspace_root=workspace_root,
        )

        edges: list[LangReferenceEdge] = []
        for (source_id, target_id), call_sites in edge_index.items():
            edges.append(
                LangReferenceEdge(
                    source=source_id,
                    target=target_id,
                    call_sites=[
                        LangReferenceCallSite(file=file_path, line=line_no)
                        for file_path, line_no in sorted(call_sites)
                    ],
                )
            )

        if request.target_symbol:
            focus_nodes = {
                node_id
                for node_id, node in nodes.items()
                if node.name == request.target_symbol
                or node.id.endswith(f"::{request.target_symbol}")
                or node.id.endswith(f".{request.target_symbol}")
            }
            filtered_edges = [
                edge
                for edge in edges
                if edge.source in focus_nodes or edge.target in focus_nodes
            ]
            referenced_nodes = {
                edge.source for edge in filtered_edges
            } | {edge.target for edge in filtered_edges} | focus_nodes
            nodes = {node_id: node for node_id, node in nodes.items() if node_id in referenced_nodes}
            edges = filtered_edges

        return LangReferenceGraphResponse(
            nodes=sorted(nodes.values(), key=lambda node: node.id),
            edges=sorted(edges, key=lambda edge: (edge.source, edge.target)),
        )

    async def validate(self, request: LangValidateRequest) -> LangValidateResponse:
        """Validate source file with syntax + linter checks."""
        resolved_path = self._resolve_file(request.path, request.workspace_dir)
        language = self._detect_language(resolved_path)
        content = self._read_file(resolved_path)
        checks = set(request.checks)

        syntax_errors: list[LangParseError] = []
        syntax_valid = True
        if "syntax" in checks:
            parse_issues = self.tree_sitter.collect_parse_issues(
                self.tree_sitter.parse(content, language)
            )
            syntax_errors = [self._to_parse_error(issue) for issue in parse_issues]
            syntax_valid = len(syntax_errors) == 0

        lint_result = LangValidateLint(tool=None, errors=[])
        if "lint" in checks:
            lint_result = await self._run_linter(language=language, file_path=resolved_path)

        type_result = LangValidateTypeCheck(tool=None, errors=[])
        if "type" in checks:
            tool_name = self.lsp_manager.get_server_name(language)
            type_errors: list[LangTypeIssue] = []
            if tool_name:
                diagnostics = await self.lsp_manager.diagnostics(
                    language=language,
                    file_path=resolved_path,
                    content=content,
                )
                type_errors = [
                    LangTypeIssue(
                        line=diagnostic.line,
                        col=diagnostic.col,
                        message=diagnostic.message,
                        severity=diagnostic.severity,
                    )
                    for diagnostic in diagnostics
                ]
            type_result = LangValidateTypeCheck(tool=tool_name, errors=type_errors)

        return LangValidateResponse(
            path=resolved_path,
            language=language,
            syntax=LangValidateSyntax(valid=syntax_valid, errors=syntax_errors),
            lint=lint_result,
            type_check=type_result,
        )

    def _language_lsp_config(self) -> dict[str, str]:
        language_cfg = getattr(self.config, "language", object())
        raw = getattr(language_cfg, "lsp_servers", {})
        if not isinstance(raw, dict):
            return {}
        return {
            str(language): str(command)
            for language, command in raw.items()
            if str(command).strip()
        }

    async def _build_read_file_lsp_enrichments(
        self,
        language: str,
        file_path: str,
        workspace_root: str,
        content: str,
        symbols: list[ExtractedSymbol],
    ) -> list[LangReadLspEnrichment]:
        if not symbols:
            return []
        if self.lsp_manager.get_server_name(language) is None:
            return []

        enrichments: list[LangReadLspEnrichment] = []
        for symbol in symbols:
            hover = await self.lsp_manager.hover(
                language=language,
                file_path=file_path,
                content=content,
                line=symbol.start_line,
                col=symbol.start_col,
            )
            definitions = await self.lsp_manager.definitions(
                language=language,
                file_path=file_path,
                content=content,
                line=symbol.start_line,
                col=symbol.start_col,
            )

            definition_models: list[LangReadLspDefinition] = []
            seen_definitions: set[tuple[str, int, int]] = set()
            for location in definitions:
                rel_path = self._relative_path_if_within_workspace(
                    location.path,
                    workspace_root,
                )
                rendered_path = rel_path or location.path
                key = (rendered_path, location.line, location.col)
                if key in seen_definitions:
                    continue
                seen_definitions.add(key)
                definition_models.append(
                    LangReadLspDefinition(
                        file=rendered_path,
                        line=location.line,
                        col=location.col,
                    )
                )

            if hover or definition_models:
                enrichments.append(
                    LangReadLspEnrichment(
                        symbol=symbol.name,
                        line=symbol.start_line,
                        hover=hover,
                        definitions=definition_models,
                    )
                )

        return enrichments

    async def _collect_lsp_reference_edges(
        self,
        edge_index: dict[tuple[str, str], set[tuple[str, int]]],
        symbol_positions: dict[str, tuple[str, int, int, str, str]],
        node_spans_by_file: dict[str, list[tuple[int, int, str]]],
        call_records: list[tuple[str, str, list[tuple[str, int, int]]]],
        file_context: dict[str, tuple[str, str, str]],
        workspace_root: str,
    ) -> None:
        for callee_node_id, (
            file_path,
            line,
            col,
            content,
            language,
        ) in symbol_positions.items():
            if language not in {"javascript", "typescript"}:
                continue
            if self.lsp_manager.get_server_name(language) is None:
                continue

            references = await self.lsp_manager.references(
                language=language,
                file_path=file_path,
                content=content,
                line=line,
                col=col,
            )
            for ref in references:
                reference_file = self._relative_path_if_within_workspace(
                    ref.path,
                    workspace_root,
                )
                if reference_file is None:
                    continue
                caller_node_id = self._node_for_call_site(
                    node_spans_by_file.get(reference_file, []),
                    ref.line,
                )
                if caller_node_id is None or caller_node_id == callee_node_id:
                    continue

                edge_index.setdefault((caller_node_id, callee_node_id), set()).add(
                    (reference_file, ref.line)
                )

        # Some servers (notably TS in common configs) are better at call-site definition
        # resolution than declaration-reference fanout. Use definition fallback for
        # unresolved call sites to recover semantic cross-file edges.
        for source_node_id, source_file, calls in call_records:
            context = file_context.get(source_file)
            if context is None:
                continue
            source_path, source_content, source_language = context
            if source_language not in {"javascript", "typescript"}:
                continue
            if self.lsp_manager.get_server_name(source_language) is None:
                continue

            resolved_call_lines = {
                call_line
                for (edge_source, _edge_target), call_sites in edge_index.items()
                if edge_source == source_node_id
                for call_file, call_line in call_sites
                if call_file == source_file
            }

            for _call_name, call_line, call_col in calls:
                if call_line in resolved_call_lines:
                    continue

                definitions = await self.lsp_manager.definitions(
                    language=source_language,
                    file_path=source_path,
                    content=source_content,
                    line=call_line,
                    col=call_col,
                )
                target_node_id: Optional[str] = None
                for definition in definitions:
                    definition_file = self._relative_path_if_within_workspace(
                        definition.path,
                        workspace_root,
                    )
                    if definition_file is None:
                        continue
                    candidate = self._node_for_call_site(
                        node_spans_by_file.get(definition_file, []),
                        definition.line,
                    )
                    if candidate is None or candidate == source_node_id:
                        continue
                    target_node_id = candidate
                    break

                if target_node_id is None:
                    continue

                edge_index.setdefault((source_node_id, target_node_id), set()).add(
                    (source_file, call_line)
                )
                resolved_call_lines.add(call_line)

    @staticmethod
    def _node_for_call_site(
        spans: list[tuple[int, int, str]],
        line_number: int,
    ) -> Optional[str]:
        matches = [
            (end_line - start_line, node_id)
            for start_line, end_line, node_id in spans
            if start_line <= line_number <= end_line
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: item[0])
        return matches[0][1]

    @staticmethod
    def _relative_path_if_within_workspace(
        path: str,
        workspace_root: str,
    ) -> Optional[str]:
        resolved = os.path.realpath(path)
        workspace = os.path.realpath(workspace_root)
        if resolved == workspace:
            return "."
        if resolved.startswith(workspace + os.sep):
            return os.path.relpath(resolved, workspace)
        return None

    def _resolve_workspace_root(self, workspace_dir: Optional[str]) -> str:
        return self.workspace.resolve_path(".", workspace_dir)

    def _resolve_file(self, path: str, workspace_dir: Optional[str]) -> str:
        resolved = self.workspace.resolve_path(path, workspace_dir)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"File not found: {path}")
        if not os.path.isfile(resolved):
            raise ValueError(f"Path is not a file: {path}")
        return resolved

    def _detect_language(self, path: str) -> str:
        return self.tree_sitter.detect_language(path)

    @staticmethod
    def _read_file(path: str) -> str:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _expand_paths(
        self,
        patterns: Iterable[str],
        workspace_root: str,
        workspace_dir: Optional[str],
    ) -> list[str]:
        resolved: set[str] = set()
        for pattern in patterns:
            if any(token in pattern for token in ("*", "?", "[")):
                glob_root = Path(workspace_root)
                for candidate in glob_root.glob(pattern):
                    if not candidate.is_file():
                        continue
                    candidate_path = os.path.realpath(str(candidate))
                    if self.workspace.is_within_workspace(candidate_path):
                        resolved.add(candidate_path)
                continue

            candidate_path = self.workspace.resolve_path(pattern, workspace_dir)
            if os.path.isfile(candidate_path):
                resolved.add(candidate_path)
            else:
                raise FileNotFoundError(f"File not found for pattern path: {pattern}")
        return sorted(resolved)

    def _apply_window(
        self,
        lines: list[str],
        symbols: list[ExtractedSymbol],
        window: Optional[str],
        language: str,
    ) -> tuple[str, Optional[str], int, list[ExtractedSymbol]]:
        total_lines = len(lines)
        if not window:
            return ("".join(lines), None, 1, symbols)

        if window.startswith("lines:"):
            window = window[6:]

        if re.match(r"^\d+\s*-\s*\d+$", window):
            start, end = [int(part.strip()) for part in window.split("-", maxsplit=1)]
            if start < 1 or end < start or end > max(total_lines, 1):
                raise ValueError(f"Invalid line window '{window}' for file with {total_lines} lines")
            selected = "".join(lines[start - 1 : end])
            selected_symbols = self._symbols_overlapping(symbols, start, end)
            return (selected, f"lines:{start}-{end}", start, selected_symbols)

        flat = self.tree_sitter.flatten_symbols(symbols)

        if window == "import:*":
            imports = [symbol for symbol in flat if symbol.kind == "import"]
            if not imports:
                return ("", "import:*", 1, [])
            fragments = [
                "".join(lines[symbol.start_line - 1 : symbol.end_line]) for symbol in imports
            ]
            start_line = min(symbol.start_line for symbol in imports)
            return ("".join(fragments), "import:*", start_line, imports)

        if window.startswith("function:"):
            target = window[len("function:") :].strip()
            symbol = next(
                (
                    item
                    for item in flat
                    if item.kind in {"function", "method"} and item.name == target
                ),
                None,
            )
            if symbol is None:
                raise ValueError(f"Function window target not found: '{target}'")
            selected = "".join(lines[symbol.start_line - 1 : symbol.end_line])
            return (selected, f"function:{target}", symbol.start_line, [symbol])

        if window.startswith("class:"):
            target = window[len("class:") :].strip()
            if "." in target:
                class_name, method_name = target.split(".", maxsplit=1)
                class_symbol = next(
                    (item for item in symbols if item.kind == "class" and item.name == class_name),
                    None,
                )
                if class_symbol is None:
                    raise ValueError(f"Class window target not found: '{class_name}'")
                method_symbol = next(
                    (item for item in class_symbol.children if item.name == method_name),
                    None,
                )
                if method_symbol is None:
                    raise ValueError(
                        f"Method window target not found: '{class_name}.{method_name}'"
                    )
                selected = "".join(
                    lines[method_symbol.start_line - 1 : method_symbol.end_line]
                )
                return (
                    selected,
                    f"class:{class_name}.{method_name}",
                    method_symbol.start_line,
                    [method_symbol],
                )

            class_symbol = next(
                (item for item in symbols if item.kind == "class" and item.name == target),
                None,
            )
            if class_symbol is None:
                raise ValueError(f"Class window target not found: '{target}'")
            selected = "".join(lines[class_symbol.start_line - 1 : class_symbol.end_line])
            return (selected, f"class:{target}", class_symbol.start_line, [class_symbol])

        raise ValueError(
            f"Unsupported window target '{window}'. Use lines:<start-end>, function:<name>, class:<name>[.<method>], or import:*."
        )

    @staticmethod
    def _number_lines(content: str, start_line: int) -> str:
        raw_lines = content.splitlines()
        numbered = [
            f"{index:4d}: {line}" for index, line in enumerate(raw_lines, start=start_line)
        ]
        output = "\n".join(numbered)
        if content.endswith("\n"):
            output += "\n"
        return output

    def _symbols_overlapping(
        self, symbols: list[ExtractedSymbol], start_line: int, end_line: int
    ) -> list[ExtractedSymbol]:
        matches: list[ExtractedSymbol] = []
        for symbol in self.tree_sitter.flatten_symbols(symbols):
            if symbol.end_line < start_line or symbol.start_line > end_line:
                continue
            matches.append(symbol)
        return matches

    def _build_function_anchored_hunks(
        self,
        original: str,
        proposed: str,
        language: str,
        requested_format: str,
    ) -> list[LangDiffHunk]:
        original_lines = original.splitlines(keepends=True)
        proposed_lines = proposed.splitlines(keepends=True)
        original_symbols = self.tree_sitter.extract_symbols(original, language, depth="full")
        proposed_symbols = self.tree_sitter.extract_symbols(proposed, language, depth="full")

        old_map = {
            self._symbol_key(symbol, parent): (symbol, parent)
            for symbol, parent in self._flatten_with_parent(original_symbols)
            if symbol.kind in {"function", "class", "method"}
        }
        new_map = {
            self._symbol_key(symbol, parent): (symbol, parent)
            for symbol, parent in self._flatten_with_parent(proposed_symbols)
            if symbol.kind in {"function", "class", "method"}
        }

        keys = sorted(set(old_map.keys()) | set(new_map.keys()))
        hunks: list[LangDiffHunk] = []

        for key in keys:
            old_entry = old_map.get(key)
            new_entry = new_map.get(key)

            old_symbol = old_entry[0] if old_entry else None
            new_symbol = new_entry[0] if new_entry else None
            anchor = self._anchor_for_symbol(
                symbol=old_symbol or new_symbol,
                parent_name=(old_entry or new_entry)[1] if (old_entry or new_entry) else None,
            )
            anchor_signature = (old_symbol or new_symbol).signature if (old_symbol or new_symbol) else "file_level"
            anchor_line = (
                old_symbol.start_line
                if old_symbol is not None
                else (new_symbol.start_line if new_symbol is not None else 1)
            )

            old_text = (
                "".join(original_lines[old_symbol.start_line - 1 : old_symbol.end_line])
                if old_symbol is not None
                else ""
            )
            new_text = (
                "".join(proposed_lines[new_symbol.start_line - 1 : new_symbol.end_line])
                if new_symbol is not None
                else ""
            )
            if old_text == new_text:
                continue

            context_before = ""
            context_after = ""
            if old_symbol is not None:
                context_before = "".join(
                    original_lines[max(0, old_symbol.start_line - 4) : old_symbol.start_line - 1]
                )
                context_after = "".join(
                    original_lines[old_symbol.end_line : old_symbol.end_line + 3]
                )

            hunks.append(
                LangDiffHunk(
                    anchor=anchor,
                    anchor_signature=anchor_signature,
                    anchor_file_line=anchor_line,
                    old_content=old_text,
                    new_content=new_text,
                    context_before=context_before,
                    context_after=context_after,
                )
            )

        if not hunks and original != proposed:
            hunks.append(
                LangDiffHunk(
                    anchor="file_level",
                    anchor_signature="file_level",
                    anchor_file_line=1,
                    old_content=original,
                    new_content=proposed,
                    context_before="",
                    context_after="",
                )
            )

        if requested_format == "unified":
            return hunks[:1] if hunks else []
        return hunks

    def _apply_single_hunk(
        self,
        content: str,
        language: str,
        anchor: str,
        old_content: str,
        new_content: str,
    ) -> tuple[str, bool, str]:
        if old_content == new_content:
            return content, True, ""

        lines = content.splitlines(keepends=True)
        anchor_range = self._find_anchor_range(content, language, anchor)
        if anchor_range is not None:
            start_line, end_line = anchor_range
            segment = "".join(lines[start_line - 1 : end_line])
            if old_content in segment:
                replaced = segment.replace(old_content, new_content, 1)
                updated = (
                    "".join(lines[: start_line - 1])
                    + replaced
                    + "".join(lines[end_line:])
                )
                return updated, True, ""

        if old_content in content:
            return content.replace(old_content, new_content, 1), True, ""

        normalized_old = self._normalize_whitespace(old_content)
        if normalized_old:
            window_size = max(1, len(old_content.splitlines()))
            plain_lines = content.splitlines(keepends=True)
            for index in range(0, len(plain_lines)):
                for extra in (0, 1, 2):
                    end = index + window_size + extra
                    if end > len(plain_lines):
                        continue
                    candidate = "".join(plain_lines[index:end])
                    if self._normalize_whitespace(candidate) == normalized_old:
                        updated = (
                            "".join(plain_lines[:index])
                            + new_content
                            + "".join(plain_lines[end:])
                        )
                        return updated, True, ""

        return content, False, "Failed to match old_content in anchor scope or fallback text search"

    def _find_anchor_range(
        self, content: str, language: str, anchor: str
    ) -> Optional[tuple[int, int]]:
        symbols = self.tree_sitter.extract_symbols(content, language, depth="full")
        for symbol, parent_name in self._flatten_with_parent(symbols):
            if self._anchor_for_symbol(symbol, parent_name) == anchor:
                return (symbol.start_line, symbol.end_line)
        return None

    def _scan_source_files(
        self,
        workspace_root: str,
        language_filter: Optional[set[str]] = None,
    ) -> Iterable[tuple[str, str, str]]:
        for current_root, dirs, files in os.walk(workspace_root):
            dirs[:] = [name for name in dirs if name not in SKIP_INDEX_DIRS]
            for file_name in files:
                full_path = os.path.join(current_root, file_name)
                extension = Path(file_name).suffix.lower()
                language = EXTENSION_TO_LANGUAGE.get(extension)
                if language is None:
                    continue
                if language_filter and language not in language_filter:
                    continue
                relative_path = os.path.relpath(full_path, workspace_root)
                yield (full_path, relative_path, language)

    async def _run_linter(self, language: str, file_path: str) -> LangValidateLint:
        linters = getattr(getattr(self.config, "language", object()), "linters", {})
        configured_linter = None
        if isinstance(linters, dict):
            configured_linter = linters.get(language)
        if configured_linter is None and language == "python":
            configured_linter = "ruff"

        if configured_linter is None:
            return LangValidateLint(tool=None, errors=[])

        if configured_linter != "ruff":
            return LangValidateLint(
                tool=configured_linter,
                errors=[
                    LangLintIssue(
                        line=1,
                        col=1,
                        message=(
                            f"Linter '{configured_linter}' is configured for '{language}' but parsing is not implemented yet."
                        ),
                        severity="warning",
                    )
                ],
            )

        command = [configured_linter, "check", "--output-format", "json", file_path]
        try:
            completed = await asyncio.to_thread(
                __import__("subprocess").run,
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return LangValidateLint(
                tool="ruff",
                errors=[
                    LangLintIssue(
                        line=1,
                        col=1,
                        message="ruff is not installed in runtime environment",
                        severity="error",
                    )
                ],
            )

        issues: list[LangLintIssue] = []
        stdout = (completed.stdout or "").strip()
        if stdout:
            try:
                parsed = json.loads(stdout)
                for item in parsed:
                    location = item.get("location", {})
                    issues.append(
                        LangLintIssue(
                            line=int(location.get("row", 1)),
                            col=int(location.get("column", 1)),
                            message=item.get("message", "lint issue"),
                            rule=item.get("code"),
                            severity="error",
                            fix_available=bool(item.get("fix")),
                        )
                    )
            except json.JSONDecodeError:
                issues.append(
                    LangLintIssue(
                        line=1,
                        col=1,
                        message=f"Unable to parse ruff JSON output: {stdout[:200]}",
                        severity="error",
                    )
                )

        if completed.returncode not in (0, 1):
            stderr = (completed.stderr or "").strip() or "ruff command failed"
            issues.append(
                LangLintIssue(
                    line=1,
                    col=1,
                    message=stderr,
                    severity="error",
                )
            )

        return LangValidateLint(tool="ruff", errors=issues)

    @staticmethod
    def _normalize_whitespace(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def _to_symbol_model(symbol: ExtractedSymbol) -> LangSymbol:
        return LangSymbol(
            name=symbol.name,
            kind=symbol.kind,
            signature=symbol.signature,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
            children=[LanguageTools._to_symbol_ref(child) for child in symbol.children],
        )

    @staticmethod
    def _to_symbol_ref(symbol: ExtractedSymbol) -> LangSymbolRef:
        return LangSymbolRef(
            name=symbol.name,
            kind=symbol.kind,
            start_line=symbol.start_line,
            end_line=symbol.end_line,
        )

    @staticmethod
    def _to_parse_error(issue: ParseIssue) -> LangParseError:
        return LangParseError(line=issue.line, col=issue.col, message=issue.message)

    def _flatten_with_parent(
        self,
        symbols: list[ExtractedSymbol],
        parent_name: Optional[str] = None,
    ) -> list[tuple[ExtractedSymbol, Optional[str]]]:
        flat: list[tuple[ExtractedSymbol, Optional[str]]] = []
        for symbol in symbols:
            flat.append((symbol, parent_name))
            next_parent = symbol.name if symbol.kind == "class" else parent_name
            for child, child_parent in self._flatten_with_parent(symbol.children, next_parent):
                flat.append((child, child_parent))
        return flat

    @staticmethod
    def _symbol_key(symbol: ExtractedSymbol, parent_name: Optional[str]) -> str:
        if symbol.kind == "method" and parent_name:
            return f"method:{parent_name}.{symbol.name}"
        return f"{symbol.kind}:{symbol.name}"

    @staticmethod
    def _anchor_for_symbol(symbol: ExtractedSymbol, parent_name: Optional[str]) -> str:
        if symbol.kind == "method" and parent_name:
            return f"class:{parent_name}.{symbol.name}"
        if symbol.kind == "class":
            return f"class:{symbol.name}"
        return f"function:{symbol.name}"
