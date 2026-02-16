from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Process-level singletons for RAG components.

Ensures ChromaVectorStore and SentenceTransformer embedding model
are initialized only once per process, avoiding costly repeated
model loading (~6 seconds per initialization).
"""

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_vector_store = None
_embedding_model = None


def get_vector_store():
    """Return process-level singleton ChromaVectorStore."""
    global _vector_store
    if _vector_store is None:
        with _lock:
            if _vector_store is None:
                from core.memory.rag.store import ChromaVectorStore
                _vector_store = ChromaVectorStore()
    return _vector_store


def get_embedding_model(model_name: str = "intfloat/multilingual-e5-small"):
    """Return process-level singleton SentenceTransformer model."""
    global _embedding_model
    if _embedding_model is None:
        with _lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer
                from core.paths import get_data_dir
                cache_dir = get_data_dir() / "models"
                cache_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Loading embedding model (singleton): %s", model_name)
                _embedding_model = SentenceTransformer(
                    model_name, cache_folder=str(cache_dir)
                )
                logger.info("Embedding model loaded (singleton)")
    return _embedding_model


def _reset_for_testing():
    """Reset singletons for test isolation."""
    global _vector_store, _embedding_model
    with _lock:
        _vector_store = None
        _embedding_model = None
