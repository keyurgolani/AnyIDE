#!/usr/bin/env python3
"""
Script to generate tool catalog documentation from OpenAPI spec.

Usage:
    python scripts/generate_tool_docs.py > docs/TOOL_CATALOG.md
"""

import json
import os
import sys
import tempfile
import warnings
import contextlib
import io
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yaml
except ImportError:
    yaml = None


def get_openapi_spec():
    """Get the OpenAPI spec from the running application."""
    temp_root = Path(tempfile.gettempdir()) / "anyide-tool-docs"
    temp_root.mkdir(parents=True, exist_ok=True)

    # Ensure script can run outside containerized /data defaults.
    if "WORKSPACE_BASE_DIR" not in os.environ:
        workspace_dir = temp_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        os.environ["WORKSPACE_BASE_DIR"] = str(workspace_dir)

    if "DB_PATH" not in os.environ:
        data_dir = temp_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        os.environ["DB_PATH"] = str(data_dir / "anyide.db")

    warnings.filterwarnings(
        "ignore",
        message="`regex` has been deprecated, please use `pattern` instead",
        category=DeprecationWarning,
    )

    # Suppress app startup logs so stdout remains pure markdown.
    with contextlib.redirect_stdout(io.StringIO()):
        from anyide.main import app
        return app.openapi()


def generate_markdown_doc(spec):
    """Generate markdown documentation from OpenAPI spec."""
    lines = []
    lines.append("# AnyIDE Tool Catalog\n")
    lines.append("Auto-generated documentation for all available tools.\n")
    lines.append(f"**Generated from:** OpenAPI spec\n")
    lines.append(f"**Version:** {spec.get('info', {}).get('version', 'Unknown')}\n")
    lines.append("---\n")

    # Group paths by tool category
    tools_by_category = {}

    for path, methods in spec.get("paths", {}).items():
        if not path.startswith("/api/tools/"):
            continue

        parts = path.split("/")
        if len(parts) >= 4:
            category = parts[3]
            tool_name = parts[4] if len(parts) > 4 else "unknown"

            if category not in tools_by_category:
                tools_by_category[category] = []

            for method, details in methods.items():
                if method in ["get", "post", "put", "delete"]:
                    tools_by_category[category].append({
                        "path": path,
                        "method": method.upper(),
                        "name": tool_name,
                        "details": details
                    })

    # Generate documentation for each category
    for category in sorted(tools_by_category.keys()):
        tools = tools_by_category[category]
        lines.append(f"## {category.upper()} Tools\n")

        for tool in sorted(tools, key=lambda x: x["name"]):
            details = tool["details"]
            lines.append(f"### {tool['name']}\n")
            lines.append(f"**Endpoint:** `{tool['method']} {tool['path']}`\n")

            # Summary
            if "summary" in details:
                lines.append(f"\n**Summary:** {details['summary']}\n")

            # Description
            if "description" in details:
                lines.append(f"\n**Description:**\n\n{details['description']}\n")

            # Request body / parameters
            if "requestBody" in details:
                lines.append("\n**Request Body:**\n")
                content = details["requestBody"].get("content", {})
                if "application/json" in content:
                    schema = content["application/json"].get("schema", {})
                    if "properties" in schema:
                        lines.append("\n| Parameter | Type | Required | Description |")
                        lines.append("|-----------|------|----------|-------------|")
                        required = schema.get("required", [])
                        for prop_name, prop_details in schema["properties"].items():
                            prop_type = prop_details.get("type", "any")
                            is_required = "Yes" if prop_name in required else "No"
                            description = prop_details.get("description", "")
                            lines.append(f"| `{prop_name}` | `{prop_type}` | {is_required} | {description} |")

            # Responses
            if "responses" in details:
                lines.append("\n**Responses:**\n")
                for status, response in details["responses"].items():
                    description = response.get("description", "No description")
                    lines.append(f"- **{status}:** {description}")

            lines.append("\n---\n")

    # Add MCP tool names
    lines.append("## MCP Tool Names\n")
    lines.append("When using MCP clients, tools are identified by their operation IDs:\n")

    for category in sorted(tools_by_category.keys()):
        tools = tools_by_category[category]
        for tool in sorted(tools, key=lambda x: x["name"]):
            details = tool["details"]
            op_id = details.get("operationId", f"{category}_{tool['name']}")
            lines.append(f"- `{op_id}` - {category}/{tool['name']}")

    return "\n".join(lines)


def main():
    """Main entry point."""
    spec = get_openapi_spec()
    markdown = generate_markdown_doc(spec)
    print(markdown)


if __name__ == "__main__":
    main()
