"""FileRepository — SQLite FileRepository using SQLAlchemy ORM.

Maps File domain entities to/from rows in the `files` table via SQLAlchemy ORM.
Uses FileMetadataConnectionManager for Session management.
Supports full-text search via FTS5 on path, keywords, and tags.
"""

from __future__ import annotations

import json
from datetime import datetime
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.models.file_model import FileRole
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from sqlalchemy import text

from src.infrastructure.storage.sqlite.models import FileORM

# ---------------------------------------------------------------------------
# ORM ↔ File mapping helpers
# ---------------------------------------------------------------------------


def _orm_to_file(orm: FileORM) -> File:
    """Map a FileORM instance to a File entity."""
    keywords_raw = orm.keywords
    tags_raw = orm.tags

    aggregated_keywords: list[str] = json.loads(keywords_raw) if keywords_raw else []
    aggregated_tags: list[str] = json.loads(tags_raw) if tags_raw else []

    created_at = orm.created_at if orm.created_at else datetime.now()
    updated_at = orm.updated_at if orm.updated_at else created_at

    metadata_raw = orm.metadata_json
    try:
        metadata: dict[str, str] = json.loads(metadata_raw) if metadata_raw else {}
    except (TypeError, ValueError):
        metadata = {}

    return File(
        id=orm.id,
        path=orm.path,
        source_type=SourceType(orm.source_type),
        file_role=FileRole(orm.file_role) if orm.file_role else None,
        hash=orm.file_hash,
        file_type=orm.file_type,
        size=orm.size,
        language=orm.language,
        aggregated_keywords=aggregated_keywords,
        aggregated_tags=aggregated_tags,
        status=FileStatus(orm.status) if orm.status else FileStatus.PENDING,
        summary=orm.summary,
        total_chunks=orm.total_chunks if orm.total_chunks is not None else 0,
        average_importance=orm.average_importance if orm.average_importance is not None else 0.5,
        metadata=metadata,
        created_at=created_at,
        updated_at=updated_at,
    )


def _file_to_orm(file: File) -> FileORM:
    """Map a File entity to a FileORM instance."""
    return FileORM(
        id=file.id,
        path=file.path,
        source_type=file.source_type.value,
        file_role=file.file_role.value if file.file_role else None,
        file_hash=file.hash,
        file_type=file.file_type,
        size=file.size,
        language=file.language,
        summary=file.summary,
        total_chunks=file.total_chunks,
        average_importance=file.average_importance,
        metadata_json=json.dumps(file.metadata) if file.metadata else None,
        keywords=json.dumps(file.aggregated_keywords),
        tags=json.dumps(file.aggregated_tags),
        status=file.status.value,
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class FileRepository:
    """SQLite-backed File repository using SQLAlchemy ORM.

    Args:
        connection_manager: FileMetadataConnectionManager for Session management.
    """

    def __init__(self, connection_manager: FileMetadataConnectionManager) -> None:
        self._conn_manager = connection_manager

    # ------------------------------------------------------------------
    # save_file
    # ------------------------------------------------------------------

    def save_file(self, file: File) -> Result[File]:
        """Save a file, returning the saved entity.

        Uses merge() for upsert semantics — avoids the INSERT OR REPLACE
        pitfall where the DELETE phase triggers ON DELETE CASCADE on child
        tables (file_chunks, file_relations), causing loss of associated rows.
        """
        session = self._conn_manager.get_session()
        try:
            orm = _file_to_orm(file)
            session.merge(orm)
            session.commit()
            return Result.ok(file)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("FILE_SAVE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_file_by_id
    # ------------------------------------------------------------------

    def get_file_by_id(self, file_id: str) -> Result[File | None]:
        """Find a file by its id."""
        session = self._conn_manager.get_session()
        try:
            orm = session.get(FileORM, file_id)
            if orm is None:
                return Result.ok(None)
            return Result.ok(_orm_to_file(orm))
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_GET_BY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_file_by_path
    # ------------------------------------------------------------------

    def get_file_by_path(self, path: str) -> Result[File | None]:
        """Find a file by its path."""
        session = self._conn_manager.get_session()
        try:
            orm = session.query(FileORM).filter(FileORM.path == path).first()
            if orm is None:
                return Result.ok(None)
            return Result.ok(_orm_to_file(orm))
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_GET_BY_PATH_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # list_files
    # ------------------------------------------------------------------

    def list_files(self) -> Result[list[File]]:
        """List all saved files."""
        session = self._conn_manager.get_session()
        try:
            orms = session.query(FileORM).order_by(FileORM.created_at.desc()).all()
            files = [_orm_to_file(orm) for orm in orms]
            return Result.ok(files)
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_LIST_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # search_files_by_query
    # ------------------------------------------------------------------

    def search_files_by_query(self, query: str) -> Result[list[File]]:
        """Search files by query across path, keywords, and tags using FTS5."""
        session = self._conn_manager.get_session()
        try:
            # FTS5 requires raw SQL — SQLAlchemy doesn't have native FTS5 support
            result = session.execute(
                text(
                    """SELECT f.* FROM files f
                       INNER JOIN files_fts ON files_fts.rowid = f.rowid
                       WHERE files_fts MATCH :query
                       ORDER BY rank"""
                ),
                {"query": query},
            )
            rows = result.fetchall()
            # Convert to ORM objects via the session
            files: list[File] = []
            for row in rows:
                orm = session.get(FileORM, row[0])
                if orm is not None:
                    files.append(_orm_to_file(orm))
            return Result.ok(files)
        except Exception as e:
            return Result.ko([ErrorWithDetails("FILE_SEARCH_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # delete_file
    # ------------------------------------------------------------------

    def delete_file(self, file_id: str) -> Result[bool]:
        """Delete a file by id, returning True if it existed."""
        session = self._conn_manager.get_session()
        try:
            orm = session.get(FileORM, file_id)
            if orm is None:
                return Result.ok(False)
            session.delete(orm)
            session.commit()
            return Result.ok(True)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("FILE_DELETE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)
