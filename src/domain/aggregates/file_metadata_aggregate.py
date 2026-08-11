"""FileMetadataAggregate — aggregate root orchestrating File, FileChunk, and FileRelation."""

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from src.domain.entities.file import File
from src.domain.entities.file_chunk import FileChunk
from src.domain.entities.file_relation import FileRelation, RelationType
from src.domain.events.file_events import (
    FileChunkAddedEvent,
    FileChunkRemovedEvent,
    FileRelationCreatedEvent,
    FileContentComposedEvent,
)
from src.domain.result import ErrorWithDetails, Result


@dataclass(frozen=True)
class FileMetadataAggregate:
    """Aggregate root for file metadata operations.

    Enforces file-chunk relationship invariants and produces
    domain events via Result.events.
    """

    file: File
    chunks: List[FileChunk]
    relations: List[FileRelation]

    @classmethod
    def of(
        cls,
        file: File,
        chunks: Optional[List[FileChunk]] = None,
        relations: Optional[List[FileRelation]] = None,
    ) -> Result["FileMetadataAggregate"]:
        """Factory method returning Result[FileMetadataAggregate]."""
        return Result.ok(cls(
            file=file,
            chunks=chunks or [],
            relations=relations or [],
        ))

    def add_chunk(self, chunk: FileChunk) -> Result["FileMetadataAggregate"]:
        """Add a chunk to this file.

        Rejects if a chunk with the same memory_id already exists.
        On success produces a FileChunkAddedEvent and updates file
        metadata via file.with_chunk().
        """
        if any(c.memory_id == chunk.memory_id for c in self.chunks):
            return Result.ko([ErrorWithDetails("CHUNK_ALREADY_EXISTS", {
                "file_id": self.file.id,
                "memory_id": chunk.memory_id,
            })])

        updated_file_result = self.file.with_chunk(
            importance=0.5,
            tags=[],
            keywords=[],
        )
        if updated_file_result.is_ko:
            return updated_file_result

        event = FileChunkAddedEvent.of(
            file_id=self.file.id,
            memory_id=chunk.memory_id,
            chunk_index=chunk.chunk_index,
        )
        if event.is_ko:
            return event

        return Result.ok(
            self.__class__(
                file=updated_file_result.value,
                chunks=[*self.chunks, chunk],
                relations=self.relations,
            ),
            events=[event.value],
        )

    def remove_chunk(self, memory_id: str) -> Result["FileMetadataAggregate"]:
        """Remove a chunk from this file.

        Rejects if no chunk with the given memory_id exists.
        On success produces a FileChunkRemovedEvent and updates file
        metadata via file.without_chunk().
        """
        chunk = next((c for c in self.chunks if c.memory_id == memory_id), None)
        if not chunk:
            return Result.ko([ErrorWithDetails("CHUNK_NOT_FOUND", {
                "file_id": self.file.id,
                "memory_id": memory_id,
            })])

        updated_file_result = self.file.without_chunk(importance=0.5)
        if updated_file_result.is_ko:
            return updated_file_result

        event = FileChunkRemovedEvent.of(
            file_id=self.file.id,
            memory_id=memory_id,
        )
        if event.is_ko:
            return event

        return Result.ok(
            self.__class__(
                file=updated_file_result.value,
                chunks=[c for c in self.chunks if c.memory_id != memory_id],
                relations=self.relations,
            ),
            events=[event.value],
        )

    def add_relation(self, relation: FileRelation) -> Result["FileMetadataAggregate"]:
        """Add a relation from this file to another.

        On success produces a FileRelationCreatedEvent.
        """
        event = FileRelationCreatedEvent.of(
            source_file_id=self.file.id,
            target_file_id=relation.target_file_id,
            relation_type=relation.relation_type.value,
        )
        if event.is_ko:
            return event

        return Result.ok(
            self.__class__(
                file=self.file,
                chunks=self.chunks,
                relations=[*self.relations, relation],
            ),
            events=[event.value],
        )

    def compose_content(
        self,
        mnemosyne_client: Callable[[str], Optional[dict]],
        summary_only: bool = False,
    ) -> Result[dict]:
        """Compose file representation from its chunks and mnemosyne content.

        The aggregate owns its chunks and uses them to produce the file's
        representation: summary (if present), composed content from chunks,
        chunks_count, and metadata.

        Args:
            mnemosyne_client: A callable that takes a memory_id and returns
                an optional dict with at least a "content" key, or None if
                the memory is not found. Passed as a parameter to keep the
                domain layer free of infrastructure references.
            summary_only: If True, returns only the file's summary without
                fetching chunk content from mnemosyne.

        Returns:
            Result[dict] with keys: summary, content, chunks_count, metadata.
            Emits FileContentComposedEvent when content is actually composed
            (summary_only=False and chunks exist).
        """
        summary = self.file.summary

        if summary_only:
            return Result.ok({
                "summary": summary,
                "content": summary or "",
                "chunks_count": 0,
                "metadata": {
                    "keywords": self.file.aggregated_keywords,
                    "tags": self.file.aggregated_tags,
                    "file_type": self.file.file_type or "",
                    "size": self.file.size,
                    "language": self.file.language,
                },
            })

        # Sort chunks by chunk_index (primary ordering)
        sorted_chunks = sorted(self.chunks, key=lambda c: c.chunk_index)
        chunks_count = len(sorted_chunks)

        # Fetch content from mnemosyne for each chunk
        content_parts: List[str] = []
        for chunk in sorted_chunks:
            memory = mnemosyne_client(chunk.memory_id)
            if memory and isinstance(memory, dict) and memory.get("content"):
                content_parts.append(memory["content"])

        # Compose: summary first, then chunk content
        composed = ""
        if summary:
            composed = summary
        if content_parts:
            chunk_content = "\n".join(content_parts)
            if composed:
                composed += "\n\n" + chunk_content
            else:
                composed = chunk_content

        event_result = FileContentComposedEvent.of(
            file_id=self.file.id,
            chunks_composed=len(content_parts),
        )
        if event_result.is_ko:
            return event_result

        return Result.ok({
            "summary": summary,
            "content": composed,
            "chunks_count": chunks_count,
            "metadata": {
                "keywords": self.file.aggregated_keywords,
                "tags": self.file.aggregated_tags,
                "file_type": self.file.file_type or "",
                "size": self.file.size,
                "language": self.file.language,
            },
        }, events=[event_result.value])

    def to_dict(
        self,
        include_relation_type: RelationType | None = None,
        include_content: bool = False,
        summary_only: bool = False,
        mnemosyne_client: Callable[[str], Optional[dict]] | None = None,
    ) -> Result[dict]:
        """Produce the full output dict used by expand_file_relations.

        The aggregate owns its representation — this method builds the
        structured dict that the use case returns to the caller.

        Args:
            include_relation_type: If set, embeds relation_type in the
                "file" sub-dict. The use case passes the relation type
                from the FileRelation it is expanding.
            include_content: If True, includes "content" and "chunks_count"
                in the output. When True and summary_only=True, uses
                compose_content(summary_only=True). When True and
                summary_only=False, composes full content from chunks.
            summary_only: Only relevant when include_content=True. If True,
                content is just the file summary without fetching chunks.
            mnemosyne_client: Required when include_content=True and
                summary_only=False. A callable that takes a memory_id and
                returns an optional dict with at least a "content" key,
                or None if not found.

        Returns:
            Result[dict] with structure:
            {
                "file": { "id", "path", "source_type", ["relation_type"] },
                "summary": ...,
                ["content": ...],
                "metadata": { "keywords", "tags", "file_type", "size", "language" },
                ["chunks_count": ...],
            }
        """
        file_dict: dict[str, object] = {
            "id": self.file.id,
            "path": self.file.path,
            "source_type": self.file.source_type.value,
        }
        if include_relation_type is not None:
            file_dict["relation_type"] = include_relation_type.value

        metadata = {
            "keywords": self.file.aggregated_keywords,
            "tags": self.file.aggregated_tags,
            "file_type": self.file.file_type or "",
            "size": self.file.size,
            "language": self.file.language,
        }

        if include_content:
            # Delegate to compose_content for the content portion
            if mnemosyne_client is None:
                return Result.ko([ErrorWithDetails("MNEMOSYNE_CLIENT_REQUIRED", {
                    "file_id": self.file.id,
                })])
            compose_result = self.compose_content(
                mnemosyne_client=mnemosyne_client,
                summary_only=summary_only,
            )
            if compose_result.is_ko:
                return compose_result

            composed = compose_result.value
            return Result.ok({
                "file": file_dict,
                "summary": composed["summary"],
                "content": composed["content"],
                "metadata": metadata,
                "chunks_count": composed["chunks_count"],
            }, events=compose_result.events)

        return Result.ok({
            "file": file_dict,
            "summary": self.file.summary,
            "metadata": metadata,
        })
