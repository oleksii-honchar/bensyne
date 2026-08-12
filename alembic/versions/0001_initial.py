"""initial schema v1-v5

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-12

This migration replicates the V1-V5 schema from file_metadata_migrations.py:
- V1: files, file_chunks, file_relations tables with indexes
- V2: file_type, size, language, status columns + FTS5
- V3: id, content_hash, content_type, is_partial, updated_at on file_chunks
- V4: id, strength, direction, description, updated_at on file_relations
- V5: summary column on files
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # V1: schema_version tracking
    # ------------------------------------------------------------------
    op.create_table(
        'schema_version',
        sa.Column('version', sa.Integer(), nullable=False),
    )

    # ------------------------------------------------------------------
    # V1: files table
    # ------------------------------------------------------------------
    op.create_table(
        'files',
        sa.Column('id', sa.String(255), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('source_type', sa.String(50), nullable=False),
        sa.Column('file_role', sa.String(50), nullable=True),
        sa.Column('total_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_hash', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('keywords', sa.Text(), nullable=True),
        sa.Column('average_importance', sa.Float(), nullable=False, server_default='0.5'),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "source_type IN ('agent_session', 'file_system', 'git', 'database', 'external', 'remote', 'unknown')",
            name='ck_files_source_type',
        ),
        sa.CheckConstraint(
            "file_role IN ('config', 'code', 'docs') OR file_role IS NULL",
            name='ck_files_file_role',
        ),
    )

    # V1: files indexes
    op.create_index('idx_files_path', 'files', ['path'])
    op.create_index('idx_files_source_type', 'files', ['source_type'])
    op.create_index('idx_files_hash', 'files', ['file_hash'])
    op.create_index('idx_files_created_at', 'files', ['created_at'])

    # ------------------------------------------------------------------
    # V1: file_chunks table
    # ------------------------------------------------------------------
    op.create_table(
        'file_chunks',
        sa.Column('file_id', sa.String(255), nullable=False),
        sa.Column('memory_id', sa.String(255), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('start_line', sa.Integer(), nullable=True),
        sa.Column('end_line', sa.Integer(), nullable=True),
        sa.Column('section_header', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('file_id', 'memory_id'),
    )

    # V1: file_chunks indexes
    op.create_index('idx_file_chunks_memory_id', 'file_chunks', ['memory_id'])
    op.create_index('idx_file_chunks_file_id_chunk_index', 'file_chunks', ['file_id', 'chunk_index'])

    # ------------------------------------------------------------------
    # V1: file_relations table
    # ------------------------------------------------------------------
    op.create_table(
        'file_relations',
        sa.Column('source_file_id', sa.String(255), nullable=False),
        sa.Column('target_file_id', sa.String(255), nullable=False),
        sa.Column('relation_type', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(['source_file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_file_id'], ['files.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('source_file_id', 'target_file_id', 'relation_type'),
    )

    # V1: file_relations indexes
    op.create_index('idx_file_relations_target', 'file_relations', ['target_file_id'])
    op.create_index('idx_file_relations_type', 'file_relations', ['relation_type'])
    op.create_index('idx_file_relations_target_type', 'file_relations', ['target_file_id', 'relation_type'])

    # ------------------------------------------------------------------
    # V2: Add file_type, size, language, status to files
    # ------------------------------------------------------------------
    with op.batch_alter_table('files') as batch_op:
        batch_op.add_column(sa.Column('file_type', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('size', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('language', sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'status',
                sa.String(20),
                nullable=False,
                server_default='pending',
            )
        )
        batch_op.create_check_constraint(
            'ck_files_status',
            "status IN ('pending', 'indexed', 'archived', 'deleted')",
        )

    # V2: FTS5 virtual table for full-text search
    op.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
            path,
            keywords,
            tags,
            tokenize=trigram,
            content='files',
            content_rowid='rowid'
        )
        """
    )

    # V2: FTS5 triggers
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS files_fts_insert AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, path, keywords, tags)
            VALUES (NEW.rowid, NEW.path, NEW.keywords, NEW.tags);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS files_fts_delete AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, path, keywords, tags)
            VALUES ('delete', OLD.rowid, OLD.path, OLD.keywords, OLD.tags);
        END
        """
    )
    op.execute(
        """
        CREATE TRIGGER IF NOT EXISTS files_fts_update AFTER UPDATE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, path, keywords, tags)
            VALUES ('delete', OLD.rowid, OLD.path, OLD.keywords, OLD.tags);
            INSERT INTO files_fts(rowid, path, keywords, tags)
            VALUES (NEW.rowid, NEW.path, NEW.keywords, NEW.tags);
        END
        """
    )

    # ------------------------------------------------------------------
    # V3: Add columns to file_chunks
    # ------------------------------------------------------------------
    with op.batch_alter_table('file_chunks') as batch_op:
        batch_op.add_column(sa.Column('id', sa.String(255), nullable=True))
        batch_op.add_column(sa.Column('content_hash', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('content_type', sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column('is_partial', sa.Boolean(), nullable=False, server_default='0')
        )
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))

    # V3: Unique index on id
    op.create_index('idx_file_chunks_id', 'file_chunks', ['id'], unique=True)

    # V3: Backfill id from file_id + memory_id
    op.execute(
        "UPDATE file_chunks SET id = file_id || ':' || memory_id WHERE id IS NULL"
    )

    # ------------------------------------------------------------------
    # V4: Add columns to file_relations
    # ------------------------------------------------------------------
    with op.batch_alter_table('file_relations') as batch_op:
        batch_op.add_column(sa.Column('id', sa.String(255), nullable=True))
        batch_op.add_column(
            sa.Column('strength', sa.Float(), nullable=False, server_default='1.0')
        )
        batch_op.add_column(
            sa.Column('direction', sa.String(20), nullable=False, server_default='unidirectional')
        )
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))

    # V4: Unique index on id
    op.create_index('idx_file_relations_id', 'file_relations', ['id'], unique=True)

    # V4: Backfill id from source_file_id + target_file_id + relation_type
    op.execute(
        "UPDATE file_relations SET id = source_file_id || ':' || target_file_id || ':' || relation_type WHERE id IS NULL"
    )

    # ------------------------------------------------------------------
    # V5: Add summary column to files
    # ------------------------------------------------------------------
    with op.batch_alter_table('files') as batch_op:
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))

    # ------------------------------------------------------------------
    # Set schema version to 5
    # ------------------------------------------------------------------
    op.execute("INSERT INTO schema_version (version) VALUES (5)")


def downgrade() -> None:
    # Reverse in order: V5 → V4 → V3 → V2 → V1

    # V5: Remove summary
    with op.batch_alter_table('files') as batch_op:
        batch_op.drop_column('summary')

    # V4: Remove columns from file_relations
    op.drop_index('idx_file_relations_id', table_name='file_relations')
    with op.batch_alter_table('file_relations') as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('description')
        batch_op.drop_column('direction')
        batch_op.drop_column('strength')
        batch_op.drop_column('id')

    # V3: Remove columns from file_chunks
    op.drop_index('idx_file_chunks_id', table_name='file_chunks')
    with op.batch_alter_table('file_chunks') as batch_op:
        batch_op.drop_column('updated_at')
        batch_op.drop_column('is_partial')
        batch_op.drop_column('content_type')
        batch_op.drop_column('content_hash')
        batch_op.drop_column('id')

    # V2: Drop FTS5 triggers and table
    op.execute("DROP TRIGGER IF EXISTS files_fts_update")
    op.execute("DROP TRIGGER IF EXISTS files_fts_delete")
    op.execute("DROP TRIGGER IF EXISTS files_fts_insert")
    op.execute("DROP TABLE IF EXISTS files_fts")

    with op.batch_alter_table('files') as batch_op:
        batch_op.drop_check_constraint('ck_files_status')
        batch_op.drop_column('status')
        batch_op.drop_column('language')
        batch_op.drop_column('size')
        batch_op.drop_column('file_type')

    # V1: Drop tables (reverse creation order)
    op.drop_index('idx_file_relations_target_type', table_name='file_relations')
    op.drop_index('idx_file_relations_type', table_name='file_relations')
    op.drop_index('idx_file_relations_target', table_name='file_relations')
    op.drop_table('file_relations')

    op.drop_index('idx_file_chunks_file_id_chunk_index', table_name='file_chunks')
    op.drop_index('idx_file_chunks_memory_id', table_name='file_chunks')
    op.drop_table('file_chunks')

    op.drop_index('idx_files_created_at', table_name='files')
    op.drop_index('idx_files_hash', table_name='files')
    op.drop_index('idx_files_source_type', table_name='files')
    op.drop_index('idx_files_path', table_name='files')
    op.drop_table('files')

    op.drop_table('schema_version')
