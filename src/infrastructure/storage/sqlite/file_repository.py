"""FileRepositorySQLite — SQLite implementation of FileRepository.

Maps File domain entities to/from rows in the `files` table.
Uses FileMetadataConnectionManager for connection management.
Supports full-text search via FTS5 on path, keywords, and tags.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import List, Optional

from src.domain.entities.file import File, FileStatus, SourceType
from src.domain.interfaces import FileRepository
from src.domain.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)

# ---------------------------------------------------------------------------
# Row ↔ File mapping helpers
# ---------------------------------------------------------------------------

def _row_to_file(row: sqlite3.Row) -> File:
    """Map a SQLite Row to a File entity."""
    # Parse JSON-encoded list fields
    keywords_raw = row["keywords"]
    tags_raw = row["tags"]

    aggregated_keywords: List[str] = json.loads(keywords_raw) if keywords_raw else []
    aggregated_tags: List[str] = json.loads(tags_raw) if tags_raw else []

    # Parse timestamps
    created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now()
    updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else created_at

    return File(
        id=row["id"],
        path=row["path"],
        source_type=SourceType(row["source_type"]),
        hash=row["file_hash"],
        file_type=row["file_type"],
        size=row["size"],
        language=row["language"],
        aggregated_keywords=aggregated_keywords,
        aggregated_tags=aggregated_tags,
        status=FileStatus(row["status"]) if row["status"] else FileStatus.PENDING,
        summary=row["summary"],
        created_at=created_at,
        updated_at=updated_at,
    )


def _file_to_row(file: File) -> dict:
    """Map a File entity to a dict suitable for SQLite INSERT/UPDATE."""
    return {
        "id": file.id,
        "path": file.path,
        "source_type": file.source_type.value,
        "file_hash": file.hash,
        "file_type": file.file_type,
        "size": file.size,
        "language": file.language,
        "summary": file.summary,
        "keywords": json.dumps(file.aggregated_keywords),
        "tags": json.dumps(file.aggregated_tags),
        "status": file.status.value,
        "created_at": file.created_at.isoformat(),
        "updated_at": file.updated_at.isoformat(),
    }

# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class FileRepositorySQLite(FileRepository):
    """SQLite-backed implementation of FileRepository.

    Args:
        connection_manager: FileMetadataConnectionManager for connection pooling.
    """

    def __init__(self, connection_manager: FileMetadataConnectionManager) -> None:
        self._conn_manager = connection_manager

    # ------------------------------------------------------------------
    # save_file
    # ------------------------------------------------------------------

    def save_file(self, file: File) -> Result[File]:
        """Save a file, returning the saved entity.

        Uses INSERT ... ON CONFLICT(id) DO UPDATE SET for upsert semantics.
        This avoids the INSERT OR REPLACE pitfall where the DELETE phase
        triggers ON DELETE CASCADE on child tables (file_chunks, file_relations),
        causing loss of associated rows when updating an existing file.
        """
        conn = self._conn_manager.get_connection()
        try:
            row = _file_to_row(file)
            conn.execute(
                """INSERT INTO files
                   (id, path, source_type, file_hash, file_type, size, language, summary,
                    keywords, tags, status, created_at, updated_at)
                   VALUES
                   (:id, :path, :source_type, :file_hash, :file_type, :size, :language, :summary,
                    :keywords, :tags, :status, :created_at, :updated_at)
                   ON CONFLICT(id) DO UPDATE SET
                       path = excluded.path,
                       source_type = excluded.source_type,
                       file_hash = excluded.file_hash,
                       file_type = excluded.file_type,
                       size = excluded.size,
                       language = excluded.language,
                       summary = excluded.summary,
                       keywords = excluded.keywords,
                       tags = excluded.tags,
                       status = excluded.status,
                       created_at = excluded.created_at,
                       updated_at = excluded.updated_at""",
                row,
            )
            conn.commit()
            return Result.ok(file)
        except Exception as e:
            conn.rollback()
            return Result.ko([ErrorWithDetails("FILE_SAVE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_file_by_id
    # ------------------------------------------------------------------

    def get_file_by_id(self, file_id: str) -> Result[Optional[File]]:
        """Find a file by its id."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM files WHERE id = ?",
                (file_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return Result.ok(None)
            return Result.ok(_row_to_file(row))
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_GET_BY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_file_by_path
    # ------------------------------------------------------------------

    def get_file_by_path(self, path: str) -> Result[Optional[File]]:
        """Find a file by its path."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM files WHERE path = ? LIMIT 1",
                (path,),
            )
            row = cursor.fetchone()
            if row is None:
                return Result.ok(None)
            return Result.ok(_row_to_file(row))
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_GET_BY_PATH_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # list_files
    # ------------------------------------------------------------------

    def list_files(self) -> Result[List[File]]:
        """List all saved files."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute("SELECT * FROM files ORDER BY created_at DESC")
            rows = cursor.fetchall()
            files = [_row_to_file(row) for row in rows]
            return Result.ok(files)
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_LIST_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # search_files_by_query
    # ------------------------------------------------------------------

    def search_files_by_query(self, query: str) -> Result[List[File]]:
        """Search files by query across path, keywords, and tags using FTS5."""
        conn = self._conn_manager.get_connection()
        try:
            # Use FTS5 for full-text search
            cursor = conn.execute(
                """SELECT f.* FROM files f
                   INNER JOIN files_fts ON files_fts.rowid = f.rowid
                   WHERE files_fts MATCH ?
                   ORDER BY rank""",
                (query,),
            )
            rows = cursor.fetchall()
            files = [_row_to_file(row) for row in rows]
            return Result.ok(files)
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_SEARCH_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # delete_file
    # ------------------------------------------------------------------

    def delete_file(self, file_id: str) -> Result[bool]:
        """Delete a file by id, returning True if it existed."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM files WHERE id = ?",
                (file_id,),
            )
            conn.commit()
            return Result.ok(cursor.rowcount > 0)
        except Exception as e:
            conn.rollback()
            return Result.ko([ErrorWithDetails("FILE_DELETE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)
