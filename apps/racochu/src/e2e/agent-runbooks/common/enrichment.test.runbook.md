> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Enrichment scenario

Verify the LLM enrichment pipeline end-to-end (general MCP functionality — **sourceType-agnostic**). Fixtures go to `tmp/vault/` (vault sourceType); because enrichment is sourceType-agnostic, any bank works — this runbook pins `tmp-vault` for determinism.

**Bank scoping is MANDATORY (D39):** Every bank-scoped MCP call must specify `memory_bank="tmp-vault"` — the `tmp-vault` source id from `dev.yaml`. This applies to `searchFiles`, `recallMemory`, `getMemoryStats`, `forgetMemory`. `listMemoryBanks` is the only exception: it takes no `memory_bank` (it lists all banks) and is used here only to confirm `tmp-vault` exists. Never omit, never mix.

> **Enrichment contract (`mastraDocTitle` / `mastraDocKeywords`):** When enrichment is enabled and the LLM endpoint responds, the chunker stamps each chunk's metadata with:
> - `mastraDocTitle` — LLM-extracted document title (non-empty string)
> - `mastraDocKeywords` — LLM-extracted document keywords (non-empty string)
>
> These keys propagate to **all** chunks of the document, are stored with the memory, and surface in the recall output. Enrichment is **best-effort**: if the LLM is unreachable or enrichment is disabled, the keys are **absent** — enrichment never blocks ingestion.

### Test Objective

Verify end-to-end enrichment feature in racochu:
1. Does the enrichment code path actually execute?
2. Does the LLM endpoint respond?
3. Are enriched chunks actually being stored with metadata (`mastraDocTitle`, `mastraDocKeywords`)?

### Prerequisites

- racochu running with enrichment enabled in config (`enrichment.enabled: true` in `dev.yaml`)
- LLM endpoint at `https://lite-llm.lan/v1` reachable
- bensyne-dev MCP tools available
- `tmp/vault/` directory writable

### Test Steps

#### Step 1: Check Current State

- Call `listMemoryBanks` (lists all banks; no bank param) → confirm `tmp-vault` appears.
  - **Note:** a bank may first appear in `listMemoryBanks` only after its initial ingest has completed — if it is missing, wait ~5s and re-list before failing.
- Call `getMemoryStats(memory_bank="tmp-vault")` to see the current memory count.
- Call `recallMemory("RB_ENRICH_001", memory_bank="tmp-vault", limit=5)` → expect 0 results (clean start).
- **PASS:** `tmp-vault` bank present; `RB_ENRICH_001` recall returns 0 rows.
- **FAIL signature:** `RB_ENRICH_001` recall returns rows on a clean start ⇒ leftover fixture from a prior run — clean up before proceeding.

#### Step 2: Create a test file with enrichable content

Create a file with a clear, identifiable topic that the LLM should be able to title + keyword. The `RB_ENRICH_001` token makes it discoverable:

```bash
mkdir -p tmp/vault

cat > tmp/vault/rb-enrichment-test.md <<'EOF'
# The Water Cycle and Its Impact on Ecosystems

RB_ENRICH_001. This document explains how the water cycle functions and why it is critical to terrestrial ecosystems.

## Evaporation and Transpiration

Water moves from oceans and lakes into the atmosphere through evaporation, and from plants through transpiration.

## Condensation and Precipitation

As water vapor rises and cools, it condenses into clouds and returns to Earth as rain or snow.

## Importance to Life

The water cycle regulates climate, replenishes freshwater, and supports nearly all life on Earth.
EOF
```

Wait **≥3s** for debounce + chunking + enrichment (the LLM call is slower than plain chunking — allow the full timeout).

#### Step 3: Discover file_id via search

- Call `searchFiles("RB_ENRICH_001", memory_bank="tmp-vault", limit=5)` → `enrich_id` = the file-backed group's `file.id` (`file != null`).
- **PASS:** a file-backed group is returned with a non-empty `file.id`.
- **FAIL signature:** 0 results after ≥3s (and one +3s retry) ⇒ fixture not ingested (wrong bank, or racochu not watching `tmp/vault/`).

#### Step 4: Verify enrichment metadata on recalled chunks

- Call `recallMemory("RB_ENRICH_001", memory_bank="tmp-vault", limit=5)`; identify the row(s) for the test file (row whose `file_enrichment.file.id == enrich_id`, or whose content contains `RB_ENRICH_001`).
- **PASS — enriched metadata present:** the recalled chunk(s) carry enrichment metadata — a non-empty `mastraDocTitle` and a non-empty `mastraDocKeywords`.
- **PASS — title is meaningful:** `mastraDocTitle` is **not** a raw file path; it reflects the document's semantic topic (e.g. mentions the "water cycle" or similar).
- **FAIL signature:** the recalled chunk has **no** `mastraDocTitle` / `mastraDocKeywords` keys ⇒ enrichment did not run, or the LLM did not respond (check Step 5 logs).
- > **Where to look:** the enrichment keys live in the memory's metadata. Inspect the recalled row (or its `metadata` block) for the keys `mastraDocTitle` and `mastraDocKeywords`.

#### Step 5: Check Logs (enrichment executed)

- Check logs at `~/.local/share/racochu/logs` to verify enrichment executed for the test file.
- **PASS:** the logs contain enrichment activity, e.g. `[enrichment] Attempting enrichment` followed by `[enrichment] LLM created` (and a successful metadata extraction) for the fixture.
- **FAIL signature:** the logs show `[enrichment] Skipped` or `[enrichment] ExtractMetadata failed` ⇒ the enrichment path was not taken, or the LLM failed — confirm the LLM endpoint is reachable and `enrichment.enabled: true` in `dev.yaml`.

#### Step 6: Cleanup

- Delete the test file from `tmp/vault/`:
  - `tmp/vault/rb-enrichment-test.md`
- Wait **≥3s** for debounce + forget.
- Call `recallMemory("RB_ENRICH_001", memory_bank="tmp-vault", limit=5)` → confirm memories were cleaned up (0 results).
- **PASS:** 0 results for `RB_ENRICH_001` after deletion.

### Expected Outcomes Summary

| Check | Expected |
|-------|----------|
| Bank scoping | Every bank-scoped call uses `memory_bank="tmp-vault"` |
| Fixture identifiable | Unique `RB_ENRICH_001` token |
| Enrichment executed | Logs show `[enrichment] Attempting enrichment` + `[enrichment] LLM created` |
| LLM responded | Enriched metadata present on recalled chunks |
| Enriched metadata | Non-empty `mastraDocTitle` + `mastraDocKeywords` |
| Title meaningful | `mastraDocTitle` reflects the document's semantic topic (not a raw path) |
| Cleanup | Memories forgotten after file deletion (0 results) |
