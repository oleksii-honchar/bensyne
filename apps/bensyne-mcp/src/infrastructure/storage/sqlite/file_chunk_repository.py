"""FileChunkRepository — SQLite implementation of FileChunkRepository using SQLAlchemy ORM.

Maps FileChunk domain entities to/from rows in the `file_chunks` table via SQLAlchemy ORM.
Uses FileMetadataConnectionManager for Session management.
"""

from __future__ import annotations

from datetime import datetime
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.models import FileChunkORM

# ---------------------------------------------------------------------------
# ORM ↔ FileChunk mapping helpers
# ---------------------------------------------------------------------------


def _orm_to_chunk(orm: FileChunkORM) -> FileChunk:
    """Map a FileChunkORM instance to a FileChunk entity."""
    created_at = orm.created_at if orm.created_at else datetime.now()
    updated_at = orm.updated_at if orm.updated_at else created_at

    return FileChunk(
        id=orm.id,
        file_id=orm.file_id,
        memory_id=orm.memory_id,
        chunk_index=orm.chunk_index,
        start_line=orm.start_line if orm.start_line is not None else 0,
        end_line=orm.end_line if orm.end_line is not None else 0,
        content_hash=orm.content_hash,
        content_type=ContentType(orm.content_type) if orm.content_type else ContentType.UNKNOWN,
        is_partial=bool(orm.is_partial) if orm.is_partial is not None else False,
        section_header=orm.section_header,
        parent_unit_ref=orm.parent_unit_ref,
        parent_unit_summary=orm.parent_unit_summary,
        created_at=created_at,
        updated_at=updated_at,
    )


def _chunk_to_orm(chunk: FileChunk) -> FileChunkORM:
    """Map a FileChunk entity to a FileChunkORM instance."""
    return FileChunkORM(
        id=chunk.id,
        file_id=chunk.file_id,
        memory_id=chunk.memory_id,
        chunk_index=chunk.chunk_index,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        content_hash=chunk.content_hash,
        content_type=chunk.content_type.value,
        is_partial=chunk.is_partial,
        section_header=chunk.section_header,
        parent_unit_ref=chunk.parent_unit_ref,
        parent_unit_summary=chunk.parent_unit_summary,
        created_at=chunk.created_at,
        updated_at=chunk.updated_at,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class FileChunkRepository:
    """SQLite-backed FileChunk repository using SQLAlchemy ORM.

    Args:
        connection_manager: FileMetadataConnectionManager for Session management.
    """

    def __init__(self, connection_manager: FileMetadataConnectionManager) -> None:
        self._conn_manager = connection_manager

    # ------------------------------------------------------------------
    # save_chunk
    # ------------------------------------------------------------------

    def save_chunk(self, chunk: FileChunk) -> Result[FileChunk]:
        """Save a chunk, returning the saved entity.

        Uses merge() for upsert semantics on the id column.
        """
        session = self._conn_manager.get_session()
        try:
            orm = _chunk_to_orm(chunk)
            session.merge(orm)
            session.commit()
            return Result.ok(chunk)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("CHUNK_SAVE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_chunk_by_id
    # ------------------------------------------------------------------

    def get_chunk_by_id(self, chunk_id: str) -> Result[FileChunk | None]:
        """Find a chunk by its id."""
        session = self._conn_manager.get_session()
        try:
            orm = session.query(FileChunkORM).filter(FileChunkORM.id == chunk_id).first()
            if orm is None:
                return Result.ok(None)
            return Result.ok(_orm_to_chunk(orm))
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_chunks_by_file_id
    # ------------------------------------------------------------------

    def get_chunks_by_file_id(self, file_id: str) -> Result[list[FileChunk]]:
        """Find all chunks belonging to a file, ordered by chunk_index."""
        session = self._conn_manager.get_session()
        try:
            orms = (
                session.query(FileChunkORM)
                .filter(FileChunkORM.file_id == file_id)
                .order_by(FileChunkORM.chunk_index.asc())
                .all()
            )
            chunks = [_orm_to_chunk(orm) for orm in orms]
            return Result.ok(chunks)
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_FILE_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_chunk_by_memory_id
    # ------------------------------------------------------------------

    def get_chunk_by_memory_id(self, memory_id: str) -> Result[FileChunk | None]:
        """Find a chunk by its associated memory id.

        A memory_id may back a chunk row in more than one file; the result is
        made deterministic on (chunk_index, file_id) so the lookup is stable
        regardless of row insertion order.
        """
        session = self._conn_manager.get_session()
        try:
            orm = (
                session.query(FileChunkORM)
                .filter(FileChunkORM.memory_id == memory_id)
                .order_by(FileChunkORM.chunk_index.asc(), FileChunkORM.file_id.asc())
                .first()
            )
            if orm is None:
                return Result.ok(None)
            return Result.ok(_orm_to_chunk(orm))
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_MEMORY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_chunks_by_memory_id
    # ------------------------------------------------------------------

    def get_chunks_by_memory_id(self, memory_id: str) -> Result[list[FileChunk]]:
        """Find all chunks by their associated memory id."""
        session = self._conn_manager.get_session()
        try:
            orms = session.query(FileChunkORM).filter(FileChunkORM.memory_id == memory_id).all()
            chunks = [_orm_to_chunk(orm) for orm in orms]
            return Result.ok(chunks)
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_MEMORY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # delete_chunk
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # delete_chunks_by_file_id
    # ------------------------------------------------------------------

    def delete_chunks_by_file_id(self, file_id: str, exclude_memory_ids: set[str]) -> Result[bool]:
        """Delete all chunks of a file whose memory_id is NOT in the exclude set.

        Used by the re-ingest rebuild path to drop stale chunk rows while
        keeping live memories (whose ids are in `exclude_memory_ids`).
        An empty exclude set deletes every chunk of the file.
        Returns Result.ok(True) on success (no-op when nothing matches).
        """
        session = self._conn_manager.get_session()
        try:
            query = session.query(FileChunkORM).filter(FileChunkORM.file_id == file_id)
            if exclude_memory_ids:
                query = query.filter(~FileChunkORM.memory_id.in_(exclude_memory_ids))
            deleted = query.delete(synchronize_session=False)
            session.commit()
            return Result.ok(deleted > 0)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("CHUNK_DELETE_BY_FILE_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # delete_chunk
    # ------------------------------------------------------------------

    def delete_chunk(self, chunk_id: str) -> Result[bool]:
        """Delete a chunk by id, returning True if it existed."""
        session = self._conn_manager.get_session()
        try:
            orm = session.query(FileChunkORM).filter(FileChunkORM.id == chunk_id).first()
            if orm is None:
                return Result.ok(False)
            session.delete(orm)
            session.commit()
            return Result.ok(True)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("CHUNK_DELETE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)
