> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Center-chunk scenario

### Test Objective

Verify `fetchFile` neighbor-window mode — `center_chunk_index` + `adjacent_chunks`, window clamping, and error codes.

> **Dynamic discovery mandate:** chunk indices are discovered **dynamically** from the baseline `fetchFile` call (step 2) — **never hardcoded** (Mastra splits are variable; R3/impact S4).

### Pre-Run Clean (STEP 0)

**Why (D41 §2.4):** start from an EMPTY bank so `chunk_index` values are discovered fresh — no stale index values left over from earlier runs.

> **Non-dense indices:** stored `chunk_index` values start at 0 but are **not guaranteed dense or contiguous** (Mastra may skip/merge sections — observed live: `[0,1,2,4,5,7,8,10,11,12]`). All assertions below use the DYNAMICALLY DISCOVERED values, never positional arithmetic like `N−1`.

```bash
# DATA_DIR = bensyne-mcp data dir. scripts/start.sh defaults to
# MNEMOSYNE_DATA_DIR=./data/dev → server runs with --data-dir ./data/dev
# (verified live: scripts/start.sh:24; the server's CWD is apps/bensyne-mcp).
# Resolves to apps/bensyne-mcp/data/dev.
# VERIFY YOUR OWN SERVER: ps aux | grep "main.py --port" | grep data-dir
# If your bensyne-mcp runs with a different --data-dir, substitute that dir.
#
# This bank's state is SPLIT across three locations (all bank-scoped, safe
# to remove):
#   {DATA_DIR}/banks/tmp-vault/ → mnemosyne.db
#   {DATA_DIR}/tmp-vault/       → file_metadata.db
#   apps/bensyne-mcp/data/tmp-vault/ → hash_index.db  ⚠️ POTENTIAL BUG
#     HashIndexService falls back to CWD-relative Path("data")/{bank}/
#     (hash_index_service.py:144) and IGNORES --data-dir — verified live:
#     server runs with --data-dir ./data/dev but dedup reads
#     data/tmp-vault/hash_index.db. Left as-is (pre-existing, out of D41
#     scope); the runbook cleans the ACTUAL location.
rm -rf apps/bensyne-mcp/data/dev/banks/tmp-vault \
       apps/bensyne-mcp/data/dev/tmp-vault \
       apps/bensyne-mcp/data/tmp-vault

# Then RESTART bensyne-mcp so no stale in-process state persists (it reopens
# DBs per bank on first tool call; a restart guarantees a clean slate):
#   apps/bensyne-mcp/scripts/start.sh
```

### Fixtures

4 sections each **> 4000 chars** (prose `maxCharacters` 4000 in `dev.yaml` ⇒ ≥1 body chunk per section):

```bash
SEC=$(python3 -c "print('lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor. ' * 60)")

cat > tmp/vault/rb-center-target.md <<EOF
# Center Chunk Target

## Section One

RB_CENTER_SEC1 $SEC

## Section Two

RB_CENTER_SEC2 $SEC

## Section Three

RB_CENTER_SEC3 $SEC

## Section Four

RB_CENTER_SEC4 $SEC
EOF
```

Wait ≥3s for debounce + chunking + ingestion.

### Test Steps

#### Step 1: Discover file_id via search

- Call `searchFiles("RB_CENTER_SEC1", memory_bank="tmp-vault", limit=5)`
- **PASS:** ≥1 result with `file != null` (file-backed group); `file.id` non-empty.
- Record `file.id` as `file_id`.

#### Step 2: Baseline fetch — dynamic discovery of N and c

- Call `fetchFile(file_id, memory_bank="tmp-vault")`
- Let `N` = number of chunks.
- Let `c` = `chunk_index` of the chunk whose `text` contains `RB_CENTER_SEC2`.
- Let `max` = the **maximum stored `chunk_index` value** in this response (indices are non-dense; `max` may be greater than `N−1` — e.g. observed live `N=10, max=12`).
- **PASS:** `N >= 4`; `c` found; `reconstruction_status == "complete"`.

#### Step 3: 0-based value-match round-trip (neighbor window, adjacent_chunks=1)

`c` (step 2) is a `chunk_index` **VALUE** read straight from the whole-fetch response.
Round-tripping it proves the value-match contract end-to-end on real data:

- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=c, adjacent_chunks=1)`
- **PASS:**
  - `content == ""`
  - **round-trip:** the returned window contains **exactly the chunk whose `chunk_index` VALUE is `c`** (the one discovered in the whole fetch) — a chunk with `chunk_index == c` whose `text` contains `RB_CENTER_SEC2`
  - the window is **positional**: the center chunk sits at window position 1 (middle), with one neighbor on each side
  - `chunks` has **exactly 3** entries (center not at an edge of the stored list)
  - the returned `chunk_index` values are sorted ascending; **they are NOT guaranteed to be {c−1, c, c+1} numerically** (non-dense storage) — assert the center VALUE matches `c` and neighbors are the chunks immediately before/after it in the stored order
  - each chunk has non-empty `text`, a `section_header` key (non-empty string), and keys `id`/`file_id`/`start_line`/`end_line`/`metadata`

#### Step 4: Window clamping (0-based values; both edges valid)

- **High edge:** Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=max, adjacent_chunks=5)`
  (`max` = maximum stored `chunk_index` VALUE from step 2 — NOT `N−1`, which may not be a stored value under non-dense indexing).
  - **PASS:** no error; the returned window ends with the chunk whose `chunk_index == max`; `chunks` length == `N` (window clamped to the full file).
- **Low edge (center=0):** Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=0, adjacent_chunks=1)`
  - **PASS:** no error (center=0 is a valid stored value); left-clamped window — `chunks` has exactly 2 entries; the first entry has `chunk_index == 0`; the second is the next stored chunk in order (its value is not necessarily 1).

#### Step 5: Error codes (value-matched)

- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=999, adjacent_chunks=1)`
  (999 is a value with **no stored chunk** — the value-match miss, not a range/overflow check).
  - **PASS:** error result with code `CENTER_CHUNK_INDEX_OUT_OF_RANGE`, and the error details include `available_chunk_indexes` (the stored 0-based values) plus `center_chunk_index` and `total_chunks`.
- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=c, adjacent_chunks=10)`
  - **PASS:** error result with code `ADJACENT_CHUNKS_OUT_OF_RANGE`.

### Cleanup

- Delete the fixture: `tmp/vault/rb-center-target.md`
- Verify with `ls tmp/vault/` that the file is gone.
