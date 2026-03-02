"""Unit tests for the skills module tools."""

from __future__ import annotations

import pytest

from anyide.modules.skills.schemas import (
    SkillsInstallRequest,
    SkillsReadFileRequest,
    SkillsReadRequest,
    SkillsSearchRequest,
)
from anyide.modules.skills.tools import SkillsTools


@pytest.fixture
def skills_dir(tmp_path):
    base = tmp_path / "skills"
    base.mkdir(parents=True, exist_ok=True)

    sample = base / "sample-skill"
    sample.mkdir()
    (sample / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: sample-skill",
                "description: Sample skill used in tests",
                "---",
                "",
                "# Sample Skill",
                "",
                "## Usage",
                "Use this skill for deterministic testing.",
                "",
                "## Details",
                "Extra details.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sample / "scripts").mkdir()
    (sample / "scripts" / "helper.sh").write_text("#!/bin/sh\necho helper\n", encoding="utf-8")
    (sample / "references").mkdir()
    (sample / "references" / "guide.md").write_text("Guide\n", encoding="utf-8")

    plain = base / "plain-skill"
    plain.mkdir()
    (plain / "SKILL.md").write_text("# Plain Skill\nNo frontmatter.\n", encoding="utf-8")

    return base


@pytest.fixture
def skills_tools(skills_dir):
    return SkillsTools(base_dir=str(skills_dir))


@pytest.mark.asyncio
async def test_skills_list_reads_frontmatter(skills_tools: SkillsTools):
    response = await skills_tools.list()

    names = [item.name for item in response.skills]
    assert "sample-skill" in names
    assert "plain-skill" in names

    sample = next(item for item in response.skills if item.name == "sample-skill")
    assert sample.description == "Sample skill used in tests"
    assert sample.size_bytes > 0


@pytest.mark.asyncio
async def test_skills_read_section_and_metadata(skills_tools: SkillsTools):
    response = await skills_tools.read(
        SkillsReadRequest(name="sample-skill", section="Usage")
    )

    assert response.name == "sample-skill"
    assert response.metadata.get("description") == "Sample skill used in tests"
    assert "Use this skill for deterministic testing." in response.content
    assert "Extra details." not in response.content
    assert response.has_scripts is True
    assert "helper.sh" in response.scripts
    assert response.has_references is True
    assert "guide.md" in response.references


@pytest.mark.asyncio
async def test_skills_read_file_blocks_escape(skills_tools: SkillsTools):
    with pytest.raises(ValueError, match="outside skill directory"):
        await skills_tools.read_file(
            SkillsReadFileRequest(
                name="sample-skill",
                file_path="../plain-skill/SKILL.md",
            )
        )


@pytest.mark.asyncio
async def test_skills_search_parses_json_output(
    monkeypatch: pytest.MonkeyPatch,
    skills_tools: SkillsTools,
):
    async def fake_run(*_args, **_kwargs):
        return (
            '[{"name":"python-performance-optimization","repo":"acme/skills","description":"Perf skill","installs":123}]',
            "",
            0,
        )

    monkeypatch.setattr(skills_tools, "_run_skills_cli", fake_run)

    response = await skills_tools.search(
        SkillsSearchRequest(query="python performance", max_results=5)
    )
    assert len(response.results) == 1
    assert response.results[0].name == "python-performance-optimization"
    assert response.results[0].installs == 123


@pytest.mark.asyncio
async def test_skills_search_rejects_unparseable_output(
    monkeypatch: pytest.MonkeyPatch,
    skills_tools: SkillsTools,
):
    async def fake_run(*_args, **_kwargs):
        return ("non-json output", "", 0)

    monkeypatch.setattr(skills_tools, "_run_skills_cli", fake_run)

    with pytest.raises(ValueError, match="Failed to parse"):
        await skills_tools.search(SkillsSearchRequest(query="react"))


@pytest.mark.asyncio
async def test_skills_search_parses_plaintext_ansi_output(
    monkeypatch: pytest.MonkeyPatch,
    skills_tools: SkillsTools,
):
    async def fake_run(*_args, **_kwargs):
        return (
            "\n".join(
                [
                    "\u001b[38;5;145mpproenca/dot-skills@vitest\u001b[0m \u001b[36m247 installs\u001b[0m",
                    "\u001b[38;5;102m└ https://skills.sh/pproenca/dot-skills/vitest\u001b[0m",
                    "",
                    "\u001b[38;5;145mjezweb/claude-skills@vitest\u001b[0m \u001b[36m147 installs\u001b[0m",
                ]
            ),
            "",
            0,
        )

    monkeypatch.setattr(skills_tools, "_run_skills_cli", fake_run)

    response = await skills_tools.search(SkillsSearchRequest(query="vitest", max_results=1))

    assert response.total == 1
    assert response.results[0].name == "vitest"
    assert response.results[0].repo == "pproenca/dot-skills"
    assert response.results[0].installs == 247


@pytest.mark.asyncio
async def test_skills_install_reports_network_error(
    monkeypatch: pytest.MonkeyPatch,
    skills_tools: SkillsTools,
):
    async def fake_run(*_args, **_kwargs):
        return ("", "ECONNREFUSED while reaching registry", 1)

    monkeypatch.setattr(skills_tools, "_run_skills_cli", fake_run)

    with pytest.raises(ConnectionError, match="network"):
        await skills_tools.install(
            SkillsInstallRequest(
                repo="vercel-labs/agent-skills",
                skill_name="sample-skill",
            )
        )


@pytest.mark.asyncio
async def test_skills_install_returns_preview(
    monkeypatch: pytest.MonkeyPatch,
    skills_tools: SkillsTools,
):
    async def fake_run(*_args, **_kwargs):
        return ("installed", "", 0)

    monkeypatch.setattr(skills_tools, "_run_skills_cli", fake_run)

    response = await skills_tools.install(
        SkillsInstallRequest(repo="vercel-labs/agent-skills", skill_name="sample-skill")
    )
    assert response.installed is True
    assert response.skill_name == "sample-skill"
    assert len(response.skill_md_preview) > 0
