> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Center-chunk scenario

### Test Objective

Verify `fetchFile` neighbor-window mode — `center_chunk_index` + `adjacent_chunks`, window clamping, and error codes.

> **Dynamic discovery mandate:** chunk indices are discovered **dynamically** from the baseline `fetchFile` call (step 2) — **never hardcoded** (Mastra splits are variable; R3/impact S4).

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
- **PASS:** `N >= 4`; `c` found; `reconstruction_status == "complete"`.

#### Step 3: Neighbor window (adjacent_chunks=1)

- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=c, adjacent_chunks=1)`
- **PASS:**
  - `content == ""`
  - `chunks` has **exactly 3** entries
  - `chunk_index` set == {c−1, c, c+1} and sorted ascending
  - each chunk has non-empty `text`, a `section_header` key (non-empty string), and keys `id`/`file_id`/`start_line`/`end_line`/`metadata`
  - the chunk with `chunk_index == c` has `text` containing `RB_CENTER_SEC2` (sanity: the window is centered on the discovered chunk)

#### Step 4: Window clamping

- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=N-1, adjacent_chunks=5)`
- **PASS:** no error; `chunks` length == `N` (window clamped to the full file).

#### Step 5: Error codes

- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=999, adjacent_chunks=1)`
- **PASS:** error result with code `CENTER_CHUNK_INDEX_OUT_OF_RANGE`.
- Call `fetchFile(file_id, memory_bank="tmp-vault", center_chunk_index=c, adjacent_chunks=10)`
- **PASS:** error result with code `ADJACENT_CHUNKS_OUT_OF_RANGE`.

### Cleanup

- Delete the fixture: `tmp/vault/rb-center-target.md`
- Verify with `ls tmp/vault/` that the file is gone.
