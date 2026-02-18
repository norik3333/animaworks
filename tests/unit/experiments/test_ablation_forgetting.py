from __future__ import annotations

"""Unit tests for Forgetting ON/OFF ablation experiment."""

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ── Ensure numpy is available for SearchMetrics import ────
_numpy_stub = None
if "numpy" not in sys.modules:
    _numpy_stub = ModuleType("numpy")
    _numpy_stub.log2 = lambda x: __import__("math").log2(x)  # type: ignore[attr-defined]
    _numpy_stub.mean = lambda x: sum(x) / len(x)  # type: ignore[attr-defined]
    _numpy_stub.median = lambda x: sorted(x)[len(x) // 2]  # type: ignore[attr-defined]
    _numpy_stub.std = lambda x: 0.0  # type: ignore[attr-defined]
    _numpy_stub.min = min  # type: ignore[attr-defined]
    _numpy_stub.max = max  # type: ignore[attr-defined]
    _numpy_stub.percentile = lambda x, p: 0.0  # type: ignore[attr-defined]
    sys.modules["numpy"] = _numpy_stub

from experiments.memory_eval.ablation.forgetting import (
    ForgettingAblation,
    ForgettingAblationResult,
    ForgettingQueryResult,
)


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def dataset_dir(tmp_path):
    """Create a minimal dataset for testing."""
    ds = tmp_path / "dataset"

    # Knowledge files
    knowledge_dir = ds / "knowledge"
    knowledge_dir.mkdir(parents=True)
    for i in range(3):
        (knowledge_dir / f"doc_{i}.md").write_text(
            "---\n"
            "created_at: '2026-02-01'\n"
            "updated_at: '2026-02-10'\n"
            "confidence: 0.8\n"
            "version: 1\n"
            "access_count: 5\n"
            "---\n\n"
            f"# Document {i}\nImportant knowledge about topic {i}.\n",
            encoding="utf-8",
        )

    # Noise files (old dates, low access)
    noise_dir = ds / "noise"
    noise_dir.mkdir(parents=True)
    for i in range(5):
        (noise_dir / f"noise_{i:04d}.md").write_text(
            "---\n"
            "created_at: '2025-06-01'\n"
            "updated_at: '2025-06-15'\n"
            "confidence: 0.3\n"
            "version: 1\n"
            "access_count: 0\n"
            "---\n\n"
            f"# Noise {i}\nIrrelevant old content {i}.\n",
            encoding="utf-8",
        )

    # Queries
    queries = {
        "queries": [
            {
                "id": "q1",
                "type": "factual",
                "text": "What is topic 0?",
                "relevant_files": ["knowledge/doc_0.md"],
                "expected_answer_keywords": ["topic 0"],
            },
            {
                "id": "q2",
                "type": "factual",
                "text": "Tell me about topic 1",
                "relevant_files": ["knowledge/doc_1.md"],
                "expected_answer_keywords": ["topic 1"],
            },
        ],
    }
    (ds / "queries.json").write_text(
        json.dumps(queries, ensure_ascii=False),
        encoding="utf-8",
    )

    return ds


@pytest.fixture
def output_dir(tmp_path):
    """Output directory for results."""
    out = tmp_path / "output"
    out.mkdir()
    return out


# ── Data structure tests ─────────────────────────────────────────


class TestForgettingQueryResult:
    """Tests for ForgettingQueryResult dataclass."""

    def test_defaults(self):
        """Default values should be zeros/empty."""
        r = ForgettingQueryResult(query_id="q1", query_text="test")
        assert r.forgetting_precision_at_3 == 0.0
        assert r.baseline_precision_at_3 == 0.0
        assert r.forgetting_retrieved_ids == []


class TestForgettingAblationResult:
    """Tests for ForgettingAblationResult dataclass."""

    def test_defaults(self):
        """Default aggregates should be zero."""
        r = ForgettingAblationResult()
        assert r.n_queries == 0
        assert r.initial_memory_count == 0
        assert r.forgetting_downscaled == 0
        assert r.precision_at_3_delta == 0.0


# ── Ground truth matching ────────────────────────────────────────


class TestMatchDocIds:
    """Tests for ground truth matching logic."""

    def test_match_by_stem(self):
        """Should match by filename stem."""
        retrieved = ["eval_forgetting/knowledge/doc_0.md#0"]
        relevant = ["knowledge/doc_0.md"]
        matched = ForgettingAblation._match_doc_ids(retrieved, relevant)
        assert matched == ["knowledge/doc_0.md"]

    def test_no_match(self):
        """Non-matching should return empty."""
        matched = ForgettingAblation._match_doc_ids(
            ["eval_forgetting/knowledge/noise.md#0"],
            ["knowledge/doc_0.md"],
        )
        assert matched == []


# ── Noise injection ──────────────────────────────────────────────


class TestNoiseInjection:
    """Tests for noise injection into knowledge directory."""

    def test_noise_increases_file_count(self, dataset_dir, tmp_path):
        """Injecting noise should increase the number of files."""
        ablation = ForgettingAblation(dataset_dir, tmp_path / "out")
        ablation._load_queries()

        # Without noise
        work_no_noise = tmp_path / "work_no_noise"
        work_no_noise.mkdir()
        with patch("core.memory.rag.store.ChromaVectorStore"), \
             patch("core.memory.rag.indexer.MemoryIndexer") as mock_ix, \
             patch("core.memory.rag.retriever.MemoryRetriever"):
            mock_ix.return_value.index_directory = MagicMock()
            anima_dir_no, _, _, _ = ablation._setup_env(work_no_noise, inject_noise=False)

        count_no_noise = len(list((anima_dir_no / "knowledge").glob("*.md")))

        # With noise
        work_noise = tmp_path / "work_noise"
        work_noise.mkdir()
        with patch("core.memory.rag.store.ChromaVectorStore"), \
             patch("core.memory.rag.indexer.MemoryIndexer") as mock_ix2, \
             patch("core.memory.rag.retriever.MemoryRetriever"):
            mock_ix2.return_value.index_directory = MagicMock()
            anima_dir_noise, _, _, _ = ablation._setup_env(work_noise, inject_noise=True)

        count_with_noise = len(list((anima_dir_noise / "knowledge").glob("*.md")))

        assert count_with_noise > count_no_noise
        assert count_with_noise == count_no_noise + 5  # 5 noise files


# ── Query evaluation ─────────────────────────────────────────────


class TestEvaluateQueries:
    """Tests for query evaluation logic."""

    def test_evaluate_queries_calculates_metrics(self, dataset_dir, output_dir):
        """_evaluate_queries should calculate precision and recall."""
        ablation = ForgettingAblation(dataset_dir, output_dir)
        ablation._load_queries()

        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(return_value=[
            MagicMock(doc_id="eval_forgetting/knowledge/doc_0.md#0"),
        ])

        result = ablation._evaluate_queries(mock_retriever)

        assert "avg_precision_at_3" in result
        assert "avg_precision_at_5" in result
        assert "avg_recall_at_5" in result
        assert len(result["query_results"]) == 2

    def test_evaluate_handles_search_error(self, dataset_dir, output_dir):
        """Should handle search errors gracefully per query."""
        ablation = ForgettingAblation(dataset_dir, output_dir)
        ablation._load_queries()

        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(side_effect=RuntimeError("search failed"))

        result = ablation._evaluate_queries(mock_retriever)

        # Should still return results (with zero metrics)
        assert len(result["query_results"]) == 2


# ── Full run test ────────────────────────────────────────────────


class TestFullRun:
    """Tests for complete ablation run."""

    def test_run_saves_json(self, dataset_dir, output_dir, tmp_path):
        """run() should save results to output directory."""
        ablation = ForgettingAblation(dataset_dir, output_dir)
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Mock everything
        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(return_value=[])

        mock_store = MagicMock()
        mock_indexer = MagicMock()
        mock_indexer.index_directory = MagicMock()

        with patch("core.memory.rag.store.ChromaVectorStore", return_value=mock_store), \
             patch("core.memory.rag.indexer.MemoryIndexer", return_value=mock_indexer), \
             patch("core.memory.rag.retriever.MemoryRetriever", return_value=mock_retriever), \
             patch("core.memory.forgetting.ForgettingEngine") as mock_fe:

            mock_engine = MagicMock()
            mock_engine.synaptic_downscaling = MagicMock(
                return_value={"scanned": 8, "marked_low": 3},
            )
            mock_engine.complete_forgetting = MagicMock(
                return_value={"forgotten_chunks": 2, "archived_files": ["noise_0001.md"]},
            )
            mock_fe.return_value = mock_engine

            result = ablation.run(work_dir)

        assert isinstance(result, ForgettingAblationResult)
        assert result.n_queries == 2
        assert result.timestamp != ""

        # Check output file
        output_file = output_dir / "forgetting_ablation_result.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["n_queries"] == 2

    def test_run_result_structure(self, dataset_dir, output_dir, tmp_path):
        """Run result should have proper ON/OFF comparison."""
        ablation = ForgettingAblation(dataset_dir, output_dir)
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(return_value=[])

        with patch("core.memory.rag.store.ChromaVectorStore"), \
             patch("core.memory.rag.indexer.MemoryIndexer") as mock_ix, \
             patch("core.memory.rag.retriever.MemoryRetriever", return_value=mock_retriever), \
             patch("core.memory.forgetting.ForgettingEngine") as mock_fe:

            mock_ix.return_value.index_directory = MagicMock()
            mock_engine = MagicMock()
            mock_engine.synaptic_downscaling = MagicMock(return_value={"marked_low": 0})
            mock_engine.complete_forgetting = MagicMock(
                return_value={"forgotten_chunks": 0, "archived_files": []},
            )
            mock_fe.return_value = mock_engine

            result = ablation.run(work_dir)

        # Verify delta calculation
        expected_delta = (
            result.forgetting_precision_at_3 - result.baseline_precision_at_3
        )
        assert abs(result.precision_at_3_delta - expected_delta) < 0.001
