"""SearchFilesUseCase — two-phase file search with metadata enrichment.

Phase 1: Query memories via MnemosyneClient.recall.
Phase 2: For each recalled memory, look up file context via FileChunkRepository,
         enrich with File metadata and relations from FileRepository / FileRelationRepository.
Returns both file-backed memories (with enrichment) and non-file memories (without).
"""

from __future__ import annotations

from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.file_entity import File
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_relation_entity import FileRelation
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository


class SearchFilesUseCase(BaseUseCase[dict, dict]):
    """Orchestrates two-phase file search with metadata enrichment."""

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        chunk_repository: FileChunkRepository,
        file_repository: FileRepository,
        relation_repository: FileRelationRepository,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.chunk_repository = chunk_repository
        self.file_repository = file_repository
        self.relation_repository = relation_repository

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that query is present and non-empty."""
        if not parameters.get("query"):
            return Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute two-phase search: recall memories, then enrich with file metadata."""
        query = parameters["query"]
        limit = parameters.get("limit", 10)

        # Phase 1: Recall memories
        recall_result = self.mnemosyne_client.recall(query, limit)
        if isinstance(recall_result, Result) and recall_result.is_ko:
            return recall_result

        # MnemosyneClient.recall may return Result or raw list depending on wiring
        memories: List[dict] = recall_result.value if isinstance(recall_result, Result) else recall_result

        # Phase 2: Enrich each memory with file context
        include_relations = parameters.get("include_relations", False)
        results = self._enrich_memories(memories, include_relations)

        return Result.ok({
            "results": results,
            "total_count": len(results),
        })

    # ------------------------------------------------------------------
    # Phase 2: Enrichment
    # ------------------------------------------------------------------

    def _enrich_memories(
        self,
        memories: List[dict],
        include_relations: bool,
    ) -> List[dict]:
        """Enrich recalled memories with file metadata.

        Groups file-backed memories by file_id; non-file memories appear as separate results.
        """
        # Track file_id → result mapping for grouping
        file_results: Dict[str, dict] = {}
        all_results: List[dict] = []

        for memory in memories:
            memory_id = memory.get("id", "")
            chunk_result = self.chunk_repository.get_chunk_by_memory_id(memory_id)

            if not chunk_result.is_ok or chunk_result.value is None:
                # Non-file memory — no chunk found or lookup failed
                all_results.append(self._build_non_file_result(memory))
                continue

            chunk = chunk_result.value
            file_id = chunk.file_id

            # Check if we already have a result for this file
            if file_id not in file_results:
                # Look up file metadata
                file_result = self.file_repository.get_file_by_id(file_id)
                if not file_result.is_ok or file_result.value is None:
                    # File lookup failed — treat as non-file memory
                    all_results.append(self._build_non_file_result(memory))
                    continue

                file = file_result.value
                # Look up relations
                relations_result = self.relation_repository.get_relations_by_file_id(file_id)
                relations: List[FileRelation] = relations_result.value if relations_result.is_ok else []

                file_results[file_id] = self._build_file_result(
                    file=file,
                    relations=relations,
                    include_relations=include_relations,
                )

            # Add this memory to the file's matched_memories
            file_results[file_id]["matched_memories"].append(
                self._build_matched_memory(memory, chunk)
            )

        # Merge file results into all_results
        all_results.extend(file_results.values())
        return all_results

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
        relations: List[FileRelation],
        include_relations: bool,
    ) -> dict:
        """Build a result entry for a file-backed memory group."""
        related_files_count = len(relations)

        related_files: Optional[List[dict]] = None
        if include_relations:
            related_files = self._resolve_related_files(relations)

        return {
            "file": self._file_to_dict(file),
            "matched_memories": [],
            "related_files_count": related_files_count,
            "related_files": related_files,
            "summary": self._generate_summary(file),
            "source_type_enrichment": {},
        }

    def _build_matched_memory(self, memory: dict, chunk: FileChunk) -> dict:
        """Build a matched memory entry within a file result."""
        return {
            "id": memory.get("id", ""),
            "content_preview": memory.get("content", ""),
            "importance": memory.get("importance", 0.0),
            "chunk_index": chunk.chunk_index,
            "section_header": "",
            "relevance_score": memory.get("relevance_score", 0.0),
        }

    def _file_to_dict(self, file: File) -> dict:
        """Convert a File entity to a dict for the result."""
        return {
            "id": file.id,
            "path": file.path,
            "source_type": file.source_type.value,
            "file_role": file.file_type or "",
            "total_chunks": 0,
            "keywords": file.aggregated_keywords,
            "tags": file.aggregated_tags,
            "average_importance": 0.5,
            "metadata": {},
        }

    def _resolve_related_files(self, relations: List[FileRelation]) -> List[dict]:
        """Resolve related file details from relations."""
        resolved: Dict[str, dict] = {}
        for rel in relations:
            # The related file is the one that is NOT the source
            target_id = rel.target_file_id
            if target_id in resolved:
                continue

            file_result = self.file_repository.get_file_by_id(target_id)
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

    def _generate_summary(self, file: File) -> str:
        """Generate a brief summary for a file result."""
        parts = []
        if file.path:
            parts.append(f"File: {file.path}")
        if file.aggregated_keywords:
            parts.append(f"Keywords: {', '.join(file.aggregated_keywords[:5])}")
        if file.aggregated_tags:
            parts.append(f"Tags: {', '.join(file.aggregated_tags[:5])}")
        return ". ".join(parts) if parts else ""
