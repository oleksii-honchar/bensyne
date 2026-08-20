> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Search scenario

### Test Objective

Verify `searchFiles` — keyword recall, bank-scoping isolation (D39), `source_type` filter demotion, `limit`, `include_relations` (including the additive `related_files[]` `summary` + `description` keys), and the `file_enrichment`/`traversal` handle contract.

### Fixtures

```bash
mkdir -p tmp/vault tmp/obsidian

cat > tmp/vault/search-rb-vault-note.md <<'EOF'
# Search Vault Note

RB_SEARCH_VAULT unique token. Body text for vault bank search.
EOF

cat > tmp/obsidian/search-rb-obs-note.md <<'EOF'
# Search Obsidian Note

RB_SEARCH_OBSIDIAN unique token. Body text for obsidian bank search.

See [[RB_SEARCH_OBS_TARGET]] for the wikilink-backed search edge.
EOF
```

Wait ≥3s for debounce + chunking + ingestion.

Then create the wikilink target note so the obsidian note's `backlink` edge resolves to a real file (Step 7's `related_files[]` is non-empty only when the target exists + is ingested):

```bash
cat > tmp/obsidian/RB_SEARCH_OBS_TARGET.md <<'EOF'
# Search Obsidian Target

RB_SEARCH_OBS_TARGET. Target note resolving the obsidian note's wikilink edge.
EOF
```

Wait ≥3s for debounce + chunking + ingestion (so the target has a real `file_id` and the edge resolves).

### Test Steps

#### Step 1: Precondition — verify banks exist

- Call `listMemoryBanks`
- **PASS:** banks include `tmp-vault` and `tmp-obsidian` (ids from `apps/racochu/dev.yaml`)
- **Note:** a bank may first appear in `listMemoryBanks` only after its initial ingest has completed — if a bank is missing, wait ~5s and re-list before failing (verified live 2026-08-19: both banks appeared after their first file was processed).

#### Step 2: Vault bank keyword search

- Call `searchFiles("RB_SEARCH_VAULT", memory_bank="tmp-vault", limit=5)`
- **PASS:** ≥1 result with `file != null` (file-backed group); `file.source_type == "vault"`; `file.id` non-empty; `matched_memories` ≥1 entry whose `content_preview` contains `RB_SEARCH_VAULT`.
- Record `file.id` as `vault_note_id`.

#### Step 3: Obsidian bank keyword search

- Call `searchFiles("RB_SEARCH_OBSIDIAN", memory_bank="tmp-obsidian", limit=5)`
- **PASS:** ≥1 file-backed group with `file.source_type == "obsidian"`; token `RB_SEARCH_OBSIDIAN` in `matched_memories[].content_preview`.

#### Step 4: Bank isolation (D39 — mandatory)

- Call `searchFiles("RB_SEARCH_VAULT", memory_bank="tmp-obsidian", limit=5)`
- **PASS:** **no** row surfaces the vault token — no file-backed group, and no non-file row with `content_preview` containing `RB_SEARCH_VAULT`. The vault memory lives only in the `tmp-vault` bank's store; a scoped request must never see it.
- **FAIL signature:** the token appears in any row ⇒ cross-bank leakage — server scoping broken.

#### Step 5: Filter demotion contract

- Call `searchFiles("RB_SEARCH_OBSIDIAN", memory_bank="tmp-obsidian", source_type="vault", limit=5)`
- **PASS:** **no** file-backed group (`file != null`) — the obsidian note fails the vault filter; yet the memory is **not dropped**: a non-file row (`file: null`) with the token in `content_preview` may still appear (filter demotes, never drops).

#### Step 6: Limit

- Call `searchFiles("RB_SEARCH_VAULT", memory_bank="tmp-vault", limit=1)`
- **PASS:** total entries in `matched_memories[]` across all results ≤ 1.

#### Step 7: Include relations

- Call `searchFiles("RB_SEARCH_OBSIDIAN", memory_bank="tmp-obsidian", limit=5, include_relations=true)`
- **PASS:** file-backed group has `related_files` (array, may be empty) and numeric `related_files_count`; group also carries `summary` (string) and `source_type_enrichment` (object).
- **PASS — `related_files[]` carries `summary` + `description`:** the obsidian note's wikilink resolves, so `related_files` contains an entry whose `id` matches the target note's `file.id` (the `RB_SEARCH_OBS_TARGET.md` group). **Every** `related_files[]` entry carries **both** a `summary` field (the target file's whole-file summary) and a `description` field (the traversed relation's description) — the keys must be present on each entry (values may be null/empty; the keys must not be absent).
- **FAIL signature:** a `related_files[]` entry is missing `summary` or `description` ⇒ additive read-path contract regression (the D44 edges-population keys are not surfaced on search).

### Cleanup

- Delete all fixture files:
  - `tmp/vault/search-rb-vault-note.md`
  - `tmp/obsidian/search-rb-obs-note.md`
  - `tmp/obsidian/RB_SEARCH_OBS_TARGET.md`
- Wait ≥3s for debounce + forget.
- Verify with `ls tmp/vault/ tmp/obsidian/` that the files are gone.
- Call `searchFiles("RB_SEARCH_OBSIDIAN", memory_bank="tmp-obsidian", limit=5)` → 0 results (memories cleaned).
