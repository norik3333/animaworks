"""Unit tests for core/memory/rag/singleton.py — RAG component singletons."""
from __future__ import annotations

import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons before and after each test for isolation."""
    from core.memory.rag.singleton import _reset_for_testing

    _reset_for_testing()
    yield
    _reset_for_testing()


@pytest.fixture
def mock_sentence_transformers():
    """Inject a mock sentence_transformers module into sys.modules.

    This allows patching SentenceTransformer even when the real
    sentence_transformers package is not installed.
    """
    mock_cls = MagicMock()
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.SentenceTransformer = mock_cls  # type: ignore[attr-defined]

    already_present = "sentence_transformers" in sys.modules
    original = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = mock_module
    yield mock_cls
    if already_present:
        sys.modules["sentence_transformers"] = original  # type: ignore[assignment]
    else:
        sys.modules.pop("sentence_transformers", None)


# ── get_vector_store ──────────────────────────────────────────────


class TestGetVectorStore:
    def test_returns_same_instance(self):
        """get_vector_store() should return the same instance on repeated calls."""
        mock_store = MagicMock()
        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store,
        ):
            from core.memory.rag.singleton import get_vector_store

            store1 = get_vector_store()
            store2 = get_vector_store()

        assert store1 is store2
        assert store1 is mock_store

    def test_creates_only_once(self):
        """ChromaVectorStore constructor should be called exactly once."""
        mock_cls = MagicMock()
        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            mock_cls,
        ):
            from core.memory.rag.singleton import get_vector_store

            get_vector_store()
            get_vector_store()
            get_vector_store()

        mock_cls.assert_called_once()


# ── get_embedding_model ──────────────────────────────────────────


class TestGetEmbeddingModel:
    def test_returns_same_instance(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """get_embedding_model() should return the same instance on repeated calls."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.singleton import get_embedding_model

        model1 = get_embedding_model()
        model2 = get_embedding_model()

        assert model1 is model2
        assert model1 is mock_model

    def test_creates_only_once(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """SentenceTransformer constructor should be called exactly once."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.singleton import get_embedding_model

        get_embedding_model()
        get_embedding_model()
        get_embedding_model()

        mock_sentence_transformers.assert_called_once()

    def test_creates_cache_dir(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """get_embedding_model() should create the models cache directory."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.singleton import get_embedding_model

        get_embedding_model()

        assert (tmp_path / "models").is_dir()


# ── _reset_for_testing ───────────────────────────────────────────


class TestResetForTesting:
    def test_reset_clears_singletons(self, tmp_path, monkeypatch):
        """_reset_for_testing() should allow re-creation of singletons."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_store_1 = MagicMock()
        mock_store_2 = MagicMock()

        from core.memory.rag.singleton import (
            _reset_for_testing,
            get_vector_store,
        )

        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store_1,
        ):
            store1 = get_vector_store()

        _reset_for_testing()

        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store_2,
        ):
            store2 = get_vector_store()

        assert store1 is not store2
        assert store1 is mock_store_1
        assert store2 is mock_store_2


# ── Thread safety ────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_get_vector_store(self):
        """Multiple threads calling get_vector_store() concurrently
        should all receive the same instance."""
        mock_store = MagicMock()
        results: list[object] = []
        errors: list[Exception] = []

        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store,
        ):
            from core.memory.rag.singleton import get_vector_store

            def worker():
                try:
                    store = get_vector_store()
                    results.append(store)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10
        assert all(r is mock_store for r in results)

    def test_concurrent_get_embedding_model(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """Multiple threads calling get_embedding_model() concurrently
        should all receive the same instance."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        results: list[object] = []
        errors: list[Exception] = []

        from core.memory.rag.singleton import get_embedding_model

        def worker():
            try:
                model = get_embedding_model()
                results.append(model)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10
        assert all(r is mock_model for r in results)


# ── MemoryIndexer integration ────────────────────────────────────


class TestMemoryIndexerEmbeddingInjection:
    def test_accepts_external_embedding_model(self, tmp_path):
        """MemoryIndexer should accept an externally provided embedding_model."""
        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        from core.memory.rag.indexer import MemoryIndexer

        indexer = MemoryIndexer(
            vector_store=mock_store,
            anima_name="test-anima",
            anima_dir=anima_dir,
            embedding_model=mock_model,
        )

        assert indexer.embedding_model is mock_model

    def test_skips_init_when_model_provided(self, tmp_path):
        """When embedding_model is provided, _init_embedding_model() should not be called."""
        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        with patch(
            "core.memory.rag.indexer.MemoryIndexer._init_embedding_model"
        ) as mock_init:
            from core.memory.rag.indexer import MemoryIndexer

            MemoryIndexer(
                vector_store=mock_store,
                anima_name="test-anima",
                anima_dir=anima_dir,
                embedding_model=mock_model,
            )

            mock_init.assert_not_called()

    def test_calls_singleton_when_no_model_provided(self, tmp_path, monkeypatch):
        """When no embedding_model is provided, _init_embedding_model() should
        use the singleton get_embedding_model()."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        with patch(
            "core.memory.rag.singleton.get_embedding_model",
            return_value=mock_model,
        ) as mock_get:
            from core.memory.rag.indexer import MemoryIndexer

            indexer = MemoryIndexer(
                vector_store=mock_store,
                anima_name="test-anima",
                anima_dir=anima_dir,
            )

            mock_get.assert_called_once()
            assert indexer.embedding_model is mock_model
