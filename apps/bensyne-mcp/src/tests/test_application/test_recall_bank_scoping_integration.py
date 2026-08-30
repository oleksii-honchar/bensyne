"""RC5 integration — recallMemory bank scoping (D3).

The RC5 hypothesis: agents passing ``memory_bank="agent-persona_researcher"`` might
NOT actually scope recall to that bank.

This test exercises the REAL router + REAL bank-bound MnemosyneClients (no
mnemosyne mocking) to determine whether the router's ``get_instance(bank)`` +
client recall actually isolates banks, or whether cross-bank leakage exists.

Behavioral assertions only (which memories come back), no log assertions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Generator

import pytest

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.domain.config_models import InstancePoolConfig
from src.infrastructure.bank.router import MemoryBankRouter
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.utils.structured_logging import LoggerMock

PERSONA_BANK = "agent-persona_researcher"
OTHER_BANK = "agent-sessions"

# Distinctive tokens that should NOT collide across banks.
PERSONA_TOKEN = "quantum_flux_capacitor_persona_xyzzy"
OTHER_TOKEN = "gimbal_lock_session_token_plugh"


# ---------------------------------------------------------------------------
# Fixtures — real router, real bank-bound clients (integration-grade)
# ---------------------------------------------------------------------------


@pytest.fixture
def router(tmp_path: Path) -> Generator[MemoryBankRouter, None, None]:
    config = InstancePoolConfig(
        max_instances=5,
        eviction_timeout=300,
        data_dir=str(tmp_path),
        default_bank="default",
    )
    yield MemoryBankRouter(config=config)


def _seed(router: MemoryBankRouter, bank: str, content: str) -> str:
    """Seed one memory in the given bank via a REAL bank-bound client."""
    client = MnemosyneClient(memory_bank=bank, data_dir=router.config.data_dir)
    result = client.remember(content=content, source="rc5-integration")
    assert result.is_ok, f"seed failed for {bank}: {result.errors}"
    return result.value


def _no_enrichment() -> FileEnrichmentService:
    """A FileEnrichmentService stub that returns results unchanged (no file layer)."""
    from unittest.mock import MagicMock

    # The enrichment service is additive (adds a file_enrichment key). For this
    # isolation test we only care about WHICH memories are returned, so we patch
    # enrich() to pass rows through without touching the file repository.
    svc = FileEnrichmentService(file_service=MagicMock(), logger=LoggerMock())
    svc.enrich = lambda results, limit: results
    return svc


def _recall_via_router(router: MemoryBankRouter, bank: str, query: str) -> list[dict]:
    """Mirror handle_recall: resolve the bank-bound client via the router, then recall."""
    async def run() -> list[dict]:
        client = await router.get_instance(bank)
        use_case = RecallMemoryUseCase(
            mnemosyne_client=client,
            file_enrichment_service=_no_enrichment(),
            logger=LoggerMock(),
        )
        result = use_case.execute({"query": query, "memory_bank": bank})
        assert result.is_ok, f"recall failed: {result.errors}"
        return result.value["results"]

    return asyncio.run(run())


# ===================================================================
# RC5 — bank scoping is real, not documentation-only
# ===================================================================


class TestRecallBankScoping:
    def test_persona_memory_returned_for_persona_bank(
        self, router: MemoryBankRouter
    ) -> None:
        """Seeding agent-persona_researcher and recalling there returns the persona memory."""
        _seed(router, PERSONA_BANK, f"Note with {PERSONA_TOKEN}")

        results = _recall_via_router(router, PERSONA_BANK, PERSONA_TOKEN)

        assert any(PERSONA_TOKEN in r.get("content", "") for r in results), (
            f"Expected persona memory in {PERSONA_BANK}, got: {results}"
        )

    def test_persona_memory_not_leaked_to_other_bank(
        self, router: MemoryBankRouter
    ) -> None:
        """The same query against agent-sessions must NOT return the persona memory."""
        _seed(router, PERSONA_BANK, f"Note with {PERSONA_TOKEN}")
        _seed(router, OTHER_BANK, f"Note with {OTHER_TOKEN}")

        results = _recall_via_router(router, OTHER_BANK, PERSONA_TOKEN)

        assert not any(PERSONA_TOKEN in r.get("content", "") for r in results), (
            f"RC5 VIOLATION: persona memory leaked into {OTHER_BANK}: {results}"
        )

    def test_other_bank_memory_scoped_to_its_own_bank(
        self, router: MemoryBankRouter
    ) -> None:
        """agent-sessions recalls return agent-sessions memory, not the persona one."""
        _seed(router, PERSONA_BANK, f"Note with {PERSONA_TOKEN}")
        _seed(router, OTHER_BANK, f"Note with {OTHER_TOKEN}")

        results = _recall_via_router(router, OTHER_BANK, OTHER_TOKEN)

        assert any(OTHER_TOKEN in r.get("content", "") for r in results)
        assert not any(PERSONA_TOKEN in r.get("content", "") for r in results)

    def test_router_returns_distinct_bank_bound_clients(
        self, router: MemoryBankRouter
    ) -> None:
        """The router hands out a client bound to each requested bank (not a shared one)."""

        async def run() -> None:
            c_persona = await router.get_instance(PERSONA_BANK)
            c_other = await router.get_instance(OTHER_BANK)
            assert c_persona.memory_bank == PERSONA_BANK
            assert c_other.memory_bank == OTHER_BANK
            assert c_persona is not c_other

        asyncio.run(run())


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
