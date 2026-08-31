"""ExpandFileRelationsUseCase — expand file relations with content composition.

Flow (aggregate-owned content composition):
1. Resolve source file via FileService.resolve_file_ref(file_id, path_handle)
   (D-2 chain: file_id exact, then path_handle metadata/path-suffix)
2. Get relations (optionally filtered by relation_types) by the resolved id
3. For each related file, get aggregate via FileService.get_file()
4. Delegate content composition to aggregate.compose_content(mnemosyne_client)
5. Enrich source_file / related_files[].file with a derived path_handle (D-1)
   only when derivable — leaves the canonical File.to_dict() block untouched
   when it is not
6. Return structured result
"""

from __future__ import annotations

from typing import Callable

import structlog.stdlib
from src.application.services.file_service import FileService, derive_path_handle
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.file_entity import File
from src.domain.file_relation_entity import FileRelation, RelationType
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository


class ExpandFileRelationsUseCase(BaseUseCase[dict, dict]):
    """Orchestrates file relations expansion with content composition.

    Delegates content composition to FileMetadata.compose_content()
    to avoid anemic domain model — the aggregate owns its chunks and produces
    its own representation.
    """

    def __init__(
        self,
        mnemosyne_client: Callable[[str], dict | None],
        file_service: FileService,
        relation_repository: FileRelationRepository,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.file_service = file_service
        self.relation_repository = relation_repository

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that at least one of file_id / path_handle is present (D-2, T4)."""
        file_id = parameters.get("file_id")
        path_handle = parameters.get("path_handle")
        if not file_id and not path_handle:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "FILE_REF_REQUIRED",
                        {
                            "file_id": file_id,
                            "path_handle": path_handle,
                        },
                    )
                ]
            )
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute relation expansion with content composition."""
        file_id: str | None = parameters.get("file_id")
        path_handle: str | None = parameters.get("path_handle")
        relation_types = parameters.get("relation_types")
        summary_only = parameters.get("summary_only", False)

        self.logger.info(
            "Expanding file relations",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=file_id,
            path_handle=path_handle,
            relation_types=relation_types,
        )

        # Step 1: Resolve source file via the D-2 chain (file_id, then path_handle).
        # Ok(None) means not found -> FILE_NOT_FOUND with conflation candidates (D-5).
        file_result = self.file_service.resolve_file_ref(file_id, path_handle)
        if not file_result.is_ok or file_result.value is None:
            return self._file_not_found(file_id, path_handle)
        source_file = file_result.value
        # Relations are always looked up by the resolved file's id (the input
        # file_id may be None when resolving by path_handle).
        resolved_file_id = source_file.id

        self.logger.debug(
            "Source file retrieved",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=resolved_file_id,
            file_path=source_file.path,
        )

        # Step 2: Get relations for the resolved source file
        relations_result = self.relation_repository.get_relations_by_file_id(resolved_file_id)
        if not relations_result.is_ok:
            relations: list[FileRelation] = []
        else:
            relations = relations_result.value

        # Expansion is one-way (outgoing): only relations where this file is
        # the source. get_relations_by_file_id is bidirectional (shared with
        # searchFiles), so restrict here to match traversal semantics.
        relations = [r for r in relations if r.source_file_id == resolved_file_id]

        # Filter by relation_types if specified
        if relation_types:
            allowed = {RelationType(rt) for rt in relation_types}
            relations = [r for r in relations if r.relation_type in allowed]

        self.logger.debug(
            "Relations retrieved",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=resolved_file_id,
            relations_count=len(relations),
        )

        # Step 3: Expand each related file
        related_files = self._expand_related_files(
            source_file,
            relations,
            summary_only=summary_only,
        )

        self.logger.info(
            "File relations expanded",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=resolved_file_id,
            related_files_count=len(related_files),
        )

        # Step 4: Enrich source_file with a derived path_handle (D-1, T4).
        # The canonical File.to_dict() block is emitted verbatim when no handle
        # is derivable (preserves the shape-pin contract).
        source_file_dict = source_file.to_dict()
        source_path_handle = derive_path_handle(source_file)
        if source_path_handle is not None:
            source_file_dict["path_handle"] = source_path_handle

        return Result.ok(
            {
                "source_file": source_file_dict,
                "related_files": related_files,
            }
        )

    def _file_not_found(self, file_id: str | None, path_handle: str | None) -> Result[dict]:
        """Build a FILE_NOT_FOUND error with conflation candidates (D-5, T4).

        When a ``file_id`` was supplied but did not resolve, surface up to 5
        files whose id ends with the supplied id's trailing 16 hex chars, each
        with ``file_id`` / ``path`` / ``path_handle``, plus a conflation hint.
        A chimeric id ends with the suffix of a real (parent) file, so its true
        source appears here. Candidates are only built from a supplied file_id
        (they are meaningless for a path_handle-only miss).
        """
        details: dict = {"file_id": file_id}
        if path_handle is not None:
            details["path_handle"] = path_handle

        if file_id:
            hex_tail = file_id[-16:]
            candidates_result = self.file_service.file_repository.find_files_by_id_suffix(hex_tail)
            details["candidates"] = []
            if candidates_result.is_ok and candidates_result.value:
                details["candidates"] = [
                    {
                        "file_id": candidate.id,
                        "path": candidate.path,
                        "path_handle": derive_path_handle(candidate),
                    }
                    for candidate in candidates_result.value
                ]
            details["hint"] = (
                "file_id not found — possible id conflation; pick from candidates "
                "or retry with path_handle"
            )

        return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", details)])

    # ------------------------------------------------------------------
    # Relations expansion
    # ------------------------------------------------------------------

    def _expand_related_files(
        self,
        source_file: File,
        relations: list[FileRelation],
        summary_only: bool = False,
    ) -> list[dict]:
        """Expand file relations into structured results with content.

        For each related file, gets the aggregate via FileService and
        delegates content composition to aggregate.compose_content().
        """
        # Deduplicate by target_file_id, keeping first relation type
        seen: dict[str, FileRelation] = {}
        for rel in relations:
            target_id = rel.target_file_id
            if target_id not in seen:
                seen[target_id] = rel

        expanded: list[dict] = []
        for target_id, rel in seen.items():
            # Get the aggregate for the related file (with chunks)
            agg_result = self.file_service.get_file(target_id)
            if not agg_result.is_ok or agg_result.value is None:
                continue

            agg = agg_result.value
            f = agg.file

            # Delegate full output composition to the aggregate
            to_dict_result = agg.to_dict(
                include_relation_type=rel.relation_type,
                include_content=True,
                summary_only=summary_only,
                mnemosyne_client=self.mnemosyne_client,
            )

            if to_dict_result.is_ko:
                # Fallback: compose minimal output on error
                file_dict: dict = {
                    "id": f.id,
                    "path": f.path,
                    "source_type": f.source_type.value,
                    "relation_type": rel.relation_type.value,
                }
                # D-1/T4: enrich with a derived path_handle when derivable.
                related_path_handle = derive_path_handle(f)
                if related_path_handle is not None:
                    file_dict["path_handle"] = related_path_handle
                chunks_count = 0
                expanded.append(
                    {
                        "file": file_dict,
                        "summary": f.summary,
                        "content": "",
                        "metadata": {
                            "keywords": f.aggregated_keywords,
                            "tags": f.aggregated_tags,
                            "file_type": f.file_type or "",
                            "size": f.size,
                            "language": f.language,
                        },
                        "chunks_count": 0,
                        "description": rel.description,
                    }
                )
            else:
                output = to_dict_result.value
                if output is not None:
                    chunks_count = output.get("chunks_count", 0)
                    # Use-case-level enrichment: the traversed relation's description
                    # is not part of the aggregate's to_dict output (spec §3.3).
                    output["description"] = rel.description
                    # D-1/T4: enrich with a derived path_handle when derivable.
                    related_path_handle = derive_path_handle(f)
                    if related_path_handle is not None:
                        output["file"]["path_handle"] = related_path_handle
                    expanded.append(output)
                else:
                    # Defensive: to_dict() returns a dict on success, but the value
                    # type is Optional (mypy). Skip the entry rather than crash.
                    chunks_count = 0

            self.logger.info(
                "Related file expanded",
                use_case="expand_file_relations",
                method="_expand_related_files",
                target_file_path=f.path,
                chunks_count=chunks_count,
            )

        return expanded


