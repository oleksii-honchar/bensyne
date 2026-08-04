"""Bank/database management."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class BankManager:
    """Resolves SQLite database paths per memory bank.

    Path rules (ADR-005):
      - Default bank: {data_dir}/mnemosyne.db
      - Custom bank:  {data_dir}/banks/{memory_bank}/mnemosyne.db
    """

    def __init__(self, data_dir: str, default_bank: str = "default") -> None:
        self.data_dir = Path(data_dir)
        self.default_bank = default_bank

    def get_bank_db_path(self, memory_bank: str) -> Path:
        """Return the SQLite path for the given memory bank.

        Ensures the parent directory exists (mkdir -p).
        """
        if memory_bank == self.default_bank:
            path = self.data_dir / "mnemosyne.db"
        else:
            path = self.data_dir / "banks" / memory_bank / "mnemosyne.db"

        path.parent.mkdir(parents=True, exist_ok=True)
        return path
