"""SQLAlchemy declarative models for the file metadata SQLite schema.

Mirrors the V5 SQLite schema defined in file_metadata_migrations.py.
Uses SQLAlchemy 2.0 style with Mapped and mapped_column.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for file metadata models."""

    pass


# ---------------------------------------------------------------------------
# File
# ---------------------------------------------------------------------------


class FileORM(Base):
    """ORM model for the `files` table.

    Maps to the V5 schema with all columns including file_type, size,
    language, status, and summary.
    """

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_role: Mapped[str | None] = mapped_column(String(50))
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_hash: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str | None] = mapped_column(Text)
    size: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    metadata_json: Mapped[str | None] = mapped_column("metadata", Text)
    keywords: Mapped[str | None] = mapped_column(Text)
    average_importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    tags: Mapped[str | None] = mapped_column(Text)

    # Relationships
    chunks: Mapped[list["FileChunkORM"]] = relationship(
        "FileChunkORM", back_populates="file", cascade="all, delete-orphan"
    )
    relations_as_source: Mapped[list["FileRelationORM"]] = relationship(
        "FileRelationORM",
        foreign_keys="FileRelationORM.source_file_id",
        back_populates="source_file",
        cascade="all, delete-orphan",
    )
    relations_as_target: Mapped[list["FileRelationORM"]] = relationship(
        "FileRelationORM",
        foreign_keys="FileRelationORM.target_file_id",
        back_populates="target_file",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "source_type IN "
            "('obsidian', 'agent-sessions', 'vault', 'unknown')",
            name="ck_files_source_type",
        ),
        CheckConstraint(
            "file_role IN ('config', 'code', 'docs') OR file_role IS NULL",
            name="ck_files_file_role",
        ),
    )


# ---------------------------------------------------------------------------
# FileChunk
# ---------------------------------------------------------------------------


class FileChunkORM(Base):
    """ORM model for the `file_chunks` table.

    Junction between files and memories with positional metadata.
    """

    __tablename__ = "file_chunks"

    file_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    memory_id: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_line: Mapped[int | None] = mapped_column(Integer)
    end_line: Mapped[int | None] = mapped_column(Integer)
    section_header: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    # V3 columns
    id: Mapped[str] = mapped_column(String(255), unique=True)
    content_hash: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    is_partial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # V6 columns
    parent_unit_ref: Mapped[str | None] = mapped_column(Text)
    parent_unit_summary: Mapped[str | None] = mapped_column(Text)

    # Relationships
    file: Mapped["FileORM"] = relationship("FileORM", back_populates="chunks")

    __table_args__ = (PrimaryKeyConstraint("file_id", "memory_id"),)


# ---------------------------------------------------------------------------
# FileRelation
# ---------------------------------------------------------------------------


class FileRelationORM(Base):
    """ORM model for the `file_relations` table.

    Tracks semantic relationships between files.
    """

    __tablename__ = "file_relations"

    source_file_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_file_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())

    # V4 columns
    id: Mapped[str] = mapped_column(String(255), unique=True)
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="unidirectional")
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    source_file: Mapped["FileORM"] = relationship(
        "FileORM", foreign_keys=[source_file_id], back_populates="relations_as_source"
    )
    target_file: Mapped["FileORM"] = relationship(
        "FileORM", foreign_keys=[target_file_id], back_populates="relations_as_target"
    )

    __table_args__ = (PrimaryKeyConstraint("source_file_id", "target_file_id", "relation_type"),)
