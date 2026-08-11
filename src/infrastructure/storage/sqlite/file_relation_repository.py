"""FileRelationRepositorySQLite — SQLite implementation of FileRelationRepository.

Maps FileRelation domain entities to/from rows in the `file_relations` table.
Uses FileMetadataConnectionManager for connection management.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from src.domain.entities.file_relation import Direction, FileRelation, RelationType
from src.domain.interfaces import FileRelationRepository
from src.domain.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)

# ---------------------------------------------------------------------------
# Row ↔ FileRelation mapping helpers
# ---------------------------------------------------------------------------

def _row_to_relation(row: sqlite3.Row) -> FileRelation:
    """Map a SQLite Row to a FileRelation entity."""
    created_at = datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now()
    updated_at = datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else created_at

    return FileRelation(
        id=row["id"],
        source_file_id=row["source_file_id"],
        target_file_id=row["target_file_id"],
        relation_type=RelationType(row["relation_type"]),
        strength=float(row["strength"]) if row["strength"] is not None else 1.0,
        direction=Direction(row["direction"]) if row["direction"] else Direction.UNIDIRECTIONAL,
        description=row["description"],
        created_at=created_at,
        updated_at=updated_at,
    )


def _relation_to_row(relation: FileRelation) -> dict:
    """Map a FileRelation entity to a dict suitable for SQLite INSERT/UPDATE."""
    return {
        "id": relation.id,
        "source_file_id": relation.source_file_id,
        "target_file_id": relation.target_file_id,
        "relation_type": relation.relation_type.value,
        "strength": relation.strength,
        "direction": relation.direction.value,
        "description": relation.description,
        "created_at": relation.created_at.isoformat(),
        "updated_at": relation.updated_at.isoformat(),
    }

# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class FileRelationRepositorySQLite(FileRelationRepository):
    """SQLite-backed implementation of FileRelationRepository.

    Args:
        connection_manager: FileMetadataConnectionManager for connection pooling.
    """

    def __init__(self, connection_manager: FileMetadataConnectionManager) -> None:
        self._conn_manager = connection_manager

    # ------------------------------------------------------------------
    # save_relation
    # ------------------------------------------------------------------

    def save_relation(self, relation: FileRelation) -> Result[FileRelation]:
        """Save a relation, returning the saved entity.

        Uses INSERT ... ON CONFLICT(id) DO UPDATE for upsert semantics on the id column.
        """
        conn = self._conn_manager.get_connection()
        try:
            row = _relation_to_row(relation)
            conn.execute(
                """INSERT INTO file_relations
                   (id, source_file_id, target_file_id, relation_type, strength,
                    direction, description, created_at, updated_at)
                   VALUES
                   (:id, :source_file_id, :target_file_id, :relation_type, :strength,
                    :direction, :description, :created_at, :updated_at)
                   ON CONFLICT(id) DO UPDATE SET
                       source_file_id = excluded.source_file_id,
                       target_file_id = excluded.target_file_id,
                       relation_type = excluded.relation_type,
                       strength = excluded.strength,
                       direction = excluded.direction,
                       description = excluded.description,
                       created_at = excluded.created_at,
                       updated_at = excluded.updated_at""",
                row,
            )
            conn.commit()
            return Result.ok(relation)
        except Exception as e:
            conn.rollback()
            return Result.ko([ErrorWithDetails("RELATION_SAVE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_relation_by_id
    # ------------------------------------------------------------------

    def get_relation_by_id(self, relation_id: str) -> Result[Optional[FileRelation]]:
        """Find a relation by its id."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_relations WHERE id = ?",
                (relation_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return Result.ok(None)
            return Result.ok(_row_to_relation(row))
        except Exception as e:
            return Result.ko([ErrorWithDetails("RELATION_GET_BY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_relations_by_file_id
    # ------------------------------------------------------------------

    def get_relations_by_file_id(self, file_id: str) -> Result[List[FileRelation]]:
        """Find all relations where the given file is either source or target."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_relations WHERE source_file_id = ? OR target_file_id = ?",
                (file_id, file_id),
            )
            rows = cursor.fetchall()
            relations = [_row_to_relation(row) for row in rows]
            return Result.ok(relations)
        except Exception as e:
            return Result.ko([ErrorWithDetails("RELATION_GET_BY_FILE_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # get_relations_by_type
    # ------------------------------------------------------------------

    def get_relations_by_type(self, relation_type: RelationType) -> Result[List[FileRelation]]:
        """Find all relations of a given type."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM file_relations WHERE relation_type = ?",
                (relation_type.value,),
            )
            rows = cursor.fetchall()
            relations = [_row_to_relation(row) for row in rows]
            return Result.ok(relations)
        except Exception as e:
            return Result.ko([ErrorWithDetails("RELATION_GET_BY_TYPE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)

    # ------------------------------------------------------------------
    # delete_relation
    # ------------------------------------------------------------------

    def delete_relation(self, relation_id: str) -> Result[bool]:
        """Delete a relation by id, returning True if it existed."""
        conn = self._conn_manager.get_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM file_relations WHERE id = ?",
                (relation_id,),
            )
            conn.commit()
            return Result.ok(cursor.rowcount > 0)
        except Exception as e:
            conn.rollback()
            return Result.ko([ErrorWithDetails("RELATION_DELETE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_connection(conn)
