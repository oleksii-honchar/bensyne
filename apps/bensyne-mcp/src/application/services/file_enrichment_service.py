"""FileEnrichmentService — shared two-phase file enrichment (D7).

Extracted from `SearchFilesUseCase._enrich_memories` so that recall and
search can share one enrichment implementation. For every recalled/searched
memory the service probes the file layer:

- File-backed memory (a FileChunk row links it to a File) ⇒ the result gains
  a `file_enrichment` block built from REAL entity values:
    - `file`: the canonical file block via File.to_dict() (D24.1) — id, path,
      source_type, file_role, total_chunks, keywords, tags,
      average_importance, metadata, file_hash (the File row's stored hash;
      null for legacy rows)
    - `chunk_hash`: the recalled memory's chunk row content_hash (per-memory;
      null for legacy/absent rows — S7). Applied OUTSIDE the per-file cache so
      multiple memories of the same file each surface their own chunk hash.
    - `relations`: capped at `limit`, sorted strength-descending
    - `related_files`: per surviving relation's other end — id, path, summary, relation type
    - `summary_chain`: File.summary (or a mechanical path+keywords+tags fallback
      when File.summary is null) followed by the distinct parent-unit summaries
      of the file's chunks
    - `traversal`: {file_id, relation_ids} — handles for expandFileRelations/fetchFile
    - `source_type_enrichment`: extra keys from File.metadata (e.g. session.*);
      empty dict only when there are none
- Pure memory (no chunk row) ⇒ `file_enrichment: None` and every other field
  of the result is byte-identical to the input.

The service never throws across its boundary: lookup failures degrade to the
pure-memory form or empty collections, per D7.
"""

from __future__ import annotations

import structlog.stdlib

from src.application.services.file_service import FileService
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_entity import File
from src.domain.file_relation_entity import FileRelation
from src.utils.result import Result


class FileEnrichmentService:
    """Application service enriching memory results with file-layer context.

    Depends only on FileService read passthroughs (D11) — no concrete
    repository imports here; use cases later depend on THIS service.
    """

    def __init__(self, file_service: FileService, logger: structlog.stdlib.BoundLogger) -> None:
        self._file_service = file_service
        self._logger = logger

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enrich(self, memories: list[dict], limit: int = 5) -> list[dict]:
        """Enrich each memory result with a `file_enrichment` block.

        Args:
            memories: recall/search result rows (each a dict carrying at least an "id").
            limit: maximum number of relations per enrichment, strongest first.

        Returns:
            A new list of the same length; each row is a copy of the input row
            with exactly one added key, `file_enrichment` (None for pure memories).
            Input dicts are never mutated.
        """
        self._logger.info(
            "Enriching memories",
            service="file_enrichment_service",
            method="enrich",
            memories_count=len(memories),
            limit=limit,
        )

        # Cache per-file enrichments so multiple memories of the same file
        # share one lookup pass.
        cache: dict[str, dict] = {}
        results: list[dict] = []
        for memory in memories:
            results.append(self._enrich_one(memory, limit, cache))

        self._logger.debug(
            "Enrichment completed",
            service="file_enrichment_service",
            method="enrich",
            enriched_count=sum(1 for r in results if r["file_enrichment"] is not None),
        )
        return results

    # ------------------------------------------------------------------
    # Per-memory enrichment
    # ------------------------------------------------------------------

    def _enrich_one(self, memory: dict, limit: int, cache: dict[str, dict]) -> dict:
        """Build one enriched result row (input row + file_enrichment key)."""
        result = dict(memory)
        result["file_enrichment"] = self._build_enrichment(memory.get("id", ""), limit, cache)
        return result

    def _build_enrichment(self, memory_id: str, limit: int, cache: dict[str, dict]) -> dict | None:
        """Resolve the file context for one memory; None when pure (D7).

        The file-level block is cached per file_id, but `chunk_hash` is
        per-memory (the recalled memory's own chunk row) — it is merged into a
        fresh dict on every call so the cache never leaks one memory's chunk
        hash into another memory of the same file.
        """
        chunk_result = self._file_service.get_chunk_by_memory_id(memory_id)
        if not chunk_result.is_ok or chunk_result.value is None:
            # Pure memory — no FileChunk row links it to the file layer.
            return None

        chunk = chunk_result.value
        file_id = chunk.file_id
        if file_id in cache:
            base = cache[file_id]
        else:
            base = self._build_file_enrichment(file_id, limit)
            if base is not None:
                cache[file_id] = base
        if base is None:
            return None
        return {**base, "chunk_hash": chunk.content_hash}

    def _build_file_enrichment(self, file_id: str, limit: int) -> dict | None:
        """Assemble the full enrichment block for a file; None when the File row is missing."""
        file_result = self._file_service.get_file_by_id(file_id)
        if not file_result.is_ok or file_result.value is None:
            # Chunk points at a missing/deleted File — degrade to pure form.
            return None
        file = file_result.value

        relations = self._load_relations(file_id, limit)
        chunks_result = self._file_service.get_chunks_by_file_id(file_id)
        chunks: list[FileChunk] = chunks_result.value if chunks_result.is_ok else []

        return {
            "file": file.to_dict(),
            "relations": [self._relation_block(rel) for rel in relations],
            "related_files": self._resolve_related_files(relations, file_id),
            "summary_chain": self._build_summary_chain(file, chunks),
            "traversal": {"file_id": file_id, "relation_ids": [rel.id for rel in relations]},
            "source_type_enrichment": dict(file.metadata),
        }

    # ------------------------------------------------------------------
    # Block builders (all values come from entities — no hardcoded stubs)
    # ------------------------------------------------------------------

    def _load_relations(self, file_id: str, limit: int) -> list[FileRelation]:
        """Load the file's relations, sorted strength-descending, capped at limit."""
        relations_result = self._file_service.get_relations_by_file_id(file_id)
        if not relations_result.is_ok:
            return []
        ordered = sorted(relations_result.value, key=lambda rel: rel.strength, reverse=True)
        return ordered[:limit]

    def _relation_block(self, relation: FileRelation) -> dict:
        """Compact relation row (id + type + strength + description) for the enrichment block."""
        return {
            "id": relation.id,
            "relation_type": relation.relation_type.value,
            "strength": relation.strength,
            "description": relation.description,
        }

    def _resolve_related_files(self, relations: list[FileRelation], source_file_id: str) -> list[dict]:
        """Resolve each relation's other end to {id, path, summary, relation}."""
        resolved: list[dict] = []
        seen: set[str] = set()
        for relation in relations:
            target_id = relation.target_file_id if relation.source_file_id == source_file_id else relation.source_file_id
            if target_id in seen or target_id == source_file_id:
                continue
            seen.add(target_id)

            file_result = self._file_service.get_related_file_by_id(target_id)
            if not file_result.is_ok or file_result.value is None:
                # Dangling edge (D4 stub policy may leave rows absent here) — skip.
                continue

            target = file_result.value
            resolved.append(
                {
                    "id": target.id,
                    "path": target.path,
                    "summary": target.summary,
                    "relation": relation.relation_type.value,
                    "description": relation.description,
                }
            )
        return resolved

    def _build_summary_chain(self, file: File, chunks: list[FileChunk]) -> list[str]:
        """File-level summary first, then distinct parent-unit summaries (in chunk order).

        When File.summary is null the head falls back to a mechanical
        path+keywords+tags generation (the SearchFilesUseCase._generate_summary
        convention), so big files always carry a traversable chain.
        """
        head = file.summary if file.summary else self._mechanical_summary(file)
        chain: list[str] = [head]

        seen: set[str] = set()
        for chunk in sorted(chunks, key=lambda c: c.chunk_index):
            parent_summary = chunk.parent_unit_summary
            if parent_summary is None or parent_summary in seen:
                continue
            seen.add(parent_summary)
            chain.append(parent_summary)
        return chain

    @staticmethod
    def _mechanical_summary(file: File) -> str:
        """Mechanical fallback summary when File.summary is null.

        Deliberate documented default (moved from SearchFilesUseCase._generate_summary):
        path + up to 5 keywords + up to 5 tags; empty string only when the file
        carries none of them.
        """
        parts: list[str] = []
        if file.path:
            parts.append(f"File: {file.path}")
        if file.aggregated_keywords:
            parts.append(f"Keywords: {', '.join(file.aggregated_keywords[:5])}")
        if file.aggregated_tags:
            parts.append(f"Tags: {', '.join(file.aggregated_tags[:5])}")
        return ". ".join(parts)
