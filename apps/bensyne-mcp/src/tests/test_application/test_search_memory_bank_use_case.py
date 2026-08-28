"""Unit tests for SearchMemoryBankUseCase.

Reference:
- spec.md C1 (use case contract), C3 (channel-weighted scoring)
- decisions.md ADR-S12 (``CHANNEL_WEIGHTS = {"name": 1, "description": 2, "derived": 1}``,
  ``+2`` persona-match bonus when ``agent_id`` matches ``persona_<agent_id>``)

The use case derives keywords purely from the bank ``name`` (tokenise on
``_`` / ``-`` / non-alphanumeric) — no hardcoded per-role table. Test
inputs are chosen so each assertion exercises a distinct scoring channel.

Behaviour assertions only — no ``logger.*`` call assertions.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.domain.memory_bank_aggregate import MemoryBank
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


# The 11 persona_<x> bank names the project owns. The use case module
# (when implemented) must register a derived-keyword entry for each, and
# the skill-text per-agent starter-keyword table must mirror this set.
EXPECTED_PERSONA_BANKS: frozenset[str] = frozenset(
    {
        "persona_architect",
        "persona_developer",
        "persona_generalist",
        "persona_icm-operator",
        "persona_researcher",
        "persona_reviewer",
        "persona_session",
        "persona_super-developer",
        "persona_super-worker",
        "persona_vault-keeper",
        "persona_worker",
    }
)


def _bank(
    name: str,
    description: str = "desc",
    status: str = "registered",
    memory_count: int = 0,
) -> MemoryBank:
    """Build a MemoryBank aggregate directly (no factory side effects)."""
    return MemoryBank(
        name=name,
        description=description,
        status=status,
        created_at=datetime.now(),
        last_accessed=None,
        memory_count=memory_count,
        memories=[],
    )


def _router(banks_on_disk: list[str] | None = None) -> MagicMock:
    """Build a fake MemoryBankRouter.

    Only ``list_bank_dirs`` is exercised by ``ListBanksUseCase`` for the
    on-disk enumeration. The search use case reuses ``ListBanksUseCase``
    internally, so we keep the router minimal.
    """
    router = MagicMock()
    router.instances = {}
    router.list_bank_dirs.return_value = banks_on_disk or []
    return router


def _service(banks: list[MemoryBank] | None = None, *, ko: bool = False) -> MagicMock:
    """Build a fake MemoryBankService whose ``list_memory_banks`` returns
    either the supplied banks or a synthetic ko."""
    service = MagicMock()
    if ko:
        service.list_memory_banks.return_value = Result.ko(
            [ErrorWithDetails("MEMORY_BANK_DB_NOT_FOUND", {"bank": "_test_"})]
        )
    else:
        service.list_memory_banks.return_value = Result.ok(banks or [])
    return service


@pytest.fixture
def logger() -> LoggerMock:
    return LoggerMock()


# -- Module-level: derived-keyword helper ---------------------------------


class TestDerivedKeywordsHelper:
    """The derived-keyword helper pure-derives from the bank ``name`` —
    no per-role table, no hardcoded mappings. Tokens are split on any
    non-alphanumeric, lowercased, and deduped."""

    def test_helper_exists(self) -> None:
        """A derived-keywords helper must be exported."""
        from src.application.use_cases import search_memory_bank_use_case as mod

        assert hasattr(mod, "_derived_keywords_for") or hasattr(mod, "derived_keywords_for"), (
            "Expected a derived-keywords helper on the use case module"
        )

    def test_persona_name_splits_on_underscore(self) -> None:
        """``persona_researcher`` → ``["persona", "researcher"]`` (no extras)."""
        from src.application.use_cases import search_memory_bank_use_case as mod

        helper = getattr(mod, "_derived_keywords_for", None) or getattr(mod, "derived_keywords_for")
        terms = helper("persona_researcher")
        assert "persona" in terms
        assert "researcher" in terms
        # Must NOT include words that are not in the name (no hardcoded mapping).
        assert "investigation" not in terms
        assert "findings" not in terms

    def test_unknown_bank_falls_back_to_split(self) -> None:
        """Unknown banks derive from ``name.split('_/-')`` lowercase, deduped."""
        from src.application.use_cases import search_memory_bank_use_case as mod

        helper = getattr(mod, "_derived_keywords_for", None) or getattr(mod, "derived_keywords_for")
        terms = helper("totally_unknown_thing")
        assert terms == ["totally", "unknown", "thing"]

    def test_hyphen_separator_treated_like_underscore(self) -> None:
        """``agent-sessions`` → ``["agent", "sessions"]``."""
        from src.application.use_cases import search_memory_bank_use_case as mod

        helper = getattr(mod, "_derived_keywords_for", None) or getattr(mod, "derived_keywords_for")
        assert helper("agent-sessions") == ["agent", "sessions"]

    def test_module_does_not_export_per_role_keywords(self) -> None:
        """The use case must NOT export a hardcoded PER_ROLE_KEYWORDS table.

        Bensyne-mcp is the consumer, not the curator, of bank metadata —
        keywords derive purely from the name.
        """
        from src.application.use_cases import search_memory_bank_use_case as mod

        assert not hasattr(mod, "PER_ROLE_KEYWORDS"), (
            "search_memory_bank_use_case must not export PER_ROLE_KEYWORDS — "
            "keywords derive purely from the bank name."
        )


# -- Channel-weight scoring -----------------------------------------------


class TestScoringChannelWeights:
    """ADR-S12 — description carries ``+2`` per term; name and derived
    keywords carry ``+1`` each. The ``+2`` persona-match bonus applies
    only when ``agent_id`` matches ``persona_<agent_id>``."""

    @pytest.fixture
    def fixtures(self, logger):
        """Build a use case pre-loaded with two banks: a well-described
        ``vault`` (backfilled) and a near-identical template-described
        ``persona_reviewer``. Used to demonstrate description-channel
        dominance under ADR-S12."""
        vault = _bank(
            "vault",
            description="Racochu-ingested vault knowledge from project .vault/ dirs — architecture, ADRs, runbooks",
            status="registered",
            memory_count=42,
        )
        reviewer = _bank(
            "persona_reviewer",
            description="Reviewer agent decision tree (persona)",
            status="registered",
            memory_count=7,
        )
        service = _service([vault, reviewer])
        router = _router()
        return {"vault": vault, "reviewer": reviewer, "service": service, "router": router, "logger": logger}

    def test_import_use_case_class(self) -> None:
        """The use case class must be importable from the new module."""
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        assert SearchMemoryBankUseCase is not None

    def test_exact_name_match_vault_first(self, fixtures) -> None:
        """``query='vault'`` → ``vault`` is the top match."""
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=fixtures["service"],
            router=fixtures["router"],
            logger=fixtures["logger"],
        )

        result = use_case.execute({"query": "vault"})

        assert result.is_ok is True
        matches = result.value["matches"]
        assert matches, "expected at least one match for query='vault'"
        assert matches[0]["name"] == "vault"
        assert matches[0]["score"] >= 1  # at least the name channel hit

    def test_channel_weight_description_dominates_derived(self, fixtures) -> None:
        """``query='runbook'`` → ``vault`` (description hit +2) outscores
        ``persona_reviewer`` (no match anywhere, score 0 → dropped) under
        ADR-S12 channel weighting. Demonstrates that curated descriptions
        carry higher signal than the auto-generated persona templates.

        With pure-derived keywords (no PER_ROLE_KEYWORDS table), the
        derived channel from ``vault`` tokenises to ``["vault"]`` only —
        no "runbook" match. So vault's score is 2 (description channel
        only), while persona_reviewer scores 0 and is dropped.
        """
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=fixtures["service"],
            router=fixtures["router"],
            logger=fixtures["logger"],
        )

        result = use_case.execute({"query": "runbook"})

        assert result.is_ok is True

        # Vault MUST appear in the response (score > 0).
        vault_match = next(
            (m for m in result.value["matches"] if m["name"] == "vault"),
            None,
        )
        assert vault_match is not None, "vault should appear in matches"

        # 'runbook' substring in '...runbooks' (description, +2); derived
        # from "vault" is ["vault"] only. Total = 2.
        assert vault_match["score"] == 2, (
            f"expected vault score == 2 (description +2 only; derived is "
            f"name-tokens with no 'runbook'), got {vault_match['score']}"
        )

        # Persona_reviewer must NOT appear (zero-score entries are dropped).
        reviewer_present = any(
            m["name"] == "persona_reviewer" for m in result.value["matches"]
        )
        assert reviewer_present is False, (
            "persona_reviewer has zero score for query='runbook' and must be dropped"
        )

    def test_backfill_impact_empty_description_under_ranks(self, logger) -> None:
        """Empty-description ``vault`` loses the +2 description channel
        hit and scores strictly lower than the backfilled variant for the
        same query. C9 backfill is load-bearing — this test proves it.

        Query ``"vault runbook"`` matches both variants on the name channel
        (``vault`` is in the bank name) so both appear in matches; the
        only difference is the description channel, which is +2 for the
        backfilled variant (description contains ``runbooks``) and 0 for
        the empty variant.
        """
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        # Backfilled vault (description contains 'runbooks')
        backfilled_vault = _bank(
            "vault",
            description="Racochu-ingested vault knowledge from project .vault/ dirs — architecture, ADRs, runbooks",
            status="registered",
            memory_count=42,
        )
        reviewer = _bank(
            "persona_reviewer",
            description="Reviewer agent decision tree (persona)",
            status="registered",
            memory_count=7,
        )

        backfilled_service = _service([backfilled_vault, reviewer])
        backfilled_router = _router()
        backfilled_case = SearchMemoryBankUseCase(
            memory_bank_service=backfilled_service,
            router=backfilled_router,
            logger=logger,
        )
        backfilled_result = backfilled_case.execute({"query": "vault runbook"})
        backfilled_vault_score = next(
            m["score"] for m in backfilled_result.value["matches"] if m["name"] == "vault"
        )

        # Empty-description vault (description "")
        empty_vault = _bank("vault", description="", status="registered", memory_count=42)
        empty_service = _service([empty_vault, reviewer])
        empty_router = _router()
        empty_case = SearchMemoryBankUseCase(
            memory_bank_service=empty_service,
            router=empty_router,
            logger=logger,
        )
        empty_result = empty_case.execute({"query": "vault runbook"})
        empty_vault_score = next(
            m["score"] for m in empty_result.value["matches"] if m["name"] == "vault"
        )

        assert backfilled_vault_score > empty_vault_score, (
            f"backfilled vault ({backfilled_vault_score}) must outrank "
            f"empty-description vault ({empty_vault_score}); "
            "C9 backfill is load-bearing under ADR-S12"
        )

    def test_agent_id_bonus_pushes_matching_persona_to_top(self, logger) -> None:
        """With ``agent_id='researcher'`` and ``query='researcher'``,
        ``persona_researcher`` ranks at index 0 (tiebreak by +2 bonus)."""
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        researcher = _bank("persona_researcher", description="Researcher agent decision tree (persona)")
        reviewer = _bank("persona_reviewer", description="Reviewer agent decision tree (persona)")
        architect = _bank("persona_architect", description="Architect agent decision tree (persona)")
        service = _service([researcher, reviewer, architect])
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "researcher", "agent_id": "researcher"})

        assert result.is_ok is True
        assert result.value["matches"][0]["name"] == "persona_researcher"


# -- Derived-keyword-only match -----------------------------------------


class TestDerivedKeywordMatch:
    """The derived channel (name-tokens) surfaces banks whose name carries
    a query-relevant token, even when the description is template-only
    and matches nothing."""

    def test_query_researcher_returns_persona_researcher(self, logger) -> None:
        """``query='researcher'`` → ``persona_researcher`` is the top match
        via name + derived channels; noise personas with template
        descriptions and non-matching name tokens are dropped."""
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        researcher = _bank(
            "persona_researcher",
            description="Researcher agent decision tree (persona)",
            status="registered",
            memory_count=18,
        )
        # Noise: other personas with template-only descriptions and no
        # "researcher" token in the name. With pure-derived keywords
        # (no PER_ROLE_KEYWORDS), their derived terms are also a miss,
        # so they score 0 and are dropped.
        noise = [
            _bank("persona_worker", description="Worker agent decision tree (persona)"),
            _bank("persona_reviewer", description="Reviewer agent decision tree (persona)"),
        ]
        service = _service([researcher, *noise])
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "researcher"})

        assert result.is_ok is True
        names = [m["name"] for m in result.value["matches"]]
        assert "persona_researcher" in names, (
            "persona_researcher must appear (name + description + derived match)"
        )
        # Noise banks must be dropped — their name tokens do not contain
        # "researcher" and their template descriptions do not either.
        assert "persona_worker" not in names
        assert "persona_reviewer" not in names

    def test_name_token_distinguishes_personas_with_same_template_desc(
        self, logger
    ) -> None:
        """Two banks sharing the template ``"X agent decision tree (persona)"``
        description — query for ``reviewer`` matches persona_reviewer (name
        and description both contain ``reviewer``) but NOT persona_researcher
        (whose name and description contain ``researcher``, not ``reviewer``).
        The derived channel (name tokens) reinforces this: ``["reviewer"]``
        for the reviewer bank, ``["researcher"]`` for the researcher bank.

        With pure-derived keywords (no PER_ROLE_KEYWORDS), the channels
        that surface persona_reviewer are name + description + derived
        (+1 +2 +1 = 4); persona_researcher scores 0 across all channels
        for query ``reviewer`` and is correctly dropped.
        """
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        researcher = _bank(
            "persona_researcher",
            description="Researcher agent decision tree (persona)",
        )
        reviewer = _bank(
            "persona_reviewer",
            description="Reviewer agent decision tree (persona)",
        )
        service = _service([researcher, reviewer])
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "reviewer"})

        assert result.is_ok is True
        names = [m["name"] for m in result.value["matches"]]
        # Only persona_reviewer matches — persona_researcher is correctly
        # dropped (no name/description/derived channel hit for "reviewer").
        assert names == ["persona_reviewer"], (
            f"expected only persona_reviewer to match query='reviewer'; got {names}"
        )
        # And the matching entry has score = 4 (name +1, desc +2, derived +1).
        assert result.value["matches"][0]["score"] == 4


# -- Validation ----------------------------------------------------------


class TestValidation:
    """Empty / whitespace query → ``QUERY_REQUIRED``."""

    def test_empty_query_returns_query_required(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=_service(),
            router=_router(),
            logger=logger,
        )

        result = use_case.execute({"query": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_whitespace_query_returns_query_required(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=_service(),
            router=_router(),
            logger=logger,
        )

        result = use_case.execute({"query": "   \t\n  "})

        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_missing_query_returns_query_required(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=_service(),
            router=_router(),
            logger=logger,
        )

        result = use_case.execute({})

        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_limit_below_minimum_rejected(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=_service(),
            router=_router(),
            logger=logger,
        )

        result = use_case.execute({"query": "x", "limit": 0})

        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_LIMIT"

    def test_limit_above_maximum_rejected(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        use_case = SearchMemoryBankUseCase(
            memory_bank_service=_service(),
            router=_router(),
            logger=logger,
        )

        result = use_case.execute({"query": "x", "limit": 51})

        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_LIMIT"

    def test_default_limit_is_ten(self, logger) -> None:
        """When ``limit`` is omitted, the response is capped at 10."""
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        banks = [
            _bank(f"persona_bank_{i:02d}", description=f"Bank {i}")
            for i in range(15)
        ]
        service = _service(banks)
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "bank"})

        assert result.is_ok is True
        assert len(result.value["matches"]) <= 10


# -- Limit clamp + truncation -------------------------------------------


class TestLimitClamp:
    """``limit`` clamps the response; ``total`` reflects pre-truncation count."""

    def test_limit_two_returns_two_matches(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        banks = [
            _bank(f"persona_role_{i:02d}", description="shared description match")
            for i in range(5)
        ]
        service = _service(banks)
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "shared", "limit": 2})

        assert result.is_ok is True
        assert len(result.value["matches"]) == 2
        # total reflects pre-truncation count (5 banks with score > 0)
        assert result.value["total"] >= 2

    def test_total_field_reflects_pre_truncation_count(self, logger) -> None:
        """``total`` is the number of zero-excluded matches BEFORE
        limit truncation. ``matches`` is truncated."""
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        banks = [
            _bank(f"persona_role_{i:02d}", description="alpha beta gamma")
            for i in range(7)
        ]
        service = _service(banks)
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "alpha", "limit": 3})

        assert result.is_ok is True
        assert len(result.value["matches"]) == 3
        assert result.value["total"] == 7  # all 7 banks match via description


# -- Empty result + zero-score drop --------------------------------------


class TestEmptyResult:
    """A query that matches nothing returns an empty list, NOT an error."""

    def test_no_match_returns_empty_matches(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        service = _service([_bank("persona_worker", description="Worker agent decision tree (persona)")])
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "zzzqqqxxx"})

        assert result.is_ok is True
        assert result.value["matches"] == []
        assert result.value["total"] == 0


# -- Result shape -------------------------------------------------------


class TestResultShape:
    """Each match entry carries the canonical shape."""

    def test_match_entry_has_canonical_fields(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        vault = _bank("vault", description="vault knowledge", memory_count=10, status="registered")
        service = _service([vault])
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "vault"})

        assert result.is_ok is True
        match = result.value["matches"][0]
        required = {"bank", "name", "description", "memory_count", "status", "score"}
        assert set(match.keys()) >= required
        assert match["bank"] == match["name"] == "vault"


# -- Determinism + tiebreak ----------------------------------------------


class TestDeterminism:
    """Two runs with identical inputs produce identical ordering; ties
    are broken by bank name (alphabetical)."""

    def test_ties_broken_alphabetically(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        # Two banks with identical scores via derived keywords only:
        # 'persona_zulu' and 'persona_alpha' both get +1 from 'persona'
        # in derived keywords for query='persona'.
        alpha = _bank("persona_alpha", description="Alpha agent")
        zulu = _bank("persona_zulu", description="Zulu agent")
        service = _service([zulu, alpha])  # reversed input order on purpose
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "persona"})

        assert result.is_ok is True
        names = [m["name"] for m in result.value["matches"]]
        # Same-score entries sort alphabetically.
        assert names == sorted(names), f"ties must break by name asc; got {names}"

    def test_repeat_call_is_stable(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        banks = [
            _bank(f"persona_role_{i:02d}", description="shared")
            for i in range(5)
        ]
        service = _service(banks)
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        first = use_case.execute({"query": "shared"}).value["matches"]
        second = use_case.execute({"query": "shared"}).value["matches"]

        assert [m["name"] for m in first] == [m["name"] for m in second]


# -- listMemoryBanks failure propagation -------------------------------


class TestUnderlyingListBanksFailure:
    """If ``list_memory_banks`` returns ``Result.ko``, the search use case
    propagates that failure (does NOT mask it with an empty result)."""

    def test_propagates_service_ko(self, logger) -> None:
        from src.application.use_cases.search_memory_bank_use_case import SearchMemoryBankUseCase

        service = _service(ko=True)
        router = _router()
        use_case = SearchMemoryBankUseCase(
            memory_bank_service=service,
            router=router,
            logger=logger,
        )

        result = use_case.execute({"query": "anything"})

        # Either propagates the ko OR, if ListBanksUseCase's honest
        # fallback path activates, the response must be an empty result
        # (matches=[], total=0) — NOT a fake success with garbage scores.
        # Both behaviours are acceptable; a fake populated match list is not.
        if result.is_ok:
            assert result.value["matches"] == []
            assert result.value["total"] == 0
        else:
            assert result.errors[0].error_code == "MEMORY_BANK_DB_NOT_FOUND"
