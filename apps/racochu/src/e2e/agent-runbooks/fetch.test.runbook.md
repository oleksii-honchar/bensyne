> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Fetch scenario

### Test Objective

Verify full-file reconstruction via `fetchFile` (no `center_chunk_index`).

### Fixtures

The fixture must be large enough to produce **≥ 2 Mastra chunks** (Mastra
merges small files into a single chunk — anything under ~5 KB is a single
chunk; a tiny fixture makes the Step 2 `chunks ≥ 2` assertion non-deterministic).
The template below produces ~5.5 KB (~3–4 chunks):

```bash
{
cat <<'EOF'
# Fetch Target

## Overview

RB_FETCH_OVERVIEW. The overview section of the fetch target.
EOF
for i in $(seq 1 40); do echo "Overview filler line $i describing the overview section."; done
cat <<'EOF'

## Details

RB_FETCH_DETAILS. The details section of the fetch target.
EOF
for i in $(seq 1 40); do echo "Details filler line $i describing the details section."; done
cat <<'EOF'

## Appendix

Appendix A: filler paragraph for tail content.
EOF
for i in $(seq 1 40); do echo "Appendix filler line $i verifying tail content survives reconstruction."; done
} > tmp/vault/rb-fetch-target.md
```

Wait ≥5s for debounce + chunking + ingestion. Verify ingestion by searching
for `RB_FETCH_OVERVIEW` (Step 1) — if 0 results, wait 5s and retry (up to 3
times). Enrichment (LLM metadata) is slower and is NOT required for this
runbook.

### Test Steps

#### Step 1: Discover file_id via search

- Call `searchFiles("RB_FETCH_OVERVIEW", memory_bank="tmp-vault", limit=5)`
- **PASS:** ≥1 result with `file != null` (file-backed group); `file.id` non-empty.
- Record `file.id` as `file_id`.

#### Step 2: Full-file reconstruction

- Call `fetchFile(file_id, memory_bank="tmp-vault")`
- **PASS:** `reconstruction_status == "complete"`; `missing_chunks == []`; `content` contains `RB_FETCH_OVERVIEW` **and** `RB_FETCH_DETAILS` **and** both section headers; `chunks` length ≥ 2; `chunk_index` values strictly increasing; every chunk `text` non-empty.

#### Step 3: Include metadata

- Call `fetchFile(file_id, memory_bank="tmp-vault", include_metadata=true)`
- **PASS:** the top-level `file` object is present (non-null) and carries `id`
  (== `file_id`), `total_chunks`, and `metadata`. (Contract:
  `include_metadata` populates the `file` block — it is null when omitted;
  per-chunk metadata is not part of the fetchFile contract.)

#### Step 4: Error — unknown file_id

- Call `fetchFile("file_does_not_exist_rbx", memory_bank="tmp-vault")`
- **PASS:** error result with code `FILE_NOT_FOUND`.

### Cleanup

- Delete the fixture: `tmp/vault/rb-fetch-target.md`
- Verify with `ls tmp/vault/` that the file is gone.
