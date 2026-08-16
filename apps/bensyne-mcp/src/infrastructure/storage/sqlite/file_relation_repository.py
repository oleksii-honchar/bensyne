"""FileRelationRepository — SQLite implementation of FileRelationRepository using SQLAlchemy ORM.

Maps FileRelation domain entities to/from rows in the `file_relations` table via SQLAlchemy ORM.
Uses FileMetadataConnectionManager for Session management.
"""

from __future__ import annotations

from datetime import datetime
from src.domain.file_relation_entity import Direction, FileRelation, RelationType
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.models import FileRelationORM

# ---------------------------------------------------------------------------
# ORM ↔ FileRelation mapping helpers
# ---------------------------------------------------------------------------


def _orm_to_relation(orm: FileRelationORM) -> FileRelation:
    """Map a FileRelationORM instance to a FileRelation entity."""
    created_at = orm.created_at if orm.created_at else datetime.now()
    updated_at = orm.updated_at if orm.updated_at else created_at

    return FileRelation(
        id=orm.id,
        source_file_id=orm.source_file_id,
        target_file_id=orm.target_file_id,
        relation_type=RelationType(orm.relation_type),
        strength=float(orm.strength) if orm.strength is not None else 1.0,
        direction=Direction(orm.direction) if orm.direction else Direction.UNIDIRECTIONAL,
        description=orm.description,
        created_at=created_at,
        updated_at=updated_at,
    )


def _relation_to_orm(relation: FileRelation) -> FileRelationORM:
    """Map a FileRelation entity to a FileRelationORM instance."""
    return FileRelationORM(
        id=relation.id,
        source_file_id=relation.source_file_id,
        target_file_id=relation.target_file_id,
        relation_type=relation.relation_type.value,
        strength=relation.strength,
        direction=relation.direction.value,
        description=relation.description,
        created_at=relation.created_at,
        updated_at=relation.updated_at,
    )


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class FileRelationRepository:
    """SQLite-backed FileRelation repository using SQLAlchemy ORM.

    Args:
        connection_manager: FileMetadataConnectionManager for Session management.
    """

    def __init__(self, connection_manager: FileMetadataConnectionManager) -> None:
        self._conn_manager = connection_manager

    # ------------------------------------------------------------------
    # save_relation
    # ------------------------------------------------------------------

    def save_relation(self, relation: FileRelation) -> Result[FileRelation]:
        """Save a relation, returning the saved entity.

        Uses merge() for upsert semantics on the id column.
        """
        session = self._conn_manager.get_session()
        try:
            orm = _relation_to_orm(relation)
            session.merge(orm)
            session.commit()
            return Result.ok(relation)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("RELATION_SAVE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_relation_by_id
    # ------------------------------------------------------------------

    def get_relation_by_id(self, relation_id: str) -> Result[FileRelation | None]:
        """Find a relation by its id."""
        session = self._conn_manager.get_session()
        try:
            orm = session.query(FileRelationORM).filter(FileRelationORM.id == relation_id).first()
            if orm is None:
                return Result.ok(None)
            return Result.ok(_orm_to_relation(orm))
        except Exception as e:
            return Result.ko([ErrorWithDetails("RELATION_GET_BY_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_relations_by_file_id
    # ------------------------------------------------------------------

    def get_relations_by_file_id(self, file_id: str) -> Result[list[FileRelation]]:
        """Find all relations where the given file is either source or target."""
        session = self._conn_manager.get_session()
        try:
            orms = (
                session.query(FileRelationORM)
                .filter((FileRelationORM.source_file_id == file_id) | (FileRelationORM.target_file_id == file_id))
                .all()
            )
            relations = [_orm_to_relation(orm) for orm in orms]
            return Result.ok(relations)
        except Exception as e:
            return Result.ko([ErrorWithDetails("RELATION_GET_BY_FILE_ID_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # get_relations_by_type
    # ------------------------------------------------------------------

    def get_relations_by_type(self, relation_type: RelationType) -> Result[list[FileRelation]]:
        """Find all relations of a given type."""
        session = self._conn_manager.get_session()
        try:
            orms = session.query(FileRelationORM).filter(FileRelationORM.relation_type == relation_type.value).all()
            relations = [_orm_to_relation(orm) for orm in orms]
            return Result.ok(relations)
        except Exception as e:
            return Result.ko([ErrorWithDetails("RELATION_GET_BY_TYPE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)

    # ------------------------------------------------------------------
    # delete_relation
    # ------------------------------------------------------------------

    def delete_relation(self, relation_id: str) -> Result[bool]:
        """Delete a relation by id, returning True if it existed."""
        session = self._conn_manager.get_session()
        try:
            orm = session.query(FileRelationORM).filter(FileRelationORM.id == relation_id).first()
            if orm is None:
                return Result.ok(False)
            session.delete(orm)
            session.commit()
            return Result.ok(True)
        except Exception as e:
            session.rollback()
            return Result.ko([ErrorWithDetails("RELATION_DELETE_ERROR", {"error": str(e)})])
        finally:
            self._conn_manager.close_session(session)
