#!/usr/bin/env python3
"""
Migration script: Move existing episodic memory embeddings from binary_vector
column to vec_episodes sqlite-vec ANN index table.

This migration is required because the old bypass mechanism in mnemosyne_client.py
stored embeddings in the binary_vector column instead of vec_episodes. Embedding
search (polyphonic recall) requires embeddings to be in vec_episodes.

Usage:
    python migrate-episodic-embeddings.py --db /path/to/mnemosyne.db
    python migrate-episodic-embeddings.py --db /path/to/mnemosyne.db --dry-run

If --db is not provided, it will search for all Bensyne database files.
"""

import sqlite3
import sys
import glob
import os
import time
import argparse
import numpy as np
from datetime import datetime, timezone
from pathlib import Path


def resolve_db_paths() -> list[str]:
    """Find all mnemosyne database paths across memory banks."""
    candidates = [
        # macOS
        "/Users/*/Library/Application Support/Bensyne/memories.db",
        "/Users/*/Library/Application Support/bensyne/memories.db",
        # Puma server (tuiteraz home) - banks directory
        "/home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/banks/*/mnemosyne.db",
        "/home/tuiteraz/bensyne/data/banks/*/mnemosyne.db",
        # Generic Puma paths - banks directory
        "/home/*/puma-lan/lite-llm/mcp/bensyne/data/banks/*/mnemosyne.db",
        "/home/*/bensyne/data/banks/*/mnemosyne.db",
        "/Volumes/Data/www/beaver/bensyne/data/banks/*/mnemosyne.db",
        "/Volumes/Data/Heroku/Bensyne/data/banks/*/mnemosyne.db",
        # Old-style single DB files
        "/home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/memories.db",
        "/home/tuiteraz/bensyne/data/memories.db",
        "/home/*/puma-lan/lite-llm/mcp/bensyne/data/memories.db",
        "/home/*/bensyne/data/memories.db",
        "/Volumes/Data/www/beaver/bensyne/data/memories.db",
        "/Volumes/Data/Heroku/Bensyne/data/memories.db",
        # Linux
        "/home/*/.local/share/bensyne/memories.db",
        "/home/*/.config/bensyne/memories.db",
        # Data directory
        "./data/memories.db",
        "./data/banks/*/mnemosyne.db",
    ]

    found = []
    for pattern in candidates:
        matches = glob.glob(pattern)
        for p in matches:
            if Path(p).exists() and p not in found:
                found.append(p)

    if not found:
        # Try environment variable
        data_dir = os.environ.get("BENSYNE_DATA_DIR")
        if data_dir:
            # Check for banks directory
            banks_pattern = f"{data_dir}/banks/*/mnemosyne.db"
            for p in glob.glob(banks_pattern):
                if Path(p).exists():
                    found.append(p)
            # Check for old-style single DB (deprecated, skip)
            # db_path = Path(data_dir) / "memories.db"
            # if db_path.exists() and str(db_path) not in found:
            #     found.append(str(db_path))

    # Debug: list all matches
    if not found:
        print("DEBUG: No matches found for any pattern")
        for pattern in candidates:
            matches = glob.glob(pattern)
            if matches:
                print(f"  {pattern} -> {matches}")
            else:
                print(f"  {pattern} -> []")
        try:
            print("DEBUG: Checking for banks in /home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/")
            listing = os.listdir("/home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/")
            print(f"  {listing}")
        except Exception as e:
            print(f"  Error: {e}")

    return found


def is_vec_available(conn) -> bool:
    """Check if sqlite-vec is available in this connection."""
    try:
        conn.execute("SELECT vec_version()")
        return True
    except Exception:
        return False


def migrate(db_path: str, dry_run: bool = False) -> int:
    """Run the migration. Returns number of embeddings migrated."""
    # Check if DB is writable (skip read-only root-owned DBs)
    if not os.access(db_path, os.W_OK):
        print(f"Skipping (read-only): {db_path}")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Load sqlite-vec extension
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
    except ImportError as e:
        print(f"ERROR: sqlite-vec not installed: {e}")
        conn.close()
        return 0
    except Exception as e:
        print(f"WARNING: Failed to load sqlite-vec: {e}")

    try:
        cursor = conn.cursor()

        # Check if vec_episodes table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='vec_episodes'
        """)
        if cursor.fetchone() is None:
            print(f"vec_episodes table not found in {db_path}. Skipping.")
            return 0

        # Check if episodic_memory table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='episodic_memory'
        """)
        if cursor.fetchone() is None:
            print(f"episodic_memory table not found in {db_path}. Skipping.")
            return 0

        # Identify episodic memories with binary_vector but no entry in vec_episodes
        cursor.execute("""
            SELECT e.id, e.rowid, e.binary_vector
            FROM episodic_memory e
            LEFT JOIN vec_episodes v ON e.rowid = v.rowid
            WHERE e.binary_vector IS NOT NULL AND e.binary_vector != '' AND v.rowid IS NULL
        """)
        rows = cursor.fetchall()

        if not rows:
            print(f"No embeddings to migrate in {db_path}")
            return 0

        if dry_run:
            print(f"[DRY-RUN] Would migrate {len(rows)} embeddings from binary_vector to vec_episodes in {db_path}")
            return len(rows)

        print(f"Migrating {len(rows)} embeddings from binary_vector to vec_episodes in {db_path}")

        # Import Mnemosyne's _vec_insert function
        try:
            from mnemosyne.core.beam import _vec_insert
        except ImportError as e:
            print(f"ERROR: Failed to import _vec_insert from mnemosyne: {e}")
            return 0

        migrated = 0
        errors = 0

        for row in rows:
            mem_id = row["id"]
            rowid = row["rowid"]
            binary_vector = row["binary_vector"]

            try:
                # Convert binary_vector to numpy array
                embedding = np.frombuffer(binary_vector, dtype=np.float32).tolist()

                # Insert into vec_episodes
                _vec_insert(conn, rowid, embedding)

                # Clear binary_vector after successful migration
                cursor.execute(
                    "UPDATE episodic_memory SET binary_vector = NULL WHERE rowid = ?",
                    (rowid,),
                )

                migrated += 1

                if migrated > 0 and migrated % 10 == 0:
                    print(f"  Migrated {migrated}/{len(rows)} embeddings...")

            except Exception as exc:
                errors += 1
                print(f"  ERROR migrating embedding for memory {mem_id} (rowid={rowid}): {exc}")

        conn.commit()
        print(f"Migration complete for {db_path}: {migrated} migrated, {errors} errors")
        return migrated
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Migrate episodic memory embeddings to vec_episodes")
    parser.add_argument("--db", type=str, help="Path to specific mnemosyne.db to migrate")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    args = parser.parse_args()

    # Determine db_paths
    if args.db:
        db_paths = [args.db]
    else:
        db_paths = resolve_db_paths()
        if not db_paths:
            print("ERROR: No databases found. Provide path with --db.")
            sys.exit(1)
        print(f"Found {len(db_paths)} databases to migrate:")
        for p in db_paths:
            print(f"  {p}")

    total_migrated = 0
    for db_path in db_paths:
        print(f"\nRunning migration on: {db_path}")
        migrated = migrate(db_path, dry_run=args.dry_run)
        total_migrated += migrated

    print(f"\n=== Migration complete: {total_migrated} total embeddings migrated across {len(db_paths)} databases ===")


if __name__ == "__main__":
    main()