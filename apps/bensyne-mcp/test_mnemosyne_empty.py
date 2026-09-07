#!/usr/bin/env python3.12
"""Test if mnemosyne stores and retrieves empty content correctly."""

import tempfile
from pathlib import Path

# Import the mnemosyne library
from mnemosyne.core.memory import Mnemosyne

# Create a temporary directory for the database
with tempfile.TemporaryDirectory() as tmpdir:
    db_path = Path(tmpdir) / "test_mnemosyne.db"
    mnemo = Mnemosyne(bank="test_bank", db_path=str(db_path))

    # Store a memory with empty content
    memory_id = mnemo.remember(
        content="",
        source="test_script",
    )
    print(f"Stored memory with id: {memory_id}")

    # Retrieve the memory
    memory = mnemo.get(memory_id)
    print(f"Retrieved memory: {memory}")

    # Check if content is present
    if memory and "content" in memory:
        print(f"Content: '{memory['content']}'")
    else:
        print("ERROR: Content is missing or empty!")
