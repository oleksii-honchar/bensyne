"""Memory bank router module — re-exports from bank subpackage.

Provides backward-compatible import path: src.services.bank_router
"""

from src.services.bank.router import MemoryBankRouter

__all__ = ["MemoryBankRouter"]
