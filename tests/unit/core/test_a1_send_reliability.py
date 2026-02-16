"""Unit tests for A1 mode send script reliability improvements."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from core.execution.agent_sdk import AgentSDKExecutor
from core.person_factory import ensure_send_scripts
from core.schemas import ModelConfig


# ── _build_env() ─────────────────────────────────────────


class TestBuildEnvPathAndProjectDir:
    """Verify _build_env() exposes person_dir in PATH and sets PROJECT_DIR."""

    def _make_executor(self, person_dir: Path) -> AgentSDKExecutor:
        mc = ModelConfig(model="claude-sonnet-4-20250514")
        return AgentSDKExecutor(model_config=mc, person_dir=person_dir)

    def test_person_dir_in_path(self, tmp_path: Path) -> None:
        """PATH should start with person_dir so `send` is discoverable."""
        person_dir = tmp_path / "persons" / "alice"
        person_dir.mkdir(parents=True)

        executor = self._make_executor(person_dir)
        env = executor._build_env()

        assert "PATH" in env
        path_entries = env["PATH"].split(":")
        assert str(person_dir) == path_entries[0], (
            "person_dir must be the first entry in PATH"
        )

    def test_system_path_preserved(self, tmp_path: Path) -> None:
        """System PATH entries should be preserved after person_dir."""
        person_dir = tmp_path / "persons" / "bob"
        person_dir.mkdir(parents=True)

        original_path = "/usr/local/bin:/usr/bin:/bin"
        with patch.dict(os.environ, {"PATH": original_path}):
            executor = self._make_executor(person_dir)
            env = executor._build_env()

        assert env["PATH"] == f"{person_dir}:{original_path}"

    def test_project_dir_set(self, tmp_path: Path) -> None:
        """ANIMAWORKS_PROJECT_DIR should be set to the project root."""
        from core.paths import PROJECT_DIR

        person_dir = tmp_path / "persons" / "carol"
        person_dir.mkdir(parents=True)

        executor = self._make_executor(person_dir)
        env = executor._build_env()

        assert "ANIMAWORKS_PROJECT_DIR" in env
        assert env["ANIMAWORKS_PROJECT_DIR"] == str(PROJECT_DIR)

    def test_person_dir_env_set(self, tmp_path: Path) -> None:
        """ANIMAWORKS_PERSON_DIR should still be set."""
        person_dir = tmp_path / "persons" / "dave"
        person_dir.mkdir(parents=True)

        executor = self._make_executor(person_dir)
        env = executor._build_env()

        assert env["ANIMAWORKS_PERSON_DIR"] == str(person_dir)

    def test_fallback_path_when_no_env(self, tmp_path: Path) -> None:
        """When PATH is not in os.environ, fall back to /usr/bin:/bin."""
        person_dir = tmp_path / "persons" / "eve"
        person_dir.mkdir(parents=True)

        env_without_path = {k: v for k, v in os.environ.items() if k != "PATH"}
        with patch.dict(os.environ, env_without_path, clear=True):
            executor = self._make_executor(person_dir)
            env = executor._build_env()

        assert env["PATH"] == f"{person_dir}:/usr/bin:/bin"


# ── ensure_send_scripts() ────────────────────────────────


class TestEnsureSendScripts:
    """Verify ensure_send_scripts() places send script for all persons."""

    def test_places_script_for_persons_without_it(self, tmp_path: Path) -> None:
        """Persons missing the send script should get it."""
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()

        # Create two person dirs without send scripts
        for name in ("alice", "bob"):
            d = persons_dir / name
            d.mkdir()
            (d / "identity.md").write_text(f"# {name}", encoding="utf-8")

        # Create a fake blank template with a send script
        blank_dir = tmp_path / "blank"
        blank_dir.mkdir()
        (blank_dir / "send").write_text("#!/bin/bash\necho send", encoding="utf-8")

        with patch("core.person_factory.BLANK_TEMPLATE_DIR", blank_dir):
            ensure_send_scripts(persons_dir)

        for name in ("alice", "bob"):
            send = persons_dir / name / "send"
            assert send.exists(), f"send script missing for {name}"
            assert send.stat().st_mode & 0o100, f"send script not executable for {name}"

    def test_does_not_overwrite_existing_scripts(self, tmp_path: Path) -> None:
        """Existing send scripts must not be replaced."""
        persons_dir = tmp_path / "persons"
        alice_dir = persons_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "identity.md").write_text("# alice", encoding="utf-8")

        # Pre-existing custom send script
        existing = alice_dir / "send"
        existing.write_text("#!/bin/bash\ncustom-send", encoding="utf-8")

        blank_dir = tmp_path / "blank"
        blank_dir.mkdir()
        (blank_dir / "send").write_text("#!/bin/bash\ntemplate-send", encoding="utf-8")

        with patch("core.person_factory.BLANK_TEMPLATE_DIR", blank_dir):
            ensure_send_scripts(persons_dir)

        assert existing.read_text(encoding="utf-8") == "#!/bin/bash\ncustom-send"

    def test_skips_dirs_without_identity(self, tmp_path: Path) -> None:
        """Directories without identity.md are not person dirs; skip them."""
        persons_dir = tmp_path / "persons"
        persons_dir.mkdir()

        # Non-person directory (no identity.md)
        non_person = persons_dir / "shared"
        non_person.mkdir()

        blank_dir = tmp_path / "blank"
        blank_dir.mkdir()
        (blank_dir / "send").write_text("#!/bin/bash\necho send", encoding="utf-8")

        with patch("core.person_factory.BLANK_TEMPLATE_DIR", blank_dir):
            ensure_send_scripts(persons_dir)

        assert not (non_person / "send").exists()

    def test_nonexistent_persons_dir(self, tmp_path: Path) -> None:
        """If persons_dir doesn't exist, ensure_send_scripts() is a no-op."""
        missing_dir = tmp_path / "nonexistent"
        # Should not raise
        ensure_send_scripts(missing_dir)
