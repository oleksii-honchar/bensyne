"""Data directory resolution.

Resolution order (highest to lowest priority):
1. Explicit value (from CLI ``--data-dir`` or config)
2. ``DATA_DIR`` environment variable
3. ``"./data"`` (relative to CWD)

The Docker image sets ``DATA_DIR=/data`` via ``ENV``; local runs rely on the
relative ``./data`` default so the server boots on any writable CWD.
"""

from __future__ import annotations

import os

# Relative default data root — resolved against the current working directory.
DEFAULT_DATA_DIR = "./data"


def resolve_data_dir(explicit: str | None = None) -> str:
    """Resolve the data directory path.

    Args:
        explicit: Explicit data dir (from CLI or config). Wins over everything.

    Returns:
        The resolved data directory string.
    """
    if explicit:
        return explicit
    env = os.getenv("DATA_DIR")
    if env:
        return env
    return DEFAULT_DATA_DIR
