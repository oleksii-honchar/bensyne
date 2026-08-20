> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Enrichment scenario

Verify the LLM enrichment pipeline end-to-end (general MCP functionality — **sourceType-agnostic**). Fixtures go to `tmp/vault/` (vault sourceType); because enrichment is sourceType-agnostic, any bank works — this runbook pins `tmp-vault` for determinism.

**Bank scoping is MANDATORY (D39):** Every bank-scoped MCP call must specify exactly one `memory_bank` matching the fixture it targets. The vault path uses `memory_bank="tmp-vault"`; the edge path (Step 5) uses `memory_bank="tmp-agent-sessions"`. This applies to `searchFiles`, `recallMemory`, `getMemoryStats`, `forgetMemory`. `listMemoryBanks` is the only exception: it takes no `memory_bank` (it lists all banks). Never omit, never mix a bank with a fixture from a different source.

> **Enrichment contract (`mastraDocTitle` / `mastraDocKeywords` / `mastraDocSummary`):** When enrichment is enabled and the LLM endpoint responds, the chunker stamps each chunk's metadata with:
> - `mastraDocTitle` — LLM-extracted document title (non-empty string)
> - `mastraDocKeywords` — LLM-extracted document keywords (non-empty string)
> - `mastraDocSummary` — LLM-extracted **whole-file** summary (non-empty string)
>
> These keys propagate to **all** chunks of the document, are stored with the memory, and surface in the recall output. The summary also flows to the file layer: `file_enrichment.summary_chain[0]` carries the **LLM whole-file summary** (NOT the mechanical `File: {path}. Keywords: …` fallback), and `related_files[].summary` carries each target file's whole-file summary.
>
> **Degraded-path control (mechanical fallback):** the LLM whole-file summary appears **only** when enrichment is enabled **and** the LLM is reachable. When either is off, `mastraDocSummary` is absent and `summary_chain[0]` degrades to the mechanical string `File: {path}. Keywords: …` (the fallback is the degraded-path control — a mechanical head starting with `File: ` is the expected signal that enrichment is NOT in effect, NOT a bug). Enrichment never blocks ingestion.

### Test Objective

Verify end-to-end enrichment feature in racochu:
1. Does the enrichment code path actually execute?
2. Does the LLM endpoint respond?
3. Are enriched chunks actually being stored with metadata (`mastraDocTitle`, `mastraDocKeywords`, `mastraDocSummary`)?
4. Does the **whole-file** LLM summary flow to the file layer (`summary_chain[0]` non-mechanical; `related_files[].summary` non-null on a real edge target)?

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
- **PASS — whole-file summary is LLM-generated (not mechanical):** on the same row, `file_enrichment.summary_chain[0]` is a **non-empty** string that does **NOT** start with `File: `. With enrichment enabled + LLM reachable, the chain head is the LLM whole-file summary.
- **FAIL signature (mechanical head):** `file_enrichment.summary_chain[0]` starts with `File: ` (the `File: {path}. Keywords: …` fallback) ⇒ the LLM summary did not flow — enrichment disabled or LLM unreachable (the degraded-path control from the contract note is in effect).
- **FAIL signature:** the recalled chunk has **no** `mastraDocTitle` / `mastraDocKeywords` keys ⇒ enrichment did not run, or the LLM did not respond (check Step 5 logs).
- > **Where to look:** the enrichment keys live in the memory's metadata. Inspect the recalled row (or its `metadata` block) for the keys `mastraDocTitle`, `mastraDocKeywords`, and `mastraDocSummary`; the whole-file summary also surfaces in `file_enrichment.summary_chain[0]`.

#### Step 5: Verify the whole-file summary propagates to a real edge target (agent-sessions)

The vault fixture is single-file (no relations), so `related_files[]` is empty there. To prove `related_files[].summary` carries a real target's **whole-file** summary, use the deterministic agent-sessions companion edge — enrichment is sourceType-agnostic, so `tmp-agent-sessions` is used for this one edge-only check (the `RB_ENRICH_EDGE_001` token scopes it).

Create the session + companion (relative to racochu root):

```bash
mkdir -p tmp/agent-sessions/rb-enrich-edge/findings

cat > tmp/agent-sessions/rb-enrich-edge/session.md <<'EOF'
---
sessionId: ses-rb-enrich-edge
createdAt: "2026-08-20T00:00:00Z"
status: active
phase: research
---

# Enrichment Edge Test

RB_ENRICH_EDGE_001. Session root content for the summary-on-edge test.
EOF
```

Wait **≥3s**, then:

```bash
cat > tmp/agent-sessions/rb-enrich-edge/findings/findings.md <<'EOF'
# Findings

RB_ENRICH_EDGE_001. Companion findings for the summary-on-edge test.
EOF
```

Wait **≥3s** for debounce + chunking + enrichment (the LLM call is slower than plain chunking — allow the full timeout). The companion detection gives `findings.md` a `parent_child` edge to `session.md`.

- Call `searchFiles("RB_ENRICH_EDGE_001", memory_bank="tmp-agent-sessions", limit=5)` → `edge_session_id` = the file-backed group for `session.md` (`file.id`); `edge_findings_id` = the file-backed group for `findings/findings.md` (`file.id`).
- Call `recallMemory("RB_ENRICH_EDGE_001", memory_bank="tmp-agent-sessions", limit=5)`; identify the **findings** row (row whose `file_enrichment.file.id == edge_findings_id`).
- **PASS — related_files summary non-null:** in the findings row's `file_enrichment.related_files[]`, the entry whose `id == edge_session_id` has a **non-null, non-empty** `summary` (the target `session.md`'s LLM whole-file summary).
- **PASS — target head is non-mechanical:** on the **session** row (row whose `file_enrichment.file.id == edge_session_id`), `file_enrichment.summary_chain[0]` does **NOT** start with `File: ` — confirming a real LLM summary is what propagates, not the mechanical fallback.
- **FAIL signature:** the `session.md` related entry's `summary` is null/empty, OR `edge_findings_id`'s `related_files[]` has no entry for `edge_session_id` ⇒ the target's summary did not flow (enrichment not applied to the target, or the edge is dangling).

#### Step 6: Check Logs (enrichment executed)

- Check logs at `~/.local/share/racochu/logs` to verify enrichment executed for the test file.
- **PASS:** the logs contain enrichment activity, e.g. `[enrichment] Attempting enrichment` followed by `[enrichment] LLM created` (and a successful metadata extraction) for the fixture.
- **FAIL signature:** the logs show `[enrichment] Skipped` or `[enrichment] ExtractMetadata failed` ⇒ the enrichment path was not taken, or the LLM failed — confirm the LLM endpoint is reachable and `enrichment.enabled: true` in `dev.yaml`.

#### Step 7: Cleanup

- Delete the test file from `tmp/vault/`:
  - `tmp/vault/rb-enrichment-test.md`
- Delete the agent-sessions edge fixture tree:
  - `rm -rf tmp/agent-sessions/rb-enrich-edge`
- Wait **≥3s** for debounce + forget.
- Call `recallMemory("RB_ENRICH_001", memory_bank="tmp-vault", limit=5)` → confirm memories were cleaned up (0 results).
- Call `recallMemory("RB_ENRICH_EDGE_001", memory_bank="tmp-agent-sessions", limit=5)` → confirm memories were cleaned up (0 results).
- **PASS:** 0 results for `RB_ENRICH_001` and `RB_ENRICH_EDGE_001` after deletion.

### Expected Outcomes Summary

| Check | Expected |
|-------|----------|
| Bank scoping | Every bank-scoped call uses `memory_bank="tmp-vault"` (vault path) or `memory_bank="tmp-agent-sessions"` (edge path); never omitted, never mixed |
| Fixture identifiable | Unique `RB_ENRICH_001` (vault) + `RB_ENRICH_EDGE_001` (edge) tokens |
| Enrichment executed | Logs show `[enrichment] Attempting enrichment` + `[enrichment] LLM created` |
| LLM responded | Enriched metadata present on recalled chunks |
| Enriched metadata | Non-empty `mastraDocTitle` + `mastraDocKeywords` + `mastraDocSummary` |
| Title meaningful | `mastraDocTitle` reflects the document's semantic topic (not a raw path) |
| Whole-file summary non-mechanical | `summary_chain[0]` does NOT start with `File: ` (LLM summary, not mechanical fallback) |
| Summary on edge target | `related_files[].summary` non-null for the `session.md` edge target |
| Mechanical-fallback control | Head starting with `File: ` is the expected degraded signal when enrichment/LLM is off |
| Cleanup | Memories forgotten after file deletion (0 results for both tokens) |
