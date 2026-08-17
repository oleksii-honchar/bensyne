"""SearchFilesUseCase — two-phase file search with metadata enrichment.

Phase 1: Query memories via MnemosyneClient.recall.
Phase 2: Group file-backed memories by file, enrich with REAL File entity
         values (delegated to FileService read passthroughs per D11), and
         add a `file_enrichment` block per result via FileEnrichmentService
         (D7 — one shared enrichment implementation for recall + searchFiles).

Response contract (stable per result, additive-only changes):
- Non-file memory: memory_id, file=None, matched_memories=[], related_files_count,
  content_preview, importance, relevance_score (+ additive file_enrichment key).
- File-backed group: file{...}, matched_memories[...], related_files_count,
  related_files, summary, source_type_enrichment (+ additive file_enrichment block).

Filters (source_type / file_role) apply to phase-2 grouping only: a recalled
memory whose file does not match the filter is emitted as a non-file result.
Pure memories are never dropped by filters.
"""

from __future__ import annotations

import structlog.stdlib

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.application.services.file_service import FileService
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_entity import File
from src.domain.file_relation_entity import FileRelation
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.utils.result import ErrorWithDetails, Result


class SearchFilesUseCase(BaseUseCase[dict, dict]):
    """Orchestrates two-phase file search with metadata enrichment.

    Depends only on FileService + FileEnrichmentService (D11) — no concrete
    repository imports here.
    """

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        file_service: FileService,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.file_service = file_service
        # Shared enrichment implementation (D7) — same code path as recall.
        self.file_enrichment_service = FileEnrichmentService(file_service=file_service, logger=logger)

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that query is present and non-empty."""
        if not parameters.get("query"):
            return Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute two-phase search: recall memories, then enrich with file metadata."""
        query = parameters["query"]
        limit = parameters.get("limit", 10)
        include_relations = parameters.get("include_relations", False)
        source_type = parameters.get("source_type")
        file_role = parameters.get("file_role")

        self.logger.info(
            "Searching files",
            use_case="search_files",
            method="execute_internal",
            query=query,
            limit=limit,
            source_type=source_type,
            file_role=file_role,
        )

        # Phase 1: Recall memories
        recall_result = self.mnemosyne_client.recall(query, limit)
        if isinstance(recall_result, Result) and recall_result.is_ko:
            return recall_result

        # MnemosyneClient.recall may return Result or raw list depending on wiring
        memories: list[dict] = recall_result.value if isinstance(recall_result, Result) else recall_result

        self.logger.debug(
            "Memories recalled",
            use_case="search_files",
            method="execute_internal",
            memories_count=len(memories),
        )

        # Phase 2: Group file-backed memories by file, enrich with real values
        results = self._group_and_enrich(memories, include_relations, source_type, file_role)

        # Additive enrichment pass (D7): every result gains a `file_enrichment`
        # key (None for pure memories — service contract). Same block shape as
        # recallMemory so consumers see one consistent enrichment contract.
        results = self.file_enrichment_service.enrich(results)

        self.logger.info(
            "File search completed",
            use_case="search_files",
            method="execute_internal",
            results_count=len(results),
            include_relations=include_relations,
        )

        return Result.ok(
            {
                "results": results,
                "total_count": len(results),
            }
        )

    # ------------------------------------------------------------------
    # Phase 2: Grouping + enrichment (real entity values, no stubs)
    # ------------------------------------------------------------------

    def _group_and_enrich(
        self,
        memories: list[dict],
        include_relations: bool,
        source_type: str | None,
        file_role: str | None,
    ) -> list[dict]:
        """Group file-backed memories by file_id; non-file memories stay separate.

        Filter semantics: a memory whose file fails the source_type/file_role
        filter is demoted to a non-file result (never dropped — recall semantics
        are preserved for unfiltered queries).
        """
        file_results: dict[str, dict] = {}
        all_results: list[dict] = []

        for memory in memories:
            memory_id = memory.get("id", "")
            chunk_result = self.file_service.get_chunk_by_memory_id(memory_id)

            if not chunk_result.is_ok or chunk_result.value is None:
                # Non-file memory — no chunk found or lookup failed
                all_results.append(self._build_non_file_result(memory))
                continue

            chunk = chunk_result.value
            file_id = chunk.file_id

            # Check if we already have a result for this file
            if file_id not in file_results:
                # Look up file metadata
                file_result = self.file_service.get_file_by_id(file_id)
                if not file_result.is_ok or file_result.value is None:
                    # File lookup failed — treat as non-file memory
                    all_results.append(self._build_non_file_result(memory))
                    continue

                file = file_result.value
                if not self._matches_filters(file, source_type, file_role):
                    # Filtered out of phase-2 grouping — demote to non-file result
                    all_results.append(self._build_non_file_result(memory))
                    continue

                # Look up relations
                relations_result = self.file_service.get_relations_by_file_id(file_id)
                relations: list[FileRelation] = relations_result.value if relations_result.is_ok else []

                file_results[file_id] = self._build_file_result(
                    file=file,
                    relations=relations,
                    include_relations=include_relations,
                )

            # Add this memory to the file's matched_memories
            file_results[file_id]["matched_memories"].append(self._build_matched_memory(memory, chunk))

        # Merge file results into all_results
        all_results.extend(file_results.values())
        return all_results

    @staticmethod
    def _matches_filters(file: File, source_type: str | None, file_role: str | None) -> bool:
        """Check a file against the optional source_type / file_role filters."""
        if source_type is not None and file.source_type.value != source_type:
            return False
        if file_role is not None and (file.file_role is None or file.file_role.value != file_role):
            return False
        return True

    # ------------------------------------------------------------------
    # Result builders
    # ------------------------------------------------------------------

    def _build_non_file_result(self, memory: dict) -> dict:
        """Build a result entry for a memory without file context."""
        return {
            "memory_id": memory.get("id", ""),
            "file": None,
            "matched_memories": [],
            "related_files_count": 0,
            "content_preview": memory.get("content", ""),
            "importance": memory.get("importance", 0.0),
            "relevance_score": memory.get("relevance_score", 0.0),
        }

    def _build_file_result(
        self,
        file: File,
        relations: list[FileRelation],
        include_relations: bool,
    ) -> dict:
        """Build a result entry for a file-backed memory group (real values)."""
        related_files_count = len(relations)

        related_files: list[dict] | None = None
        if include_relations:
            related_files = self._resolve_related_files(relations, file.id)

        return {
            "file": self._file_to_dict(file),
            "matched_memories": [],
            "related_files_count": related_files_count,
            "related_files": related_files,
            "summary": self.file_enrichment_service._mechanical_summary(file) if not file.summary else file.summary,
            # Real File.metadata extra keys (service contract: empty dict only when none)
            "source_type_enrichment": dict(file.metadata),
        }

    def _build_matched_memory(self, memory: dict, chunk: FileChunk) -> dict:
        """Build a matched memory entry within a file result."""
        return {
            "id": memory.get("id", ""),
            "content_preview": memory.get("content", ""),
            "importance": memory.get("importance", 0.0),
            "chunk_index": chunk.chunk_index,
            # Real value from the chunk row (None when the chunk has no header)
            "section_header": chunk.section_header,
            "relevance_score": memory.get("relevance_score", 0.0),
        }

    def _file_to_dict(self, file: File) -> dict:
        """Convert a File entity to a dict for the result (real entity values)."""
        return {
            "id": file.id,
            "path": file.path,
            "source_type": file.source_type.value,
            "file_role": file.file_role.value if file.file_role is not None else "",
            "total_chunks": file.total_chunks,
            "keywords": file.aggregated_keywords,
            "tags": file.aggregated_tags,
            "average_importance": file.average_importance,
            "metadata": dict(file.metadata),
        }

    def _resolve_related_files(self, relations: list[FileRelation], source_file_id: str) -> list[dict]:
        """Resolve related file details from relations."""
        resolved: dict[str, dict] = {}
        for rel in relations:
            # The related file is the one that is NOT the source
            target_id = rel.target_file_id if rel.source_file_id == source_file_id else rel.source_file_id
            if target_id in resolved or target_id == source_file_id:
                continue

            file_result = self.file_service.get_related_file_by_id(target_id)
            if not file_result.is_ok or file_result.value is None:
                continue

            f = file_result.value
            resolved[target_id] = {
                "id": f.id,
                "path": f.path,
                "source_type": f.source_type.value,
                "relation_type": rel.relation_type.value,
                "strength": rel.strength,
            }

        return list(resolved.values())
