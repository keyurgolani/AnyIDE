"""Tree-sitter helpers and symbol extraction for language tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

try:
    from tree_sitter import Node, Tree
    from tree_sitter_language_pack import get_parser
except ImportError:  # pragma: no cover - dependency/packaging failure path
    Node = None  # type: ignore[assignment]
    Tree = None  # type: ignore[assignment]
    get_parser = None  # type: ignore[assignment]


EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".cs": "csharp",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".mjs": "javascript",
    ".mts": "typescript",
}


CLASS_NODE_TYPES = {
    "class_definition",
    "class_declaration",
    "class_specifier",
    "struct_specifier",
    "interface_declaration",
}
FUNCTION_NODE_TYPES = {
    "function_definition",
    "function_declaration",
    "function_item",
    "method_definition",
    "method_declaration",
    "constructor_declaration",
    "arrow_function",
}
METHOD_NODE_TYPES = {"method_definition", "method_declaration", "constructor_declaration"}
IMPORT_NODE_TYPES = {
    "import_statement",
    "import_from_statement",
    "import_declaration",
    "using_declaration",
    "preproc_include",
}
VARIABLE_NODE_TYPES = {
    "assignment",
    "lexical_declaration",
    "variable_declaration",
    "const_declaration",
    "let_declaration",
}
TYPE_NODE_TYPES = {
    "type_alias_declaration",
    "interface_declaration",
    "enum_declaration",
}
CALL_NODE_TYPES = {"call", "call_expression", "invocation_expression"}
IDENTIFIER_NODE_TYPES = {
    "identifier",
    "property_identifier",
    "field_identifier",
    "type_identifier",
}


@dataclass
class ExtractedSymbol:
    """Symbol extracted from a parsed file."""

    name: str
    kind: str
    signature: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    start_byte: int
    end_byte: int
    children: list["ExtractedSymbol"] = field(default_factory=list)


@dataclass
class ParseIssue:
    """Syntax parse issue with position."""

    line: int
    col: int
    message: str


@dataclass
class CallSite:
    """Call-site metadata for reference graph generation."""

    name: str
    line: int


class TreeSitterService:
    """Parser cache and extraction helpers backed by tree-sitter-language-pack."""

    def __init__(self):
        self._parsers: dict[str, object] = {}

    def on_startup(self) -> None:
        """Warm parser cache for common languages."""
        for language in ("python", "javascript", "typescript", "go", "rust"):
            try:
                self.get_parser(language)
            except Exception:
                continue

    def get_parser(self, language: str):
        """Return cached parser for language."""
        if get_parser is None:
            raise RuntimeError(
                "tree-sitter dependencies are not installed. Install tree-sitter and tree-sitter-language-pack."
            )
        if language not in self._parsers:
            self._parsers[language] = get_parser(language)
        return self._parsers[language]

    def detect_language(self, path: str) -> str:
        """Detect language from file extension."""
        suffix = Path(path).suffix.lower()
        if suffix in EXTENSION_TO_LANGUAGE:
            return EXTENSION_TO_LANGUAGE[suffix]
        raise ValueError(
            f"Unsupported file extension for language tools: '{suffix or '<none>'}'."
        )

    def parse(self, content: str, language: str) -> Tree:
        """Parse source content and return tree."""
        parser = self.get_parser(language)
        return parser.parse(content.encode("utf-8"))

    def collect_parse_issues(self, tree: Tree) -> list[ParseIssue]:
        """Collect syntax issues from the parse tree."""
        if tree is None:
            return []

        issues: list[ParseIssue] = []

        def visit(node: Node) -> None:
            if node.type == "ERROR":
                issues.append(
                    ParseIssue(
                        line=node.start_point.row + 1,
                        col=node.start_point.column + 1,
                        message="syntax error",
                    )
                )
            elif node.is_missing:
                issues.append(
                    ParseIssue(
                        line=node.start_point.row + 1,
                        col=node.start_point.column + 1,
                        message=f"missing token: {node.type}",
                    )
                )
            for child in node.children:
                visit(child)

        visit(tree.root_node)
        if not issues and tree.root_node.has_error:
            issues.append(
                ParseIssue(
                    line=tree.root_node.start_point.row + 1,
                    col=tree.root_node.start_point.column + 1,
                    message="syntax error",
                )
            )
        return issues

    def extract_symbols(
        self,
        content: str,
        language: str,
        depth: str = "signatures",
    ) -> list[ExtractedSymbol]:
        """Extract top-level symbols (with class children for methods)."""
        tree = self.parse(content, language)
        source = content.encode("utf-8")
        symbols: list[ExtractedSymbol] = []

        for child in tree.root_node.children:
            symbols.extend(self._extract_from_node(child, source, parent_kind=None, depth=depth))

        return symbols

    def extract_calls(
        self,
        content: str,
        language: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> list[CallSite]:
        """Extract call sites for basic reference graph generation."""
        tree = self.parse(content, language)
        calls: list[CallSite] = []

        def visit(node: Node) -> None:
            if node.type in CALL_NODE_TYPES:
                line_no = node.start_point.row + 1
                if start_line is not None and line_no < start_line:
                    pass
                elif end_line is not None and line_no > end_line:
                    pass
                else:
                    name = self._extract_call_name(node)
                    if name:
                        calls.append(CallSite(name=name, line=line_no))
            for child in node.children:
                visit(child)

        visit(tree.root_node)
        return calls

    def render_skeleton(self, symbols: list[ExtractedSymbol]) -> str:
        """Render a compact structural skeleton representation."""
        lines: list[str] = []
        for symbol in symbols:
            lines.append(self._render_symbol(symbol, depth=0))
            for child in symbol.children:
                lines.append(self._render_symbol(child, depth=1))
        return "\n".join(lines).rstrip()

    def flatten_symbols(
        self,
        symbols: Iterable[ExtractedSymbol],
        include_children: bool = True,
    ) -> list[ExtractedSymbol]:
        """Flatten nested symbol tree."""
        flat: list[ExtractedSymbol] = []

        def visit(symbol: ExtractedSymbol) -> None:
            flat.append(symbol)
            if include_children:
                for child in symbol.children:
                    visit(child)

        for symbol in symbols:
            visit(symbol)
        return flat

    def _extract_from_node(
        self,
        node: Node,
        source: bytes,
        parent_kind: Optional[str],
        depth: str,
    ) -> list[ExtractedSymbol]:
        normalized = self._normalize_node(node)
        if normalized is None:
            return []

        kind = self._classify_node(normalized.type, parent_kind)
        if kind is None:
            symbols: list[ExtractedSymbol] = []
            for child in normalized.children:
                symbols.extend(self._extract_from_node(child, source, parent_kind, depth))
            return symbols

        name = self._extract_symbol_name(normalized, source, kind)
        signature = self._extract_signature(normalized, source)
        symbol = ExtractedSymbol(
            name=name,
            kind=kind,
            signature=signature,
            start_line=normalized.start_point.row + 1,
            end_line=normalized.end_point.row + 1,
            start_col=normalized.start_point.column + 1,
            end_col=normalized.end_point.column + 1,
            start_byte=normalized.start_byte,
            end_byte=normalized.end_byte,
            children=[],
        )

        if depth == "full" or kind == "class":
            for child in normalized.children:
                child_symbols = self._extract_from_node(
                    child,
                    source,
                    parent_kind=kind,
                    depth=depth,
                )
                for child_symbol in child_symbols:
                    if kind == "class" and child_symbol.kind == "function":
                        child_symbol.kind = "method"
                    if child_symbol.kind in {"method", "function", "variable", "type"}:
                        symbol.children.append(child_symbol)

        return [symbol]

    @staticmethod
    def _normalize_node(node: Node) -> Optional[Node]:
        """Normalize wrappers such as decorated definitions."""
        if node.type == "decorated_definition":
            child = node.child_by_field_name("definition")
            if child is not None:
                return child
        return node

    @staticmethod
    def _classify_node(node_type: str, parent_kind: Optional[str]) -> Optional[str]:
        if node_type in IMPORT_NODE_TYPES:
            return "import"
        if node_type in CLASS_NODE_TYPES:
            return "class"
        if node_type in TYPE_NODE_TYPES:
            return "type"
        if node_type in METHOD_NODE_TYPES:
            return "method"
        if node_type in FUNCTION_NODE_TYPES:
            if parent_kind == "class":
                return "method"
            return "function"
        if node_type in VARIABLE_NODE_TYPES:
            return "variable"
        return None

    def _extract_symbol_name(self, node: Node, source: bytes, kind: str) -> str:
        for field_name in ("name", "declarator"):
            child = node.child_by_field_name(field_name)
            if child is not None:
                name = self._identifier_text(child, source)
                if name:
                    return name

        for child in node.children:
            name = self._identifier_text(child, source)
            if name:
                return name

        fallback = node.type.replace("_", " ")
        return f"{kind}:{fallback}"

    def _extract_call_name(self, node: Node) -> Optional[str]:
        function_node = node.child_by_field_name("function")
        if function_node is None and node.children:
            function_node = node.children[0]
        if function_node is None:
            return None
        return self._identifier_text(function_node, function_node.text)

    def _identifier_text(self, node: Node, source: bytes) -> Optional[str]:
        if node.type in IDENTIFIER_NODE_TYPES:
            return node.text.decode("utf-8", errors="replace")
        for child in node.children:
            text = self._identifier_text(child, source)
            if text:
                return text
        text = node.text.decode("utf-8", errors="replace").strip()
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", text):
            return text
        return None

    @staticmethod
    def _extract_signature(node: Node, source: bytes) -> str:
        text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
        first_line = text.splitlines()[0].strip() if text else ""
        return first_line or node.type

    @staticmethod
    def _render_symbol(symbol: ExtractedSymbol, depth: int) -> str:
        indent = "  " * depth
        return (
            f"{indent}{symbol.kind} {symbol.name}"
            f" ({symbol.start_line}-{symbol.end_line}): {symbol.signature}"
        )
