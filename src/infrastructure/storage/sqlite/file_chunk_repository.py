"""FileChunkRepositorySQLite — SQLite implementation of FileChunkRepository.

Maps FileChunk domain entities to/from rows in the `file_chunks` table.
Uses FileMetadataConnectionManager for connection management.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from src.domain.entities.file_chunk import ContentType, FileChunk
from src.domain.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)

# ---------------------------------------------------------------------------
# Row ↔ FileChunk mapping helpers
# ---------------------------------------------------------------------------

def _row_to_chunk(row: sqlite3.Row) -> FileChunk:
    """Map a SQLite Row to a FileChunk entity."""
    created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now()
    updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else created_at

    return FileChunk(
        id=row["id"],
        file_id=row["file_id"],
        memory_id=row["memory_id"],
        chunk_index=row["chunk_index"],
        start_line=row["start_line"] if row["start_line"] is not None else 0,
        end_line=row["end_line"] if row["end_line"] is not None else 0,
        content_hash=row["content_hash"],
        content_type=ContentType(row["content_type"]) if row["content_type"] else ContentType.UNKNOWN,
        is_partial=bool(row["is_partial"]) if row["is_partial"] is not None else False,
        created_at=created_at,
        updated_at=updated_at,
    )


def _chunk_to_row(chunk: FileChunk) -> dict:
    """Map a FileChunk entity to a dict suitable for SQLite INSERT/UPDATE."""
    return {
        "id": chunk.id,
        "file_id": chunk.file_id,
        "memory_id": chunk.memory_id,
        "chunk_index": chunk.chunk_index,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "content_hash": chunk.content_hash,
        "content_type": chunk.content_type.value,
        "is_partial": int(chunk.is_partial),
        "created_at": chunk.created_at.isoformat(),
        "updated_at": chunk.updated_at.isoformat(),
    }

# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class FileChunkRepositorySQLite:
    """SQLite-backed FileChunk repository.

    Args:
        connection_manager: FileMetadataConnectionManager for connection pooling.
    """

    def __init__(self, connection_manager: FileMetadataConnectionManager) -> None:
        self._conn_manager = connection_manager

    # ------------------------------------------------------------------
    # save_chunk
    # ------------------------------------------------------------------

    def save_chunk(self, chunk: FileChunk) -> Result[FileChunk]:
        """Save a chunk, returning the saved entity.

        Uses INSERT ... ON CONFLICT(id) DO UPDATE for upsert semantics on the id column.
        """
        conn = self._conn_manager.get_connection()
        try:
            row = _chunk_to_row(chunk)
            conn.execute(
                """INSERT INTO file_chunks
                   (id, file_id, memory_id, chunk_index, start_line, end_line,
                    content_hash, content_type, is_partial, created_at, updated_at)
                   VALUES
                   (:id, :file_id, :memory_id, :chunk_index, :start_line, :end_line,
                    :content_hash, :content_type, :is_partial, :created_at, :updated_at)
                   ON CONFLICT(id) DO UPDATE SET
                       file_id = excluded.file_id,
                       memory_id = excluded.memory_id,
                       chunk_index = excluded.chunk_index,
                       start_line = excluded.start_line,
                       end_line = excluded.end_line,
                       content_hash = excluded.content_hash,
                       content_type = excluded.content_type,
                       is_partial = excluded.is_partial,
                       created_at = excluded.created_at,
                       updated_at = excluded.updated_at""",
                row,
            )
            conn.commit()
            return Result.ok(chunk)
        except Exception as e:
            conn.rollback()
            return Result.ko([ErrorWithDetails("CHUNK_SAVE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_chunk_by_id
    # ------------------------------------------------------------------

    def get_chunk_by_id(self, chunk_id: str) -> Result[Optional[FileChunk]]:
        """Find a chunk by its id."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_chunks WHERE id = ?",
                (chunk_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return Result.ok(None)
            return Result.ok(_row_to_chunk(row))
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_chunks_by_file_id
    # ------------------------------------------------------------------

    def get_chunks_by_file_id(self, file_id: str) -> Result[List[FileChunk]]:
        """Find all chunks belonging to a file, ordered by chunk_index."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_chunks WHERE file_id = ? ORDER BY chunk_index ASC",
                (file_id,),
            )
            rows = cursor.fetchall()
            chunks = [_row_to_chunk(row) for row in rows]
            return Result.ok(chunks)
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_FILE_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_chunk_by_memory_id
    # ------------------------------------------------------------------

    def get_chunk_by_memory_id(self, memory_id: str) -> Result[Optional[FileChunk]]:
        """Find a chunk by its associated memory id."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_chunks WHERE memory_id = ? LIMIT 1",
                (memory_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return Result.ok(None)
            return Result.ok(_row_to_chunk(row))
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_MEMORY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_chunks_by_memory_id
    # ------------------------------------------------------------------

    def get_chunks_by_memory_id(self, memory_id: str) -> Result[List[FileChunk]]:
        """Find all chunks by their associated memory id."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_chunks WHERE memory_id = ?",
                (memory_id,),
            )
            rows = cursor.fetchall()
            chunks = [_row_to_chunk(row) for row in rows]
            return Result.ok(chunks)
        except Exception as e:
            return Result.ko([ErrorWithDetails("CHUNK_GET_BY_MEMORY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # delete_chunk
    # ------------------------------------------------------------------

    def delete_chunk(self, chunk_id: str) -> Result[bool]:
        """Delete a chunk by id, returning True if it existed."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM file_chunks WHERE id = ?",
                (chunk_id,),
            )
            conn.commit()
            return Result.ok(cursor.rowcount > 0)
        except Exception as e:
            conn.rollback()
            return Result.ko([ErrorWithDetails("CHUNK_DELETE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)
