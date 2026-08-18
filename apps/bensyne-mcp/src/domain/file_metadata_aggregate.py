"""FileMetadata — aggregate root orchestrating File, FileChunk, and FileRelation."""

from dataclasses import dataclass
from typing import Callable

from src.domain.file_entity import File
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_relation_entity import FileRelation, RelationType
from src.domain.events.file_events import (
    FileChunkRemovedEvent,
    FileContentComposedEvent,
)
from src.domain.events.file_chunk_events import FileChunkCreatedEvent
from src.utils.result import ErrorWithDetails, Result


@dataclass(frozen=True)
class FileMetadata:
    """Aggregate root for file metadata operations.

    Enforces file-chunk relationship invariants and produces
    domain events via Result.events.
    """

    file: File
    chunks: list[FileChunk]
    relations: list[FileRelation]

    @classmethod
    def of(
        cls,
        file: File,
        chunks: list[FileChunk] | None = None,
        relations: list[FileRelation] | None = None,
    ) -> Result["FileMetadata"]:
        """Factory method returning Result[FileMetadata]."""
        return Result.ok(
            cls(
                file=file,
                chunks=chunks or [],
                relations=relations or [],
            )
        )

    def upsert_chunk(self, chunk: FileChunk) -> Result["FileMetadata"]:
        """Upsert a chunk by memory_id (spec §4.1, D19a).

        Decision table:
        - No existing chunk with the same memory_id: add the chunk and
          re-aggregate file keyword/importance via file.with_chunk().
          Emits exactly one FileChunkCreatedEvent (entity-level class).
        - Existing chunk, chunk_index differs: replace — remove the old
          row, insert the new row under the preserved row id
          fc_{file_id}_{memory_id} (update_metadata cannot change
          chunk_index). Emits FileChunkRemovedEvent then
          FileChunkCreatedEvent, in that order.
        - Existing chunk, updatable metadata fields differ: in-place
          update_metadata on the existing chunk, row id preserved.
          Emits FileChunkUpdatedEvent.
        - Existing chunk, all fields equal: silent no-op — zero events
          (idempotency contract: dedup-hit re-materialization must be
          event-silent, D14).

        The uniqueness invariant (one chunk row per memory_id per file)
        is enforced by this upsert instead of rejected.
        """
        existing = next(
            (c for c in self.chunks if c.memory_id == chunk.memory_id), None
        )

        if existing is None:
            updated_file_result = self.file.with_chunk(
                importance=0.5,
                tags=[],
                keywords=[],
            )
            if updated_file_result.is_ko:
                return updated_file_result

            event = FileChunkCreatedEvent.of(
                chunk.id, self.file.id, chunk.memory_id
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

        if existing.chunk_index != chunk.chunk_index:
            # Replace: chunk_index is positional data that update_metadata
            # cannot change — remove old row, insert new row, same row id.
            without_result = self.file.without_chunk(importance=0.5)
            if without_result.is_ko:
                return without_result

            removed_event = FileChunkRemovedEvent.of(
                file_id=self.file.id,
                memory_id=chunk.memory_id,
            )
            if removed_event.is_ko:
                return removed_event

            replaced = FileChunk.of(
                {
                    "id": existing.id,
                    "file_id": chunk.file_id,
                    "memory_id": chunk.memory_id,
                    "chunk_index": chunk.chunk_index,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content_hash": chunk.content_hash,
                    "content_type": chunk.content_type,
                    "is_partial": chunk.is_partial,
                    "section_header": chunk.section_header,
                    "parent_unit_ref": chunk.parent_unit_ref,
                    "parent_unit_summary": chunk.parent_unit_summary,
                }
            )
            if replaced.is_ko:
                return replaced

            added_file_result = without_result.value.with_chunk(
                importance=0.5,
                tags=[],
                keywords=[],
            )
            if added_file_result.is_ko:
                return added_file_result

            new_chunks = [
                replaced.value if c.memory_id == chunk.memory_id else c
                for c in self.chunks
            ]
            return Result.ok(
                self.__class__(
                    file=added_file_result.value,
                    chunks=new_chunks,
                    relations=self.relations,
                ),
                events=[removed_event.value, *replaced.events],
            )

        updated_chunk_result = existing.update_metadata(
            content_type=chunk.content_type,
            content_hash=chunk.content_hash,
            is_partial=chunk.is_partial,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            section_header=chunk.section_header,
            parent_unit_ref=chunk.parent_unit_ref,
            parent_unit_summary=chunk.parent_unit_summary,
        )
        if updated_chunk_result.is_ko:
            return updated_chunk_result

        if not updated_chunk_result.events:
            # All fields equal: idempotent re-materialization is event-silent.
            return Result.ok(self)

        new_chunks = [
            updated_chunk_result.value if c.memory_id == chunk.memory_id else c
            for c in self.chunks
        ]
        return Result.ok(
            self.__class__(
                file=self.file,
                chunks=new_chunks,
                relations=self.relations,
            ),
            events=updated_chunk_result.events,
        )

    def remove_chunk(self, memory_id: str) -> Result["FileMetadata"]:
        """Remove a chunk from this file.

        Rejects if no chunk with the given memory_id exists.
        On success produces a FileChunkRemovedEvent and updates file
        metadata via file.without_chunk().
        """
        chunk = next((c for c in self.chunks if c.memory_id == memory_id), None)
        if not chunk:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "CHUNK_NOT_FOUND",
                        {
                            "file_id": self.file.id,
                            "memory_id": memory_id,
                        },
                    )
                ]
            )

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

    def upsert_relation(self, relation: FileRelation) -> Result["FileMetadata"]:
        """Upsert a relation by (target_file_id, relation_type), scoped to
        this aggregate's file as source (spec §4.2, D19b).

        Decision table:
        - A relation whose source_file_id is not this aggregate's file:
          rejected (RELATION_SOURCE_MISMATCH) — the dedup scope is this
          file as source.
        - No existing relation with the same (target, type): add it under
          the canonical id fr_{source}_{target}_{type} (the production
          scheme). Emits exactly one FileRelationCreatedEvent — the
          entity-level class from file_relation_events.py, which the
          FileRelation factory produces; the aggregate-level duplicate in
          file_events.py is never referenced here.
        - Existing (target, type) with differing strength/description/
          direction: update in place via update_metadata on the existing
          relation, same id. Emits exactly one FileRelationUpdatedEvent.
        - Existing (target, type) all equal: silent no-op — zero events
          (idempotency contract: dedup-hit re-materialization must be
          event-silent, D14).

        The same target under DIFFERENT relation types coexists — the
        dedup key includes relation_type. The aggregate never renames ids:
        an in-memory relation with a legacy fr_{s}_{t} id keeps it through
        the update branch; legacy rows converge at persist time.
        """
        if relation.source_file_id != self.file.id:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "RELATION_SOURCE_MISMATCH",
                        {
                            "aggregate_file_id": self.file.id,
                            "relation_source_file_id": relation.source_file_id,
                        },
                    )
                ]
            )

        existing = next(
            (
                r
                for r in self.relations
                if r.source_file_id == self.file.id
                and r.target_file_id == relation.target_file_id
                and r.relation_type == relation.relation_type
            ),
            None,
        )

        if existing is None:
            canonical_id = (
                f"fr_{self.file.id}_{relation.target_file_id}"
                f"_{relation.relation_type.value}"
            )
            # FileRelation.of re-validates and emits the entity-level
            # FileRelationCreatedEvent (file_relation_events.py) carrying
            # the canonical id — the aggregate-level duplicate in
            # file_events.py is deliberately not used.
            stored = FileRelation.of(
                {
                    "id": canonical_id,
                    "source_file_id": relation.source_file_id,
                    "target_file_id": relation.target_file_id,
                    "relation_type": relation.relation_type,
                    "strength": relation.strength,
                    "direction": relation.direction,
                    "description": relation.description,
                    "created_at": relation.created_at,
                    "updated_at": relation.updated_at,
                }
            )
            if stored.is_ko:
                return stored

            return Result.ok(
                self.__class__(
                    file=self.file,
                    chunks=self.chunks,
                    relations=[*self.relations, stored.value],
                ),
                events=stored.events,
            )

        updated = existing.update_metadata(
            strength=relation.strength,
            description=relation.description,
            direction=relation.direction,
        )
        if updated.is_ko:
            return updated

        if not updated.events:
            # All fields equal: idempotent re-materialization is event-silent.
            return Result.ok(self)

        new_relations = [
            updated.value if r is existing else r for r in self.relations
        ]
        return Result.ok(
            self.__class__(
                file=self.file,
                chunks=self.chunks,
                relations=new_relations,
            ),
            events=updated.events,
        )

    def compose_content(
        self,
        mnemosyne_client: Callable[[str], dict | None],
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
            return Result.ok(
                {
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
                }
            )

        # Sort chunks by chunk_index (primary ordering)
        sorted_chunks = sorted(self.chunks, key=lambda c: c.chunk_index)
        chunks_count = len(sorted_chunks)

        # Fetch content from mnemosyne for each chunk
        content_parts: list[str] = []
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

        return Result.ok(
            {
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
            },
            events=[event_result.value],
        )

    def compose_fetch(
        self,
        mnemosyne_client: Callable[[str], dict | None],
        center_chunk_index: int | None = None,
        adjacent_chunks: int = 1,
    ) -> Result[dict]:
        """Compose the full fetch body from this aggregate's chunks.

        The aggregate owns its fetch composition (Task 11, Option 3):
        dedup by memory_id (first occurrence wins) → sort by
        (chunk_index, start_line) → either whole-file reconstruction (with
        gap indicators for missing memories) or a neighbor window around
        ``center_chunk_index``. The use case is a pure delegator that only
        wraps this body with the optional ``file`` block.

        Emits NO events — the fetch path historically composes content
        without emitting FileContentComposedEvent (byte-identity contract).

        Args:
            mnemosyne_client: Callable memory_id -> optional dict with a
                "content" key, or None. Keeps the domain layer free of
                infrastructure references.
            center_chunk_index: When set, return only the window
                [center - adjacent .. center + adjacent] (clamped). Out of
                [0, len(chunks)) ⇒ CENTER_CHUNK_INDEX_OUT_OF_RANGE.
            adjacent_chunks: Half-width of the neighbor window (0..5).

        Returns:
            Result[dict] body with keys: content, chunks,
            reconstruction_status, missing_chunks.
        """
        seen: set[str] = set()
        deduped: list[FileChunk] = []
        for chunk in self.chunks:
            if chunk.memory_id not in seen:
                seen.add(chunk.memory_id)
                deduped.append(chunk)
        ordered = sorted(deduped, key=lambda c: (c.chunk_index, c.start_line))

        if center_chunk_index is None:
            return self._compose_fetch_whole(mnemosyne_client, ordered)

        total = len(ordered)
        if center_chunk_index < 0 or center_chunk_index >= total:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "CENTER_CHUNK_INDEX_OUT_OF_RANGE",
                        {
                            "center_chunk_index": center_chunk_index,
                            "total_chunks": total,
                        },
                    )
                ]
            )
        low = max(0, center_chunk_index - adjacent_chunks)
        high = min(total - 1, center_chunk_index + adjacent_chunks)
        return self._compose_fetch_neighbor(mnemosyne_client, ordered[low : high + 1])

    def _compose_fetch_whole(
        self,
        mnemosyne_client: Callable[[str], dict | None],
        chunks: list[FileChunk],
    ) -> Result[dict]:
        """Whole-file reconstruction: joined content + 6-key chunk details."""
        content_parts: list[str] = []
        chunk_details: list[dict] = []
        missing: list[str] = []

        for chunk in chunks:
            memory = mnemosyne_client(chunk.memory_id)
            if memory and isinstance(memory, dict) and memory.get("content"):
                content = memory["content"]
                content_parts.append(content)
                chunk_details.append(
                    {
                        "memory_id": chunk.memory_id,
                        "chunk_index": chunk.chunk_index,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content": content or "",
                        "chunk_hash": chunk.content_hash,
                    }
                )
            else:
                content_parts.append(
                    f"<< missing chunk {chunk.memory_id} "
                    f"(index={chunk.chunk_index}, "
                    f"lines={chunk.start_line}-{chunk.end_line}) >>"
                )
                missing.append(chunk.memory_id)
                chunk_details.append(
                    {
                        "memory_id": chunk.memory_id,
                        "chunk_index": chunk.chunk_index,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "content": "",
                        "chunk_hash": chunk.content_hash,
                    }
                )

        return Result.ok(
            {
                "content": "\n".join(content_parts),
                "chunks": chunk_details,
                "reconstruction_status": "complete" if chunks and not missing else "partial",
                "missing_chunks": missing,
            }
        )

    def _compose_fetch_neighbor(
        self,
        mnemosyne_client: Callable[[str], dict | None],
        chunks: list[FileChunk],
    ) -> Result[dict]:
        """Neighbor window: content="" + 7-key chunk details (+ section_header)."""
        chunk_details: list[dict] = []
        missing: list[str] = []

        for chunk in chunks:
            memory = mnemosyne_client(chunk.memory_id)
            content: str | None = None
            if memory and isinstance(memory, dict) and memory.get("content"):
                content = memory["content"]
            else:
                missing.append(chunk.memory_id)
            chunk_details.append(
                {
                    "memory_id": chunk.memory_id,
                    "chunk_index": chunk.chunk_index,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "content": content or "",
                    "section_header": chunk.section_header,
                    "chunk_hash": chunk.content_hash,
                }
            )

        return Result.ok(
            {
                "content": "",
                "chunks": chunk_details,
                "reconstruction_status": "complete" if not missing else "partial",
                "missing_chunks": missing,
            }
        )

    def to_dict(
        self,
        include_relation_type: RelationType | None = None,
        include_content: bool = False,
        summary_only: bool = False,
        mnemosyne_client: Callable[[str], dict | None] | None = None,
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
                return Result.ko(
                    [
                        ErrorWithDetails(
                            "MNEMOSYNE_CLIENT_REQUIRED",
                            {
                                "file_id": self.file.id,
                            },
                        )
                    ]
                )
            compose_result = self.compose_content(
                mnemosyne_client=mnemosyne_client,
                summary_only=summary_only,
            )
            if compose_result.is_ko:
                return compose_result

            composed = compose_result.value
            return Result.ok(
                {
                    "file": file_dict,
                    "summary": composed["summary"],
                    "content": composed["content"],
                    "metadata": metadata,
                    "chunks_count": composed["chunks_count"],
                },
                events=compose_result.events,
            )

        return Result.ok(
            {
                "file": file_dict,
                "summary": self.file.summary,
                "metadata": metadata,
            }
        )
