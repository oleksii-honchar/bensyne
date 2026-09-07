#!/usr/bin/env python3.12
"""Query the mnemosyne database to check if content is stored for memory_id 6d2583771bab2e49."""

import sqlite3
from pathlib import Path

# The mnemosyne database path (from find command)
db_path = Path("/Users/tuiteraz/.hermes/mnemosyne/data/mnemosyne.db")

if not db_path.exists():
    print(f"Database not found at {db_path}")
    exit(1)

# Connect to the database
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cursor = conn.cursor()

# Query for the specific memory_id
memory_id = "6d2583771bab2e49"
cursor.execute("SELECT * FROM working_memory WHERE id = ?", (memory_id,))
row = cursor.fetchone()

if row:
    print(f"Found memory in working_memory:")
    print(f"  id: {row['id']}")
    print(f"  content: {row['content']}")
    print(f"  source: {row['source']}")
    print(f"  metadata: {row['metadata']}")
else:
    print(f"Memory {memory_id} not found in working_memory")
    # Try episodic_memory
    cursor.execute("SELECT * FROM episodic_memory WHERE id = ?", (memory_id,))
    row = cursor.fetchone()
    if row:
        print(f"Found memory in episodic_memory:")
        print(f"  id: {row['id']}")
        print(f"  content: {row['content']}")
        print(f"  source: {row['source']}")
        print(f"  metadata: {row['metadata']}")
    else:
        print(f"Memory {memory_id} not found in episodic_memory either")

conn.close()
