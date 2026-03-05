"""Unit tests for CLI index --shared flag."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cli.commands.index_cmd import (
    _index_shared_collections,
    _is_anima_enabled,
    setup_index_command,
)


# ── _is_anima_enabled ─────────────────────────────────────


class TestIsAnimaEnabled:
    def test_enabled_when_no_status_file(self, tmp_path: Path) -> None:
        assert _is_anima_enabled(tmp_path) is True

    def test_enabled_explicitly(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text('{"enabled": true}')
        assert _is_anima_enabled(tmp_path) is True

    def test_disabled(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text('{"enabled": false}')
        assert _is_anima_enabled(tmp_path) is False

    def test_enabled_default_when_key_missing(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text('{"model": "claude-sonnet-4-6"}')
        assert _is_anima_enabled(tmp_path) is True

    def test_corrupted_json_treated_as_enabled(self, tmp_path: Path) -> None:
        (tmp_path / "status.json").write_text("{bad")
        assert _is_anima_enabled(tmp_path) is True


# ── setup_index_command (--shared flag registration) ──────


class TestSetupSharedFlag:
    def test_shared_flag_registered(self) -> None:
        """--shared flag is available in the argument parser."""
        parser = argparse.ArgumentParser()
        subs = parser.add_subparsers()
        setup_index_command(subs)
        args = parser.parse_args(["index", "--shared"])
        assert args.shared is True

    def test_shared_defaults_false(self) -> None:
        parser = argparse.ArgumentParser()
        subs = parser.add_subparsers()
        setup_index_command(subs)
        args = parser.parse_args(["index"])
        assert args.shared is False


# ── _index_shared_collections ─────────────────────────────


_PATCH_STORE = "core.memory.rag.store.ChromaVectorStore"
_PATCH_INDEXER = "core.memory.rag.MemoryIndexer"
_PATCH_VDBDIR = "core.paths.get_anima_vectordb_dir"


class TestIndexSharedCollections:
    @pytest.fixture
    def base_dir(self, tmp_path: Path) -> Path:
        """Set up a minimal base directory with common_knowledge."""
        d = tmp_path / "data"
        d.mkdir(exist_ok=True)
        ck = d / "common_knowledge"
        ck.mkdir(exist_ok=True)
        (ck / "ref.md").write_text("# Reference")
        return d

    @pytest.fixture
    def anima_dirs(self, base_dir: Path) -> list[Path]:
        animas = base_dir / "animas"
        alice = animas / "alice"
        alice.mkdir(parents=True, exist_ok=True)
        bob = animas / "bob"
        bob.mkdir(parents=True, exist_ok=True)
        return [alice, bob]

    def test_dry_run_does_not_write_meta(
        self, anima_dirs: list[Path], base_dir: Path, tmp_path: Path,
    ) -> None:
        with patch(_PATCH_STORE), \
             patch(_PATCH_INDEXER), \
             patch(_PATCH_VDBDIR, return_value=tmp_path / "vdb"):
            _index_shared_collections(
                anima_dirs, base_dir, full=False, dry_run=True,
            )
        for d in anima_dirs:
            assert not (d / "index_meta.json").exists()

    def test_indexes_into_each_anima_db(
        self, anima_dirs: list[Path], base_dir: Path, tmp_path: Path,
    ) -> None:
        with patch(_PATCH_STORE), \
             patch(_PATCH_INDEXER) as MockIdx, \
             patch(_PATCH_VDBDIR, return_value=tmp_path / "vdb"):
            mock_indexer = MagicMock()
            mock_indexer.index_directory.return_value = 3
            MockIdx.return_value = mock_indexer

            total = _index_shared_collections(
                anima_dirs, base_dir, full=False, dry_run=False,
            )

        assert total == 3 * len(anima_dirs)
        for d in anima_dirs:
            meta_path = d / "index_meta.json"
            assert meta_path.exists()
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            assert "shared_common_knowledge_hash" in data

    def test_skips_when_no_shared_dirs(self, tmp_path: Path) -> None:
        """Returns 0 when common_knowledge/ and common_skills/ don't exist."""
        base = tmp_path / "empty"
        base.mkdir()
        total = _index_shared_collections([], base, full=False, dry_run=False)
        assert total == 0

    def test_hash_skip_on_second_call(
        self, anima_dirs: list[Path], base_dir: Path, tmp_path: Path,
    ) -> None:
        """Second call with unchanged files skips indexing."""
        with patch(_PATCH_STORE), \
             patch(_PATCH_INDEXER) as MockIdx, \
             patch(_PATCH_VDBDIR, return_value=tmp_path / "vdb"):
            mock_indexer = MagicMock()
            mock_indexer.index_directory.return_value = 3
            MockIdx.return_value = mock_indexer

            _index_shared_collections(
                anima_dirs, base_dir, full=False, dry_run=False,
            )
            MockIdx.reset_mock()

            _index_shared_collections(
                anima_dirs, base_dir, full=False, dry_run=False,
            )
            MockIdx.assert_not_called()

    def test_full_flag_forces_reindex(
        self, anima_dirs: list[Path], base_dir: Path, tmp_path: Path,
    ) -> None:
        """--full ignores stored hash and re-indexes."""
        with patch(_PATCH_STORE), \
             patch(_PATCH_INDEXER) as MockIdx, \
             patch(_PATCH_VDBDIR, return_value=tmp_path / "vdb"):
            mock_indexer = MagicMock()
            mock_indexer.index_directory.return_value = 2
            MockIdx.return_value = mock_indexer

            _index_shared_collections(
                anima_dirs, base_dir, full=False, dry_run=False,
            )
            MockIdx.reset_mock()
            mock_indexer.reset_mock()
            mock_indexer.index_directory.return_value = 2
            MockIdx.return_value = mock_indexer

            total = _index_shared_collections(
                anima_dirs, base_dir, full=True, dry_run=False,
            )
            assert total == 2 * len(anima_dirs)
