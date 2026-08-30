"""SearchMemoryBankUseCase — keyword-scored bank discovery.

Returns a ranked, deduped list of banks whose ``name`` + ``description``
match the query. Reuses ``ListBanksUseCase`` for the merged view
(filesystem ∪ pool ∪ registry), then applies inline substring scoring with
ADR-S12 channel weighting: ``description`` carries +2, ``name`` and
``derived`` carry +1 each. The +2 persona-match bonus applies when
``agent_id == f"agent-persona_{name}"``.

Scoring algorithm follows ``spec.md`` C3 verbatim — substring match on
each channel; no embeddings, no whole-word boundary. Derived keywords are
pure-derived from the bank ``name`` (split on non-alphanumeric, lowercase,
deduped) so the algorithm depends only on data bensyne-mcp already has
under ``list_memory_banks`` — no per-role keyword tables.

Rationale (per ADR-S2 / ADR-S8 / ADR-S12):

- Description is the highest-trust signal because it is human-curated
  via ``registerMemoryBank(name=..., description=...)``.
- Name is often a role slug (``agent-persona_<x>``, ``agent-sessions``,
  ``vault``) — a system identifier, not a vocabulary surface.
- Derived keywords normalise the name (split on ``_`` and ``-``) so that
  a query for ``reviewer`` matches a bank named ``agent-persona_reviewer``
  even when the description is missing or template-only.
- The +2 description weight incentivises bank owners to maintain their
  descriptions: a well-described bank beats a well-named bank on equal
  vocabulary.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog.stdlib

from src.application.use_cases.base_use_case import BaseUseCase
from src.application.use_cases.list_banks_use_case import ListBanksUseCase
from src.utils.result import ErrorWithDetails, Result

if TYPE_CHECKING:
    from src.application.services.memory_bank_service import MemoryBankService
    from src.infrastructure.bank.router import MemoryBankRouter


# Channel weights (ADR-S12): description is the highest-trust signal.
CHANNEL_WEIGHTS: dict[str, int] = {"name": 1, "description": 2, "derived": 1}
PERSONA_MATCH_BONUS: int = 2  # applied when agent_id matches agent-persona_<agent_id>
DEFAULT_LIMIT: int = 10
MIN_LIMIT: int = 1
MAX_LIMIT: int = 50

# Tokenisation: split on any non-alphanumeric, lowercase, drop empties.
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _derived_keywords_for(name: str) -> list[str]:
    """Pure-derive keywords from a bank name — no external data, no hardcoded
    per-role table. Returns name tokens (split on ``_`` / ``-`` / any
    non-alphanumeric), lowercased and deduped preserving first-seen order.

    Examples:
        ``agent-persona_reviewer`` → ``["agent", "persona", "reviewer"]``
        ``vault-racochu`` → ``["vault", "racochu"]``
        ``agent-sessions`` → ``["agent", "sessions"]``

    Helper is exported (``_`` prefix signals module-private but tests may
    introspect) so the derivation is unit-testable in isolation.
    """
    parts = _TOKEN_SPLIT_RE.split(name.lower())
    return list(dict.fromkeys(p for p in parts if p))


def _tokenize(query: str) -> list[str]:
    """Tokenise query: lowercase, split on non-alphanumeric, drop empties.

    Dedupes via dict.fromkeys to preserve first-seen order. Pure function.
    """
    tokens = _TOKEN_SPLIT_RE.split(query.lower())
    return list(dict.fromkeys(t for t in tokens if t))


class SearchMemoryBankUseCase(BaseUseCase[dict, dict]):
    """Discover memory banks relevant to a task.

    Reuses ``ListBanksUseCase`` for the merged view, then applies
    channel-weighted substring scoring per ADR-S12. Returns ranked matches
    sorted by ``(-score, name)`` with optional ``agent_id`` persona-match
    bonus.

    Wire response:
        ``{"matches": [...], "total": <int>}``

    Each match entry is the canonical listMemoryBanks shape plus a
    ``score`` field::

        {
            "bank": <str>,            # == name
            "name": <str>,
            "description": <str>,
            "memory_count": <int>,
            "status": <str>,
            "score": <int>,
        }
    """

    def __init__(
        self,
        memory_bank_service: "MemoryBankService",
        router: "MemoryBankRouter",
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.memory_bank_service = memory_bank_service
        self.router = router

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate query (required, non-empty after strip), limit (1–50,
        default 10), and agent_id (optional string)."""
        query = parameters.get("query")
        self.logger.debug(
            "validate_params:start",
            use_case="search_memory_bank",
            method="validate_params",
            has_query=isinstance(query, str),
            query_len=len(query) if isinstance(query, str) else None,
            limit=parameters.get("limit", DEFAULT_LIMIT),
            has_agent_id="agent_id" in parameters,
        )

        # Reject None, empty string, non-string, and whitespace-only.
        if not isinstance(query, str) or not query.strip():
            self.logger.debug(
                "validate_params:rejected",
                use_case="search_memory_bank",
                method="validate_params",
                error_code="QUERY_REQUIRED",
                reason="query is not a non-empty string",
            )
            return Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])

        limit = parameters.get("limit", DEFAULT_LIMIT)
        # Reject bools (subclass of int but semantically wrong), non-ints,
        # and out-of-range values. Per spec: 1 ≤ limit ≤ 50.
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < MIN_LIMIT
            or limit > MAX_LIMIT
        ):
            self.logger.debug(
                "validate_params:rejected",
                use_case="search_memory_bank",
                method="validate_params",
                error_code="INVALID_LIMIT",
                limit=limit,
            )
            return Result.ko([ErrorWithDetails("INVALID_LIMIT", {"limit": limit})])

        agent_id = parameters.get("agent_id")
        if agent_id is not None and not isinstance(agent_id, str):
            # Spec: malformed agent_id is ignored, not a hard error.
            self.logger.debug(
                "validate_params:agent_id_ignored",
                use_case="search_memory_bank",
                method="validate_params",
                agent_id_type=type(agent_id).__name__,
            )
            agent_id = None

        self.logger.debug(
            "validate_params:ok",
            use_case="search_memory_bank",
            method="validate_params",
            query_len=len(query.strip()),
            limit=limit,
            agent_id=agent_id,
        )
        return Result.ok(
            {"query": query.strip(), "limit": limit, "agent_id": agent_id}
        )

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Run the merged listing, score every bank against the query
        tokens, drop zero-score entries, sort by (-score, name), and
        truncate to ``limit``."""
        query: str = parameters["query"]
        limit: int = parameters["limit"]
        agent_id: str | None = parameters.get("agent_id")

        self.logger.debug(
            "execute:start",
            use_case="search_memory_bank",
            method="execute_internal",
            query=query,
            limit=limit,
            agent_id=agent_id,
        )

        # 1. Get the merged bank listing (filesystem ∪ pool ∪ registry).
        self.logger.debug(
            "execute:list_banks:start",
            use_case="search_memory_bank",
            method="execute_internal",
        )
        list_use_case = ListBanksUseCase(
            memory_bank_service=self.memory_bank_service,
            router=self.router,
            logger=self.logger,
        )
        list_result = list_use_case.execute({})
        if list_result.is_ko:
            # Honest fallback (per ADR-7 / ListBanksUseCase): warn and
            # continue with an empty universe. Matches are empty, total 0.
            self.logger.warning(
                "Underlying listMemoryBanks failed; search returning empty result",
                use_case="search_memory_bank",
                method="execute_internal",
                phase="list_banks",
                errors=list_result.get_formatted_errors(),
            )
            return Result.ok({"matches": [], "total": 0})

        banks: list[dict] = list_result.value["banks"]
        self.logger.debug(
            "execute:list_banks:ok",
            use_case="search_memory_bank",
            method="execute_internal",
            phase="list_banks",
            bank_count=len(banks),
        )

        # 2. Tokenise the query.
        query_terms: list[str] = _tokenize(query)
        self.logger.debug(
            "execute:tokenize:ok",
            use_case="search_memory_bank",
            method="execute_internal",
            phase="tokenize",
            query_terms=query_terms,
            term_count=len(query_terms),
        )

        # 3. Score every bank.
        scored: list[tuple[int, dict]] = []  # (score, bank_entry_with_score)
        self.logger.debug(
            "execute:scoring:start",
            use_case="search_memory_bank",
            method="execute_internal",
            phase="scoring",
            candidate_count=len(banks),
        )
        for bank in banks:
            name = bank["name"]
            description_lower = (bank.get("description") or "").lower()
            derived = _derived_keywords_for(name)

            score = 0
            for term in query_terms:
                if term in name.lower():
                    score += CHANNEL_WEIGHTS["name"]
                if term in description_lower:
                    score += CHANNEL_WEIGHTS["description"]
                if term in derived:
                    score += CHANNEL_WEIGHTS["derived"]

            # Persona-match bonus: only when agent_id matches an
            # agent-persona_<agent_id> bank name.
            if agent_id and name == f"agent-persona_{agent_id}":
                score += PERSONA_MATCH_BONUS

            self.logger.debug(
                "execute:scoring:bank",
                use_case="search_memory_bank",
                method="execute_internal",
                phase="scoring",
                bank=name,
                score=score,
                derived_terms=derived,
                has_description=bool(description_lower),
            )

            if score > 0:
                scored.append((score, {**bank, "score": score}))

        # 4. Sort by (-score, name) for deterministic ordering.
        scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))
        self.logger.debug(
            "execute:sort:ok",
            use_case="search_memory_bank",
            method="execute_internal",
            phase="sort",
            scored_count=len(scored),
        )

        # 5. Truncate to limit; total reflects pre-truncation count.
        total = len(scored)
        matches = [entry for _, entry in scored[:limit]]
        self.logger.debug(
            "execute:truncate:ok",
            use_case="search_memory_bank",
            method="execute_internal",
            phase="truncate",
            total=total,
            returned=len(matches),
            limit=limit,
        )

        return Result.ok({"matches": matches, "total": total})
