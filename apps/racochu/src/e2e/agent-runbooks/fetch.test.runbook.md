> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Fetch scenario

### Test Objective

Verify full-file reconstruction via `fetchFile` (no `center_chunk_index`).

### Fixtures

```bash
cat > tmp/vault/rb-fetch-target.md <<'EOF'
# Fetch Target

## Overview

RB_FETCH_OVERVIEW. The overview section of the fetch target.

## Details

RB_FETCH_DETAILS. The details section of the fetch target.
EOF
```

Wait ≥3s for debounce + chunking + ingestion.

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
- **PASS:** every chunk in `chunks` carries a `metadata` object.

#### Step 4: Error — unknown file_id

- Call `fetchFile("file_does_not_exist_rbx", memory_bank="tmp-vault")`
- **PASS:** error result with code `FILE_NOT_FOUND`.

### Cleanup

- Delete the fixture: `tmp/vault/rb-fetch-target.md`
- Verify with `ls tmp/vault/` that the file is gone.
