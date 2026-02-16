from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of AnimaWorks core/server, licensed under AGPL-3.0.
# See LICENSES/AGPL-3.0.txt for the full license text.


"""Active forgetting mechanism based on synaptic homeostasis hypothesis.

Implements three stages of memory forgetting:
1. Synaptic downscaling (daily): Mark low-activation chunks
2. Neurogenesis reorganization (weekly): Merge similar low-activation chunks
3. Complete forgetting (monthly): Archive and delete forgotten memories

Based on:
- Tononi & Cirelli (2003, 2006): Synaptic homeostasis hypothesis
- Frankland et al. (2013): Hippocampal neurogenesis and active forgetting
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("animaworks.forgetting")

# ── Configuration ──────────────────────────────────────────────────

# Synaptic downscaling thresholds
DOWNSCALING_DAYS_THRESHOLD = 90  # Days since last access
DOWNSCALING_ACCESS_THRESHOLD = 3  # Minimum access count to avoid marking

# Neurogenesis reorganization
REORGANIZATION_SIMILARITY_THRESHOLD = 0.80  # Vector similarity for merging

# Complete forgetting
FORGETTING_LOW_ACTIVATION_DAYS = 60  # Days in low activation before deletion

# Protected memory types (procedural memory has higher forgetting resistance)
PROTECTED_MEMORY_TYPES = frozenset({"procedures", "skills", "shared_users"})


# ── ForgettingEngine ───────────────────────────────────────────────


class ForgettingEngine:
    """Active forgetting based on synaptic homeostasis and neurogenesis."""

    def __init__(self, anima_dir: Path, anima_name: str) -> None:
        self.anima_dir = anima_dir
        self.anima_name = anima_name
        self.archive_dir = anima_dir / "archive" / "forgotten"

    def _is_protected(self, metadata: dict) -> bool:
        """Check if a chunk is protected from forgetting."""
        if metadata.get("memory_type") in PROTECTED_MEMORY_TYPES:
            return True
        if metadata.get("importance") == "important":
            return True
        return False

    def _get_vector_store(self):
        """Get vector store singleton."""
        from core.memory.rag.singleton import get_vector_store
        return get_vector_store()

    def _get_all_chunks(self, collection_name: str) -> list[dict]:
        """Get all chunks from a collection with their metadata."""
        try:
            store = self._get_vector_store()
            coll = store.client.get_collection(name=collection_name)
            result = coll.get(include=["metadatas", "documents"])
            chunks = []
            if result["ids"]:
                for i, doc_id in enumerate(result["ids"]):
                    chunks.append({
                        "id": doc_id,
                        "metadata": result["metadatas"][i] if result["metadatas"] else {},
                        "content": result["documents"][i] if result["documents"] else "",
                    })
            return chunks
        except Exception as e:
            logger.warning("Failed to get chunks from %s: %s", collection_name, e)
            return []

    # ── Stage 1: Synaptic Downscaling (Daily) ──────────────────────

    def synaptic_downscaling(self) -> dict[str, Any]:
        """Mark low-activation chunks (daily, runs in daily_consolidate).

        Criteria: days_since_access > 90 AND access_count < 3
        Action: Set activation_level="low", record low_activation_since
        Skip: Protected memory types, important chunks, already low
        """
        logger.info("Starting synaptic downscaling for anima=%s", self.anima_name)
        now = datetime.now()
        now_iso = now.isoformat()
        total_scanned = 0
        total_marked = 0
        store = self._get_vector_store()

        # Scan all relevant collections
        for memory_type in ("knowledge", "episodes"):
            collection_name = f"{self.anima_name}_{memory_type}"
            chunks = self._get_all_chunks(collection_name)
            total_scanned += len(chunks)

            ids_to_mark: list[str] = []
            metas_to_mark: list[dict] = []

            for chunk in chunks:
                meta = chunk["metadata"]

                # Skip protected
                if self._is_protected(meta):
                    continue

                # Skip already low
                if meta.get("activation_level") == "low":
                    continue

                # Check access recency
                access_count = int(meta.get("access_count", 0))
                last_accessed_str = meta.get("last_accessed_at", "")

                if last_accessed_str:
                    try:
                        last_accessed = datetime.fromisoformat(str(last_accessed_str))
                        days_since = (now - last_accessed).total_seconds() / 86400.0
                    except (ValueError, TypeError):
                        days_since = float("inf")
                else:
                    # Never accessed — use updated_at as fallback
                    updated_str = meta.get("updated_at", "")
                    if updated_str:
                        try:
                            updated_at = datetime.fromisoformat(str(updated_str))
                            days_since = (now - updated_at).total_seconds() / 86400.0
                        except (ValueError, TypeError):
                            days_since = float("inf")
                    else:
                        days_since = float("inf")

                # Apply threshold
                if days_since > DOWNSCALING_DAYS_THRESHOLD and access_count < DOWNSCALING_ACCESS_THRESHOLD:
                    ids_to_mark.append(chunk["id"])
                    metas_to_mark.append({
                        "activation_level": "low",
                        "low_activation_since": now_iso,
                    })

            # Batch update
            if ids_to_mark:
                try:
                    store.update_metadata(collection_name, ids_to_mark, metas_to_mark)
                    total_marked += len(ids_to_mark)
                    logger.info(
                        "Marked %d chunks as low-activation in %s",
                        len(ids_to_mark), collection_name,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to mark chunks in %s: %s", collection_name, e,
                    )

        result = {
            "scanned": total_scanned,
            "marked_low": total_marked,
        }
        logger.info(
            "Synaptic downscaling complete for anima=%s: scanned=%d, marked=%d",
            self.anima_name, total_scanned, total_marked,
        )
        return result

    # ── Stage 2: Neurogenesis Reorganization (Weekly) ──────────────

    async def neurogenesis_reorganize(
        self,
        model: str = "anthropic/claude-sonnet-4-20250514",
    ) -> dict[str, Any]:
        """Merge similar low-activation chunks (weekly, runs in weekly_integrate).

        Criteria: activation_level=="low" AND pairwise vector similarity >= 0.8
        Action: LLM merge -> delete originals -> insert merged chunk
        """
        logger.info("Starting neurogenesis reorganization for anima=%s", self.anima_name)
        store = self._get_vector_store()
        total_merged = 0
        merged_pairs: list[str] = []

        for memory_type in ("knowledge", "episodes"):
            collection_name = f"{self.anima_name}_{memory_type}"
            chunks = self._get_all_chunks(collection_name)

            # Filter low-activation chunks
            low_chunks = [
                c for c in chunks
                if c["metadata"].get("activation_level") == "low"
                and not self._is_protected(c["metadata"])
            ]

            if len(low_chunks) < 2:
                continue

            # Find similar pairs using vector similarity
            similar_pairs = self._find_similar_pairs(
                low_chunks, collection_name, store,
            )

            if not similar_pairs:
                continue

            # Merge each pair via LLM
            for chunk_a, chunk_b, similarity in similar_pairs:
                try:
                    merged_content = await self._merge_chunks_llm(
                        chunk_a, chunk_b, similarity, model,
                    )
                    if merged_content:
                        # Delete originals
                        store.delete_documents(
                            collection_name, [chunk_a["id"], chunk_b["id"]],
                        )
                        # Index merged content
                        self._index_merged_chunk(
                            merged_content, chunk_a, memory_type,
                        )
                        total_merged += 1
                        merged_pairs.append(
                            f"{chunk_a['id']} + {chunk_b['id']}"
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to merge chunks %s and %s: %s",
                        chunk_a["id"], chunk_b["id"], e,
                    )

        result = {
            "merged_count": total_merged,
            "merged_pairs": merged_pairs,
        }
        logger.info(
            "Neurogenesis reorganization complete for anima=%s: merged=%d",
            self.anima_name, total_merged,
        )
        return result

    def _find_similar_pairs(
        self,
        chunks: list[dict],
        collection_name: str,
        store,
    ) -> list[tuple[dict, dict, float]]:
        """Find pairs of low-activation chunks with high vector similarity."""
        from core.memory.rag.singleton import get_embedding_model

        pairs: list[tuple[dict, dict, float]] = []
        processed_ids: set[str] = set()

        try:
            embedding_model = get_embedding_model()
            for i, chunk_a in enumerate(chunks):
                if chunk_a["id"] in processed_ids:
                    continue

                # Generate embedding for chunk_a
                embedding = embedding_model.encode(
                    [chunk_a["content"]],
                    convert_to_numpy=True,
                    show_progress_bar=False,
                )[0].tolist()

                # Query for similar chunks
                results = store.query(
                    collection=collection_name,
                    embedding=embedding,
                    top_k=5,
                )

                for r in results:
                    other_id = r.document.id
                    if other_id == chunk_a["id"] or other_id in processed_ids:
                        continue

                    # Check if the other chunk is also low-activation
                    other_chunk = next(
                        (c for c in chunks if c["id"] == other_id), None,
                    )
                    if other_chunk is None:
                        continue

                    similarity = r.score
                    if similarity >= REORGANIZATION_SIMILARITY_THRESHOLD:
                        pairs.append((chunk_a, other_chunk, similarity))
                        processed_ids.add(chunk_a["id"])
                        processed_ids.add(other_id)
                        break  # One merge per chunk per cycle

        except Exception as e:
            logger.warning("Failed to find similar pairs: %s", e)

        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs

    async def _merge_chunks_llm(
        self,
        chunk_a: dict,
        chunk_b: dict,
        similarity: float,
        model: str,
    ) -> str | None:
        """Merge two chunks using LLM."""
        prompt = f"""以下は同一人物の記憶システムにある、類似した2つの記憶断片です。

【記憶断片1】
{chunk_a['content']}

【記憶断片2】
{chunk_b['content']}

類似度: {similarity:.2f}

タスク: この2つの記憶を1つに統合してください。
- 重複する情報は1つにまとめる
- 両方の重要な情報を保持する
- 簡潔にまとめる

統合された記憶のみを出力してください（説明不要）:"""

        try:
            import litellm

            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return response.choices[0].message.content or None
        except Exception as e:
            logger.warning("LLM merge failed: %s", e)
            return None

    def _index_merged_chunk(
        self,
        content: str,
        source_chunk: dict,
        memory_type: str,
    ) -> None:
        """Index a merged chunk back into the vector store."""
        try:
            from core.memory.rag.indexer import MemoryIndexer
            from core.memory.rag.singleton import get_vector_store
            from core.memory.rag.store import Document

            store = get_vector_store()
            indexer = MemoryIndexer(store, self.anima_name, self.anima_dir)

            # Generate new ID
            merged_id = f"{self.anima_name}/{memory_type}/merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}#0"

            embedding = indexer._generate_embeddings([content])[0]

            now_iso = datetime.now().isoformat()
            metadata = {
                "anima": self.anima_name,
                "memory_type": memory_type,
                "source_file": "merged",
                "chunk_index": 0,
                "total_chunks": 1,
                "created_at": now_iso,
                "updated_at": now_iso,
                "importance": "normal",
                "access_count": 0,
                "last_accessed_at": "",
                "activation_level": "normal",
                "low_activation_since": "",
            }

            doc = Document(id=merged_id, content=content, embedding=embedding, metadata=metadata)
            collection_name = f"{self.anima_name}_{memory_type}"
            store.upsert(collection_name, [doc])

            logger.debug("Indexed merged chunk: %s", merged_id)

        except Exception as e:
            logger.warning("Failed to index merged chunk: %s", e)

    # ── Stage 3: Complete Forgetting (Monthly) ─────────────────────

    def complete_forgetting(self) -> dict[str, Any]:
        """Archive and delete chunks that remain low-activation (monthly).

        Criteria: low_activation_since > 60 days ago AND access_count == 0
        Action: Move source file to archive/forgotten/, delete from vector index
        """
        logger.info("Starting complete forgetting for anima=%s", self.anima_name)
        now = datetime.now()
        store = self._get_vector_store()
        total_forgotten = 0
        archived_files: list[str] = []

        for memory_type in ("knowledge", "episodes"):
            collection_name = f"{self.anima_name}_{memory_type}"
            chunks = self._get_all_chunks(collection_name)

            ids_to_delete: list[str] = []
            source_files_to_archive: set[str] = set()

            for chunk in chunks:
                meta = chunk["metadata"]

                # Skip protected
                if self._is_protected(meta):
                    continue

                # Must be low activation
                if meta.get("activation_level") != "low":
                    continue

                # Check duration of low activation
                low_since_str = meta.get("low_activation_since", "")
                if not low_since_str:
                    continue

                try:
                    low_since = datetime.fromisoformat(str(low_since_str))
                    days_low = (now - low_since).total_seconds() / 86400.0
                except (ValueError, TypeError):
                    continue

                # Check criteria
                access_count = int(meta.get("access_count", 0))
                if days_low > FORGETTING_LOW_ACTIVATION_DAYS and access_count == 0:
                    ids_to_delete.append(chunk["id"])
                    source_file = meta.get("source_file", "")
                    if source_file and source_file != "merged":
                        source_files_to_archive.add(source_file)

            # Archive source files
            for source_file in source_files_to_archive:
                self._archive_source_file(source_file)
                archived_files.append(source_file)

            # Delete from vector index
            if ids_to_delete:
                try:
                    store.delete_documents(collection_name, ids_to_delete)
                    total_forgotten += len(ids_to_delete)
                    logger.info(
                        "Deleted %d forgotten chunks from %s",
                        len(ids_to_delete), collection_name,
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to delete chunks from %s: %s", collection_name, e,
                    )

        result = {
            "forgotten_chunks": total_forgotten,
            "archived_files": archived_files,
        }
        logger.info(
            "Complete forgetting done for anima=%s: forgotten=%d, archived=%d files",
            self.anima_name, total_forgotten, len(archived_files),
        )
        return result

    def _archive_source_file(self, relative_path: str) -> None:
        """Move source file to archive/forgotten/ directory."""
        source_path = self.anima_dir / relative_path
        if not source_path.exists():
            return

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        dest_path = self.archive_dir / source_path.name

        # Add timestamp suffix if destination exists
        if dest_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = self.archive_dir / f"{source_path.stem}_{timestamp}{source_path.suffix}"

        try:
            shutil.move(str(source_path), str(dest_path))
            logger.info("Archived forgotten file: %s -> %s", relative_path, dest_path.name)
        except Exception as e:
            logger.warning("Failed to archive %s: %s", relative_path, e)
