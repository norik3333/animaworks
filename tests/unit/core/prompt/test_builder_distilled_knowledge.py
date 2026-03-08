"""Unit tests for distilled knowledge summary injection in builder.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from core.prompt.builder import (
    BuildResult,
    _extract_entry_summary,
    build_system_prompt,
)

# ── Helpers ──────────────────────────────────────────────


def _make_mock_memory(anima_dir: Path, data_dir: Path) -> MagicMock:
    """Create a mock MemoryManager with standard stubs."""
    memory = MagicMock()
    memory.anima_dir = anima_dir
    memory.read_company_vision.return_value = ""
    memory.read_identity.return_value = "I am Test Anima"
    memory.read_injection.return_value = ""
    memory.read_permissions.return_value = ""
    memory.read_specialty_prompt.return_value = ""
    memory.read_current_state.return_value = ""
    memory.read_pending.return_value = ""
    memory.read_bootstrap.return_value = ""
    memory.list_knowledge_files.return_value = []
    memory.list_episode_files.return_value = []
    memory.list_procedure_files.return_value = []
    memory.list_skill_summaries.return_value = []
    memory.list_common_skill_summaries.return_value = []
    memory.list_skill_metas.return_value = []
    memory.list_common_skill_metas.return_value = []
    memory.list_procedure_metas.return_value = []
    memory.common_skills_dir = data_dir / "common_skills"
    memory.list_shared_users.return_value = []
    memory.collect_distilled_knowledge.return_value = []
    memory.collect_distilled_knowledge_separated.return_value = ([], [])
    model_cfg = MagicMock()
    model_cfg.model = "claude-sonnet-4-6"
    model_cfg.supervisor = None
    memory.read_model_config.return_value = model_cfg
    return memory


def _entry(name: str, content: str, confidence: float, *, description: str = "") -> dict:
    """Build a DK entry dict."""
    return {
        "name": name,
        "content": content,
        "description": description,
        "confidence": confidence,
        "path": f"/tmp/test/{name}.md",
        "mtime": 0.0,
    }


# ── _extract_entry_summary ───────────────────────────────


class TestExtractEntrySummary:
    def test_uses_description_when_present(self) -> None:
        entry = _entry("foo", "# Heading\nBody.", 0.5, description="My description")
        assert _extract_entry_summary(entry) == "My description"

    def test_falls_back_to_heading(self) -> None:
        entry = _entry("foo", "# Deploy Guide\nBody text.", 0.5)
        assert _extract_entry_summary(entry) == "Deploy Guide"

    def test_falls_back_to_first_paragraph(self) -> None:
        entry = _entry("foo", "Body without heading.", 0.5)
        assert _extract_entry_summary(entry) == "Body without heading."

    def test_falls_back_to_name(self) -> None:
        entry = _entry("deploy-procedure", "", 0.5)
        assert _extract_entry_summary(entry) == "deploy procedure"


# ── Summary injection format ──────────────────────────────


class TestSummaryInjectionFormat:
    def test_summary_list_format(self, tmp_path: Path, data_dir: Path) -> None:
        """DK entries are injected as '- **name**: summary' list items."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        memory.collect_distilled_knowledge_separated.return_value = (
            [_entry("deploy-procedure", "Deploy using docker compose up.", 0.7, description="Docker deploy steps")],
            [_entry("python-basics", "Python is dynamic.", 0.9, description="Python language overview")],
        )

        result = build_system_prompt(memory)
        assert isinstance(result, BuildResult)
        assert "- **deploy-procedure**: Docker deploy steps" in result
        assert "- **python-basics**: Python language overview" in result

    def test_no_full_content_in_prompt(self, tmp_path: Path, data_dir: Path) -> None:
        """Full body content must NOT appear in the prompt."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        memory.collect_distilled_knowledge_separated.return_value = (
            [_entry("proc", "FULL_BODY_SHOULD_NOT_APPEAR", 0.7, description="Short desc")],
            [],
        )

        result = build_system_prompt(memory)
        assert "FULL_BODY_SHOULD_NOT_APPEAR" not in result.system_prompt


class TestDistilledEntriesEmpty:
    def test_distilled_entries_empty(self, tmp_path: Path, data_dir: Path) -> None:
        """Empty list -> no DK sections."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        memory.collect_distilled_knowledge_separated.return_value = ([], [])

        result = build_system_prompt(memory)
        assert "## Distilled Knowledge" not in result
        assert "## Procedures" not in result


# ── Overflow ──────────────────────────────────────────────


class TestOverflowFilesInBuildResult:
    def test_overflow_files_in_build_result(self, tmp_path: Path, data_dir: Path) -> None:
        """Entries exceeding budget appear in BuildResult.overflow_files."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        many_entries = [_entry(f"know-{i}", f"content {i}", 0.5, description=f"desc {i}") for i in range(50)]
        memory.collect_distilled_knowledge_separated.return_value = ([], many_entries)

        result = build_system_prompt(memory)
        assert isinstance(result, BuildResult)
        assert len(result.overflow_files) > 0


class TestAutoComputeWhenNoEntries:
    def test_auto_compute_when_no_entries(self, tmp_path: Path, data_dir: Path) -> None:
        """Builder calls collect_distilled_knowledge_separated."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        memory.collect_distilled_knowledge_separated.return_value = (
            [],
            [_entry("auto-computed", "Auto content", 0.8, description="Auto desc")],
        )

        result = build_system_prompt(memory)
        assert isinstance(result, BuildResult)
        memory.collect_distilled_knowledge_separated.assert_called_once()
        assert "auto-computed" in result
        assert "Auto desc" in result


# ── Ordering ──────────────────────────────────────────────


class TestConfidenceSortingInOutput:
    def test_confidence_sorting_in_output(self, tmp_path: Path, data_dir: Path) -> None:
        """Entries are injected in confidence-descending order."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        memory.collect_distilled_knowledge_separated.return_value = (
            [],
            [
                _entry("high-conf", "high content", 0.9, description="HIGH_DESC"),
                _entry("low-conf", "low content", 0.3, description="LOW_DESC"),
            ],
        )

        result = build_system_prompt(memory)
        assert "HIGH_DESC" in result
        assert "LOW_DESC" in result
        high_pos = result.system_prompt.index("HIGH_DESC")
        low_pos = result.system_prompt.index("LOW_DESC")
        assert high_pos < low_pos


# ── Separate budgets ─────────────────────────────────────


class TestSeparateBudgets:
    def test_procedure_budget_does_not_starve_knowledge(self, tmp_path: Path, data_dir: Path) -> None:
        """Procedure overflow does not consume knowledge budget."""
        anima_dir = tmp_path / "animas" / "alice"
        anima_dir.mkdir(parents=True)
        (anima_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = _make_mock_memory(anima_dir, data_dir)
        many_procs = [_entry(f"proc-{i}", f"c{i}", 0.5, description=f"d{i}") for i in range(100)]
        know_entry = _entry("important-know", "kc", 0.9, description="Important knowledge")
        memory.collect_distilled_knowledge_separated.return_value = (many_procs, [know_entry])

        result = build_system_prompt(memory)
        assert "important-know" in result.system_prompt
        assert "Important knowledge" in result.system_prompt
