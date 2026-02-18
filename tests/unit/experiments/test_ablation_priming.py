from __future__ import annotations

"""Unit tests for Priming ON/OFF ablation experiment."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _chromadb_available() -> bool:
    """Check if ChromaDB is importable."""
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False


# ── Ensure SearchMetrics is importable (mock numpy if needed) ────

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

from experiments.memory_eval.ablation.priming import (
    PrimingAblation,
    PrimingAblationResult,
    PrimingQueryResult,
)
from tests.evaluation.framework.metrics import SearchMetrics


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
            f"---\ncreated_at: '2026-01-01'\nversion: 1\n---\n\n# Doc {i}\nContent about topic {i}.\n",
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


class TestPrimingQueryResult:
    """Tests for PrimingQueryResult dataclass."""

    def test_defaults(self):
        """Default values should be zeros/empty."""
        r = PrimingQueryResult(
            query_id="q1", query_text="test", query_type="factual",
        )
        assert r.priming_tokens == 0
        assert r.priming_precision_at_3 == 0.0
        assert r.baseline_precision_at_3 == 0.0
        assert r.priming_retrieved_ids == []
        assert r.baseline_retrieved_ids == []


class TestPrimingAblationResult:
    """Tests for PrimingAblationResult dataclass."""

    def test_defaults(self):
        """Default aggregates should be zero."""
        r = PrimingAblationResult()
        assert r.n_queries == 0
        assert r.avg_priming_precision_at_3 == 0.0
        assert r.precision_at_3_delta == 0.0
        assert r.query_results == []


# ── Ground truth matching ────────────────────────────────────────


class TestMatchDocIds:
    """Tests for ground truth matching logic."""

    def test_exact_match(self):
        """Doc IDs containing the full relevant path should match."""
        retrieved = [
            "eval_priming/knowledge/doc_0.md#0",
            "eval_priming/knowledge/doc_1.md#0",
        ]
        relevant = ["knowledge/doc_0.md"]
        matched = PrimingAblation._match_doc_ids(retrieved, relevant)
        assert matched == ["knowledge/doc_0.md"]

    def test_stem_match(self):
        """Matching by filename stem should work."""
        retrieved = [
            "eval_priming/knowledge/company_remote_work_policy.md#0",
        ]
        relevant = ["knowledge/company_remote_work_policy.md"]
        matched = PrimingAblation._match_doc_ids(retrieved, relevant)
        assert len(matched) == 1

    def test_no_match(self):
        """Non-matching doc IDs should not be matched."""
        retrieved = ["eval_priming/knowledge/unrelated.md#0"]
        relevant = ["knowledge/doc_0.md"]
        matched = PrimingAblation._match_doc_ids(retrieved, relevant)
        assert matched == []

    def test_empty_retrieved(self):
        """Empty retrieved list should return empty matches."""
        matched = PrimingAblation._match_doc_ids([], ["knowledge/doc_0.md"])
        assert matched == []


# ── Setup tests ──────────────────────────────────────────────────


class TestPrimingAblationSetup:
    """Tests for PrimingAblation setup."""

    @pytest.mark.skipif(
        not _chromadb_available(),
        reason="ChromaDB not available",
    )
    @pytest.mark.asyncio
    async def test_setup_creates_anima_dir(self, dataset_dir, output_dir, tmp_path):
        """Setup should create anima directory structure."""
        ablation = PrimingAblation(dataset_dir, output_dir)
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        await ablation.setup(work_dir)

        anima_dir = work_dir / "animas" / "eval_priming"
        assert anima_dir.exists()
        assert (anima_dir / "knowledge").exists()
        assert ablation._anima_dir == anima_dir

    @pytest.mark.asyncio
    async def test_setup_loads_queries(self, dataset_dir, output_dir, tmp_path):
        """Setup should load queries from queries.json."""
        ablation = PrimingAblation(dataset_dir, output_dir)
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        # Mock the RAG components to avoid ChromaDB dependency
        with patch("core.memory.rag.store.ChromaVectorStore"), \
             patch("core.memory.rag.indexer.MemoryIndexer"), \
             patch("core.memory.rag.retriever.MemoryRetriever"), \
             patch("core.memory.priming.PrimingEngine"):
            await ablation.setup(work_dir)

        assert len(ablation._queries) == 2

    @pytest.mark.asyncio
    async def test_setup_missing_queries(self, tmp_path, output_dir):
        """Setup should handle missing queries.json gracefully."""
        empty_dataset = tmp_path / "empty_dataset"
        empty_dataset.mkdir()

        ablation = PrimingAblation(empty_dataset, output_dir)
        work_dir = tmp_path / "work"
        work_dir.mkdir()

        with patch("core.memory.rag.store.ChromaVectorStore"), \
             patch("core.memory.rag.indexer.MemoryIndexer"), \
             patch("core.memory.rag.retriever.MemoryRetriever"), \
             patch("core.memory.priming.PrimingEngine"):
            await ablation.setup(work_dir)

        assert ablation._queries == []


# ── Run tests with mocks ─────────────────────────────────────────


@dataclass
class _MockPrimingResult:
    """Minimal mock for PrimingResult."""

    related_knowledge: str = ""
    sender_profile: str = ""
    recent_activity: str = ""
    matched_skills: list[str] = None

    def __post_init__(self):
        if self.matched_skills is None:
            self.matched_skills = []

    def estimated_tokens(self) -> int:
        return max(1, len(self.related_knowledge) // 4)


@dataclass
class _MockSearchResult:
    """Minimal mock for MemoryRetriever search result."""

    doc_id: str
    score: float = 0.8
    content: str = ""


class TestRunWithPriming:
    """Tests for run_with_priming method."""

    @pytest.mark.asyncio
    async def test_returns_query_results(self, dataset_dir, output_dir):
        """run_with_priming should return one result per query."""
        ablation = PrimingAblation(dataset_dir, output_dir)

        ablation._queries = [
            {"id": "q1", "type": "factual", "text": "What is topic 0?",
             "relevant_files": ["knowledge/doc_0.md"]},
        ]

        mock_priming = AsyncMock()
        mock_priming.prime_memories = AsyncMock(return_value=_MockPrimingResult(
            related_knowledge="Content about doc_0",
        ))
        ablation._priming_engine = mock_priming

        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(return_value=[
            _MockSearchResult(doc_id="eval_priming/knowledge/doc_0.md#0"),
        ])
        ablation._retriever = mock_retriever

        results = await ablation.run_with_priming()

        assert len(results) == 1
        assert results[0].query_id == "q1"
        assert results[0].priming_tokens > 0

    @pytest.mark.asyncio
    async def test_handles_priming_error(self, dataset_dir, output_dir):
        """Should handle priming engine errors gracefully."""
        ablation = PrimingAblation(dataset_dir, output_dir)
        ablation._queries = [
            {"id": "q1", "type": "factual", "text": "query",
             "relevant_files": ["knowledge/doc_0.md"]},
        ]

        mock_priming = AsyncMock()
        mock_priming.prime_memories = AsyncMock(side_effect=RuntimeError("API error"))
        ablation._priming_engine = mock_priming
        ablation._retriever = MagicMock()

        results = await ablation.run_with_priming()
        assert len(results) == 1
        assert results[0].priming_precision_at_3 == 0.0


class TestRunWithoutPriming:
    """Tests for run_without_priming method."""

    @pytest.mark.asyncio
    async def test_returns_baseline_results(self, dataset_dir, output_dir):
        """run_without_priming should return results without priming metrics."""
        ablation = PrimingAblation(dataset_dir, output_dir)
        ablation._queries = [
            {"id": "q1", "type": "factual", "text": "What is topic 0?",
             "relevant_files": ["knowledge/doc_0.md"]},
        ]

        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(return_value=[
            _MockSearchResult(doc_id="eval_priming/knowledge/doc_0.md#0"),
        ])
        ablation._retriever = mock_retriever

        results = await ablation.run_without_priming()

        assert len(results) == 1
        assert results[0].baseline_retrieved_ids == [
            "eval_priming/knowledge/doc_0.md#0",
        ]
        # Priming fields should remain at defaults
        assert results[0].priming_tokens == 0


# ── Full run test ────────────────────────────────────────────────


class TestFullRun:
    """Tests for the complete ablation run."""

    @pytest.mark.asyncio
    async def test_run_saves_json(self, dataset_dir, output_dir):
        """run() should save results to output directory."""
        ablation = PrimingAblation(dataset_dir, output_dir)
        ablation._queries = [
            {"id": "q1", "type": "factual", "text": "query",
             "relevant_files": ["knowledge/doc_0.md"]},
        ]

        # Mock both priming and retriever
        mock_priming = AsyncMock()
        mock_priming.prime_memories = AsyncMock(return_value=_MockPrimingResult())
        ablation._priming_engine = mock_priming

        mock_retriever = MagicMock()
        mock_retriever.search = MagicMock(return_value=[])
        ablation._retriever = mock_retriever

        result = await ablation.run()

        assert isinstance(result, PrimingAblationResult)
        assert result.n_queries == 1
        assert result.timestamp != ""

        # Check output file
        output_file = output_dir / "priming_ablation_result.json"
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["n_queries"] == 1

    @pytest.mark.asyncio
    async def test_run_empty_queries(self, tmp_path, output_dir):
        """run() with no queries should produce zero-value results."""
        empty_ds = tmp_path / "empty"
        empty_ds.mkdir()

        ablation = PrimingAblation(empty_ds, output_dir)
        ablation._queries = []
        ablation._priming_engine = AsyncMock()
        ablation._retriever = MagicMock()

        result = await ablation.run()
        assert result.n_queries == 0
        assert result.avg_priming_precision_at_3 == 0.0
