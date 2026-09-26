#!/usr/bin/env python3
"""
Migration script: Move all existing working_memory rows to episodic_memory.

Determines TTL based on session_id prefix:
- session_id starting with 'agent-session-ses_' → 365 days
- All others → NULL (no expiry)

Usage:
    python migrate-working-to-episodic.py [db_path]

If db_path is not provided, it will search for the Bensyne data directory.
"""

import sqlite3
import sys
import glob
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def resolve_db_path() -> str | None:
    """Find the memories database path."""
    # Try known locations
    candidates = [
        # macOS
        "/Users/*/Library/Application Support/Bensyne/memories.db",
        "/Users/*/Library/Application Support/bensyne/memories.db",
        # Puma server (tuiteraz home)
        "/home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/memories.db",
        "/home/tuiteraz/bensyne/data/memories.db",
        # Generic Puma paths
        "/home/*/puma-lan/lite-llm/mcp/bensyne/data/memories.db",
        "/home/*/bensyne/data/memories.db",
        "/Volumes/Data/www/beaver/bensyne/data/memories.db",
        "/Volumes/Data/Heroku/Bensyne/data/memories.db",
        # Linux
        "/home/*/.local/share/bensyne/memories.db",
        "/home/*/.config/bensyne/memories.db",
        # Data directory
        "./data/memories.db",
    ]

    for pattern in candidates:
        matches = glob.glob(pattern)
        if matches:
            for p in matches:
                if Path(p).exists():
                    return p

    # Try environment variable
    import os
    data_dir = os.environ.get("BENSYNE_DATA_DIR")
    if data_dir:
        db_path = Path(data_dir) / "memories.db"
        if db_path.exists():
            return str(db_path)

    # Debug: list all matches
    print("DEBUG: No matches found for any pattern")
    for pattern in candidates:
        matches = glob.glob(pattern)
        if matches:
            print(f"  {pattern} -> {matches}")
        else:
            print(f"  {pattern} -> []")
    print("DEBUG: Checking for memories.db in /home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/")
    try:
        import os
        listing = os.listdir("/home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/")
        print(f"  {listing}")
    except Exception as e:
        print(f"  Error: {e}")

    return None


def get_session_ttl(session_id: str | None) -> datetime | None:
    """Determine TTL based on session_id.

    Returns:
        datetime if TTL applies (agent-session), None otherwise.
    """
    if session_id and session_id.startswith("agent-session-"):
        return datetime.now(timezone.utc) + timedelta(days=365)
    return None


def migrate(db_path: str) -> int:
    """Run the migration. Returns number of rows migrated."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        cursor = conn.cursor()

        # Query all working_memory rows
        cursor.execute("""
            SELECT id, content, source, timestamp, session_id, importance,
                   metadata_json, veracity, created_at
            FROM working_memory
        """)
        rows = cursor.fetchall()

        print(f"Migrating {len(rows)} rows from working_memory to episodic_memory...")

        migrated = 0
        for row in rows:
            mem_id = row["id"]
            content = row["content"]
            source = row["source"] or "bensyne:migration"
            timestamp = row["timestamp"]
            session_id = row["session_id"] or "bensyne"
            importance = row["importance"] or 0.5
            metadata_json = row["metadata_json"]
            veracity = row["veracity"] or "unknown"
            created_at = row["created_at"]

            # Determine TTL based on session_id
            ttl = get_session_ttl(session_id)
            valid_until = ttl.isoformat() if ttl else None

            # Direct INSERT into episodic_memory (INSERT OR IGNORE to avoid duplicates)
            cursor.execute("""
                INSERT OR IGNORE INTO episodic_memory
                (id, content, source, timestamp, session_id, importance,
                 metadata_json, summary_of, veracity, created_at, valid_until)
                VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)
            """, (
                mem_id,
                content,
                source,
                timestamp,
                session_id,
                importance,
                metadata_json,
                veracity,
                created_at,
                valid_until,
            ))

            if cursor.rowcount > 0:
                migrated += 1

            if migrated > 0 and migrated % 100 == 0:
                conn.commit()
                print(f"Migrated {migrated}/{len(rows)} rows...")

        conn.commit()
        print(f"Migration complete. {migrated} rows migrated.")

        return migrated
    finally:
        conn.close()


def main():
    # Determine db_path
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = resolve_db_path()
        if db_path is None:
            print("ERROR: memories.db not found. Provide path as argument.")
            sys.exit(1)
        print(f"Found database at: {db_path}")

    print(f"Running migration on: {db_path}")
    migrate(db_path)


if __name__ == "__main__":
    main()