"""RecallMemoryUseCase — searches memories via MnemosyneClient.

Validates non-empty query, delegates to MnemosyneClient.recall, enriches the
returned results with file-layer context via FileEnrichmentService (D7), and
returns Result with results and memory_bank.

The enrichment post-pass is additive: every result row gains a `file_enrichment`
key (None for pure memories — service contract). Enrichment work is scoped to
the results actually returned by mnemosyne (already capped by recall `limit`).
"""

import structlog.stdlib
from src.application.services.file_enrichment_service import FileEnrichmentService
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import ErrorWithDetails, Result


class RecallMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory recall via MnemosyneClient + file enrichment."""

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        file_enrichment_service: FileEnrichmentService,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.file_enrichment_service = file_enrichment_service

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that query is present and non-empty."""
        if not parameters.get("query"):
            return Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute recall via MnemosyneClient, then enrich returned results."""
        query = parameters["query"]
        limit = parameters.get("limit", 10)
        memory_bank = parameters.get("memory_bank", "default")
        enrich_limit = parameters.get("enrich_limit", 5)

        self.logger.info(
            "Recalling memory",
            use_case="recall_memory",
            method="execute_internal",
            query=query,
            limit=limit,
            enrich_limit=enrich_limit,
            memory_bank=memory_bank,
        )

        recall_result = self.mnemosyne_client.recall(query, limit)
        if recall_result.is_ko:
            return recall_result

        results = recall_result.value

        # Enrich only the results actually returned (budget capped by recall limit).
        enriched_results = self.file_enrichment_service.enrich(results, enrich_limit)

        self.logger.info(
            "Memory recalled",
            use_case="recall_memory",
            method="execute_internal",
            results_count=len(enriched_results),
            memory_bank=memory_bank,
        )

        return Result.ok(
            {
                "results": enriched_results,
                "memory_bank": memory_bank,
            }
        )
