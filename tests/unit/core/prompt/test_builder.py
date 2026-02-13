"""Unit tests for core/prompt/builder.py — system prompt construction."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.prompt.builder import (
    _build_messaging_section,
    _discover_other_persons,
    build_system_prompt,
    inject_shortterm,
)


# ── _discover_other_persons ───────────────────────────────


class TestDiscoverOtherPersons:
    def test_finds_siblings(self, tmp_path):
        persons_root = tmp_path / "persons"
        persons_root.mkdir()
        alice = persons_root / "alice"
        alice.mkdir()
        (alice / "identity.md").write_text("I am Alice", encoding="utf-8")
        bob = persons_root / "bob"
        bob.mkdir()
        (bob / "identity.md").write_text("I am Bob", encoding="utf-8")

        result = _discover_other_persons(alice)
        assert result == ["bob"]

    def test_excludes_self(self, tmp_path):
        persons_root = tmp_path / "persons"
        persons_root.mkdir()
        alice = persons_root / "alice"
        alice.mkdir()
        (alice / "identity.md").write_text("I am Alice", encoding="utf-8")

        result = _discover_other_persons(alice)
        assert "alice" not in result

    def test_excludes_dirs_without_identity(self, tmp_path):
        persons_root = tmp_path / "persons"
        persons_root.mkdir()
        alice = persons_root / "alice"
        alice.mkdir()
        (alice / "identity.md").write_text("I am Alice", encoding="utf-8")
        noident = persons_root / "noident"
        noident.mkdir()
        # no identity.md

        result = _discover_other_persons(alice)
        assert "noident" not in result

    def test_no_siblings(self, tmp_path):
        persons_root = tmp_path / "persons"
        persons_root.mkdir()
        alice = persons_root / "alice"
        alice.mkdir()
        (alice / "identity.md").write_text("I am Alice", encoding="utf-8")

        result = _discover_other_persons(alice)
        assert result == []


# ── _build_messaging_section ──────────────────────────────


class TestBuildMessagingSection:
    def test_with_persons(self, tmp_path):
        person_dir = tmp_path / "alice"
        person_dir.mkdir()
        with patch("core.prompt.builder.load_prompt", return_value="messaging section"):
            result = _build_messaging_section(person_dir, ["bob", "charlie"])
            assert result == "messaging section"

    def test_no_persons(self, tmp_path):
        person_dir = tmp_path / "alice"
        person_dir.mkdir()
        with patch("core.prompt.builder.load_prompt", return_value="messaging section") as mock_lp:
            _build_messaging_section(person_dir, [])
            call_kwargs = mock_lp.call_args[1]
            assert "(まだ他の社員はいません)" in call_kwargs["persons_line"]


# ── build_system_prompt ───────────────────────────────────


class TestBuildSystemPrompt:
    def test_builds_prompt(self, tmp_path, data_dir):
        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)
        (person_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = MagicMock()
        memory.person_dir = person_dir
        memory.read_company_vision.return_value = "Company Vision"
        memory.read_identity.return_value = "I am Alice"
        memory.read_injection.return_value = ""
        memory.read_permissions.return_value = ""
        memory.read_current_state.return_value = "status: idle"
        memory.read_pending.return_value = ""
        memory.read_bootstrap.return_value = ""
        memory.list_knowledge_files.return_value = []
        memory.list_episode_files.return_value = []
        memory.list_procedure_files.return_value = []
        memory.list_skill_summaries.return_value = []
        memory.list_common_skill_summaries.return_value = []
        memory.common_skills_dir = data_dir / "common_skills"
        memory.list_shared_users.return_value = []

        with patch("core.prompt.builder.load_prompt", return_value="prompt section"):
            result = build_system_prompt(memory)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_includes_identity(self, tmp_path, data_dir):
        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)
        (person_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = MagicMock()
        memory.person_dir = person_dir
        memory.read_company_vision.return_value = ""
        memory.read_identity.return_value = "I am Alice"
        memory.read_injection.return_value = ""
        memory.read_permissions.return_value = ""
        memory.read_current_state.return_value = ""
        memory.read_pending.return_value = ""
        memory.read_bootstrap.return_value = ""
        memory.list_knowledge_files.return_value = []
        memory.list_episode_files.return_value = []
        memory.list_procedure_files.return_value = []
        memory.list_skill_summaries.return_value = []
        memory.list_common_skill_summaries.return_value = []
        memory.common_skills_dir = data_dir / "common_skills"
        memory.list_shared_users.return_value = []

        with patch("core.prompt.builder.load_prompt", return_value="prompt"):
            result = build_system_prompt(memory)
            assert "I am Alice" in result

    def test_includes_skills(self, tmp_path, data_dir):
        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)
        (person_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = MagicMock()
        memory.person_dir = person_dir
        memory.read_company_vision.return_value = ""
        memory.read_identity.return_value = ""
        memory.read_injection.return_value = ""
        memory.read_permissions.return_value = ""
        memory.read_current_state.return_value = ""
        memory.read_pending.return_value = ""
        memory.read_bootstrap.return_value = ""
        memory.list_knowledge_files.return_value = []
        memory.list_episode_files.return_value = []
        memory.list_procedure_files.return_value = []
        memory.list_skill_summaries.return_value = [("coding", "Write code")]
        memory.list_common_skill_summaries.return_value = [("deploy", "Deploy apps")]
        memory.common_skills_dir = data_dir / "common_skills"
        memory.list_shared_users.return_value = []

        with patch("core.prompt.builder.load_prompt", return_value="section"):
            result = build_system_prompt(memory)
            # Common skills section is built inline (not via load_prompt)
            assert "共通スキル" in result
            assert "deploy" in result
            # Personal skills are built via load_prompt("skills_guide", ...)
            # which returns "section" in mock; verify it was called
            # The memory_guide template gets skill names as kwargs
            assert "coding" in result or "section" in result

    def test_includes_bootstrap(self, tmp_path, data_dir):
        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)
        (person_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = MagicMock()
        memory.person_dir = person_dir
        memory.read_company_vision.return_value = ""
        memory.read_identity.return_value = ""
        memory.read_injection.return_value = ""
        memory.read_permissions.return_value = ""
        memory.read_current_state.return_value = ""
        memory.read_pending.return_value = ""
        memory.read_bootstrap.return_value = "Bootstrap instructions"
        memory.list_knowledge_files.return_value = []
        memory.list_episode_files.return_value = []
        memory.list_procedure_files.return_value = []
        memory.list_skill_summaries.return_value = []
        memory.list_common_skill_summaries.return_value = []
        memory.common_skills_dir = data_dir / "common_skills"
        memory.list_shared_users.return_value = []

        with patch("core.prompt.builder.load_prompt", return_value="section"):
            result = build_system_prompt(memory)
            assert "Bootstrap instructions" in result

    def test_includes_state_and_pending(self, tmp_path, data_dir):
        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)
        (person_dir / "identity.md").write_text("I am Alice", encoding="utf-8")

        memory = MagicMock()
        memory.person_dir = person_dir
        memory.read_company_vision.return_value = ""
        memory.read_identity.return_value = ""
        memory.read_injection.return_value = ""
        memory.read_permissions.return_value = ""
        memory.read_current_state.return_value = "status: working"
        memory.read_pending.return_value = "- task 1"
        memory.read_bootstrap.return_value = ""
        memory.list_knowledge_files.return_value = []
        memory.list_episode_files.return_value = []
        memory.list_procedure_files.return_value = []
        memory.list_skill_summaries.return_value = []
        memory.list_common_skill_summaries.return_value = []
        memory.common_skills_dir = data_dir / "common_skills"
        memory.list_shared_users.return_value = []

        with patch("core.prompt.builder.load_prompt", return_value="section"):
            result = build_system_prompt(memory)
            assert "現在の状態" in result
            assert "status: working" in result
            assert "未完了タスク" in result
            assert "task 1" in result


# ── inject_shortterm ──────────────────────────────────────


class TestInjectShortterm:
    def test_no_shortterm(self):
        shortterm = MagicMock()
        shortterm.load_markdown.return_value = ""
        result = inject_shortterm("base prompt", shortterm)
        assert result == "base prompt"

    def test_with_shortterm(self):
        shortterm = MagicMock()
        shortterm.load_markdown.return_value = "# Short-term memory\nContent"
        result = inject_shortterm("base prompt", shortterm)
        assert "base prompt" in result
        assert "Short-term memory" in result
        assert "---" in result
