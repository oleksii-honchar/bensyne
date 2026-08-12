"""ExpandFileRelationsUseCase — expand file relations with content composition.

Flow (aggregate-owned content composition):
1. Get source file aggregate via FileService.get_file()
2. Get relations (optionally filtered by relation_types)
3. For each related file, get aggregate via FileService.get_file()
4. Delegate content composition to aggregate.compose_content(mnemosyne_client)
5. Return structured result
"""

from __future__ import annotations

from typing import Callable

import structlog.stdlib
from src.application.services.file_service import FileService
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.file_metadata_aggregate import FileMetadataAggregate
from src.domain.file_entity import File
from src.domain.file_relation_entity import FileRelation, RelationType
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository


class ExpandFileRelationsUseCase(BaseUseCase[dict, dict]):
    """Orchestrates file relations expansion with content composition.

    Delegates content composition to FileMetadataAggregate.compose_content()
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
        """Validate that file_id is present and non-empty."""
        file_id = parameters.get("file_id")
        if not file_id:
            return Result.ko([ErrorWithDetails("FILE_ID_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute relation expansion with content composition."""
        file_id = parameters["file_id"]
        relation_types = parameters.get("relation_types")
        summary_only = parameters.get("summary_only", False)

        self.logger.info(
            "Expanding file relations",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=file_id,
            relation_types=relation_types,
        )

        # Step 1: Get source file aggregate via FileService
        source_result = self.file_service.get_file(file_id)
        if not source_result.is_ok or source_result.value is None:
            return Result.ko([ErrorWithDetails("FILE_NOT_FOUND", {"file_id": file_id})])
        source_agg = source_result.value
        source_file = source_agg.file

        self.logger.debug(
            "Source file retrieved",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=file_id,
            file_path=source_file.path,
        )

        # Step 2: Get relations for source file
        relations_result = self.relation_repository.get_relations_by_file_id(file_id)
        if not relations_result.is_ok:
            relations: list[FileRelation] = []
        else:
            relations = relations_result.value

        # Filter by relation_types if specified
        if relation_types:
            allowed = {RelationType(rt) for rt in relation_types}
            relations = [r for r in relations if r.relation_type in allowed]

        self.logger.debug(
            "Relations retrieved",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=file_id,
            relations_count=len(relations),
        )

        # Step 3: Expand each related file
        related_files = self._expand_related_files(
            source_file, relations, summary_only=summary_only,
        )

        self.logger.info(
            "File relations expanded",
            use_case="expand_file_relations",
            method="execute_internal",
            file_id=file_id,
            related_files_count=len(related_files),
        )

        return Result.ok({
            "source_file": self._file_to_dict(source_file),
            "related_files": related_files,
        })

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
                chunks_count = 0
                expanded.append({
                    "file": {
                        "id": f.id,
                        "path": f.path,
                        "source_type": f.source_type.value,
                        "relation_type": rel.relation_type.value,
                    },
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
                })
            else:
                output = to_dict_result.value
                chunks_count = output.get("chunks_count", 0)
                expanded.append(output)

            self.logger.info(
                "Related file expanded",
                use_case="expand_file_relations",
                method="_expand_related_files",
                target_file_path=f.path,
                chunks_count=chunks_count,
            )

        return expanded

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _file_to_dict(self, file: File) -> dict:
        """Convert a File entity to a dict for the result."""
        return {
            "id": file.id,
            "path": file.path,
            "source_type": file.source_type.value,
        }
