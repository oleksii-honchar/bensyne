# Agent e2e test

Test manually all the bensyne and racochu functionality — use mcp tools, do not try to call server via curl.

**MCP enforcement:** Use only Bensyne MCP tools available via `meta_search` / `meta_use` (e.g., `recallMemory`, `listMemoryBanks`). **Never curl the MCP server.**

Fixtures go to `tmp/vault/` (vault sourceType).

**Bank scoping is MANDATORY (D39):** Every bank-scoped MCP call must specify `memory_bank="tmp-vault"` — the `tmp-vault` source id from `dev.yaml`. This applies to `searchFiles`, `recallMemory`, `expandFileRelations`, `fetchFile`, `getMemoryStats`, `forgetMemory`, `updateMemory`, `sleep`. `listMemoryBanks` is the only exception: it takes no `memory_bank` (it lists all banks) and is used here only to confirm `tmp-vault` exists. Never omit, never mix.

> **Vault edge contract (ADR-V3 / ADR-V4):**
> - **Index files are skipped entirely** — `_index.md`, `_Vault-Home.md`, or frontmatter `type: index` produce **zero chunks and zero edges**.
> - **`see_also` frontmatter → `recommendation` edges** (strength 1). Values are vault-relative paths; a missing `.md` extension is retried defensively.
> - **Body wikilinks → `backlink` edges** (strength 1). Resolution ladder (first hit wins): path form `[[folder/node.type]]` → `vaultRoot/node.type.md`; bare form → vault-root `target.md` → same-folder `target.md` → vault-wide stem match where `basename - .md` **equals** `target` (plain node) or **starts with `target + .`** (typed node, the dominant form: `[[0002-x]]` → `0002-x.concept.md`).
> - **Existence gate (D49):** every emitted edge target is verified on disk — nonexistent targets emit **nothing** (no PENDING stubs, unlike obsidian). Ambiguous bare stems (0 or >1 candidates) are dropped. No self-edges.
> - **Node metadata:** vault frontmatter maps to `note.type`, `note.status`, `note.created`, `note.modified`, `note.tags`, `note.properties.{id,system,title,see_also,supersedes,superseded_by,deprecated}`; body wikilink targets (normalized) → `note.wikilinks`.
> - **Body cleaning:** `[[t|a]]` → `a`, `[[t]]` → `t` in the embedded text; edges are extracted from the original body.

## Vault Scenario

### Test Objective

Verify end-to-end the **vault** chunking strategy's distinctive behavior:
1. Are **index/MOC files skipped** (zero chunks, zero edges)?
2. Are **`see_also` frontmatter edges** emitted as resolved `recommendation` relations?
3. Are **body wikilinks** resolved across all real-world forms (path, bare-slug→typed, bare-exact-root) into `backlink` relations?
4. Is the **existence gate** enforced (missing/ambiguous/self targets → no edges, no stubs)?
5. Are **node metadata keys** (`note.*`) mapped from vault frontmatter?
6. Are **wikilinks cleaned** from embedded body text?
7. Are **deprecated nodes** still chunked (metadata-only handling)?

### Prerequisites

- racochu running with `sourceType: vault` on the `tmp-vault` watch source
- bensyne-dev MCP tools available
- `tmp/vault/` directory writable

### Test Steps

#### Step 1: Check Current State

- Call `listMemoryBanks` (lists all banks; no bank param) → confirm `tmp-vault` appears.
- Call `recallMemory("RB_VAULT_HUB_TOKEN", memory_bank="tmp-vault", limit=5)` → expect 0 results (clean start).
- **PASS:** `tmp-vault` bank present; `RB_VAULT_HUB_TOKEN` recall returns 0 rows.

#### Step 2: Create the vault fixture tree

Create all 9 files (3 index, 6 content) — index files carry tokens + links that must produce **nothing**:

```bash
mkdir -p tmp/vault/concepts tmp/vault/decisions

# ── INDEX FILES (must be skipped: 0 chunks, 0 edges) ──────────────────────
cat > tmp/vault/_Vault-Home.md <<'EOF'
---
type: index
title: Vault Home
createdAt: 2026-08-19T10:00:00Z
updatedAt: 2026-08-19T10:00:00Z
tags:
  - vault
see_also:
  - concepts/0001-rb-vault-alpha.concept.md
---
# Vault Home

RB_VAULT_HOME_TOKEN. Links: [[0001-rb-vault-alpha]] [[0003-rb-vault-gamma]]
EOF

cat > tmp/vault/RB_VAULT_INDEXTYPE.md <<'EOF'
---
type: index
title: RB Vault Index Type Test
tags:
  - vault
---
RB_VAULT_ITYPE_TOKEN. Index detected via frontmatter type, not filename.
EOF

cat > tmp/vault/concepts/_index.md <<'EOF'
---
type: index
title: Concepts Index
tags:
  - vault
see_also:
  - concepts/0001-rb-vault-alpha.concept.md
  - concepts/0002-rb-vault-beta.concept.md
---
# Concepts

RB_VAULT_CINDEX_TOKEN. - [[0001-rb-vault-alpha]] - [[0002-rb-vault-beta]]
EOF

# ── CONTENT NODES ─────────────────────────────────────────────────────────
# HUB: see_also (4 entries: real, no-.md, self, ghost) + wikilinks (5 forms)
cat > tmp/vault/decisions/0003-rb-vault-gamma.decision.md <<'EOF'
---
type: decision
title: RB Vault Gamma Decision
id: DEC-RB-0003
status: accepted
createdAt: 2026-08-19T10:00:00Z
updatedAt: 2026-08-19T10:00:00Z
tags:
  - decision
  - rb-vault
system: racochu
see_also:
  - concepts/0001-rb-vault-alpha.concept.md
  - concepts/0002-rb-vault-beta.concept
  - decisions/0003-rb-vault-gamma.decision.md
  - concepts/0009-rb-vault-ghost.concept.md
---
# RB Vault Gamma Decision

RB_VAULT_HUB_TOKEN. Decision hub body.

Related: [[concepts/0001-rb-vault-alpha.concept]] (path form).
Bare slug: [[0002-rb-vault-beta]] (typed-node form).
Plain root: [[RB_VAULT_PLAIN]] (exact-stem root form).
Self: [[0003-rb-vault-gamma]] (must be dropped).
Ghost: [[0005-rb-vault-missing]] (nonexistent, must be dropped).
EOF

# Target 1: metadata node + edges back to hub
cat > tmp/vault/concepts/0001-rb-vault-alpha.concept.md <<'EOF'
---
type: concept
title: RB Vault Alpha Concept
id: C-RB-0001
status: active
createdAt: 2026-08-19T10:00:00Z
updatedAt: 2026-08-19T10:00:00Z
tags:
  - concept
  - rb-vault
system: racochu
see_also:
  - decisions/0003-rb-vault-gamma.decision.md
---
# RB Vault Alpha Concept

RB_VAULT_ALPHA_TOKEN. Concept alpha body. Links back: [[0003-rb-vault-gamma]].
EOF

# Target 2: deprecated node (metadata-only; must still be chunked)
cat > tmp/vault/concepts/0002-rb-vault-beta.concept.md <<'EOF'
---
type: concept
title: RB Vault Beta Concept
id: C-RB-0002
status: deprecated
createdAt: 2026-08-19T10:00:00Z
updatedAt: 2026-08-19T10:00:00Z
tags:
  - concept
  - rb-vault
deprecated:
  reason: superseded by alpha
  replaced_by: concepts/0001-rb-vault-alpha.concept.md
---
# RB Vault Beta Concept

RB_VAULT_BETA_TOKEN. Concept beta body.
EOF

# Plain root-level node (exact-stem bare target; no frontmatter)
cat > tmp/vault/RB_VAULT_PLAIN.md <<'EOF'
# RB Vault Plain Root

RB_VAULT_PLAIN_TOKEN. Plain root-level node, no frontmatter.
EOF

# Ambiguity pair (same bare stem, two folders → [[RB_VAULT_AMB]] must drop)
cat > tmp/vault/concepts/RB_VAULT_AMB.concept.md <<'EOF'
# RB Vault Amb Concept

RB_VAULT_AMB_CON_TOKEN. Ambiguity member (concepts).
EOF

cat > tmp/vault/decisions/RB_VAULT_AMB.decision.md <<'EOF'
# RB Vault Amb Decision

RB_VAULT_AMB_DEC_TOKEN. Ambiguity member (decisions).
EOF
```

Wait **≥3s** for debounce + chunking.

> **Ingestion-order guard (existence gate):** edges are existence-gated at chunk time.
> Watcher order is nondeterministic — a hub chunked before its targets exist would
> drop those edges. Re-touch the two edge-source files after everything exists:

```bash
echo "" >> tmp/vault/decisions/0003-rb-vault-gamma.decision.md
echo "" >> tmp/vault/concepts/0001-rb-vault-alpha.concept.md
```

Wait **≥3s** for debounce + re-chunking (now all targets exist — edges must resolve).

#### Step 3: Discover file_ids via search (bank-scoped)

- Call `searchFiles("RB_VAULT_HUB_TOKEN", memory_bank="tmp-vault", limit=5)` → `hub_id` (file-backed group's `file.id`, `file != null`).
- Call `searchFiles("RB_VAULT_ALPHA_TOKEN", memory_bank="tmp-vault", limit=5)` → `alpha_id`.
- Call `searchFiles("RB_VAULT_BETA_TOKEN", memory_bank="tmp-vault", limit=5)` → `beta_id`.
- Call `searchFiles("RB_VAULT_PLAIN_TOKEN", memory_bank="tmp-vault", limit=5)` → `plain_id`.
- Call `searchFiles("RB_VAULT_AMB_DEC_TOKEN", memory_bank="tmp-vault", limit=5)` → `amb_dec_id`.
- **PASS:** all five `file.id`s are non-empty.

#### Step 4: V1 — Index files produce zero chunks and zero edges

- Call `recallMemory("RB_VAULT_HOME_TOKEN", memory_bank="tmp-vault", limit=5)` → **0 rows**.
- Call `recallMemory("RB_VAULT_CINDEX_TOKEN", memory_bank="tmp-vault", limit=5)` → **0 rows**.
- Call `recallMemory("RB_VAULT_ITYPE_TOKEN", memory_bank="tmp-vault", limit=5)` → **0 rows**.
- Call `searchFiles("RB_VAULT_HOME_TOKEN", memory_bank="tmp-vault", limit=5)` → **no file-backed group**.
- **PASS:** all three index files (filename `_Vault-Home.md`, filename `_index.md`, frontmatter `type: index` on a regular name) are fully skipped — their `see_also`/wikilinks emit no edges either.

#### Step 5: V2 — Node metadata mapping (hub)

- Call `recallMemory("RB_VAULT_HUB_TOKEN", memory_bank="tmp-vault", limit=10)`; find hub rows (rows whose `file_enrichment.file.id == hub_id`).
- **PASS — source_type:** `file_enrichment.file.source_type == "vault"`.
- **PASS — typed metadata:**
  - `note.type` = "decision"
  - `note.status` = "accepted"
  - `note.created` = "2026-08-19T10:00:00Z" (from `createdAt`)
  - `note.modified` = "2026-08-19T10:00:00Z" (from `updatedAt`)
  - `note.tags` = JSON array containing "decision" and "rb-vault"
- **PASS — vault-specific properties:**
  - `note.properties.id` = "DEC-RB-0003"
  - `note.properties.system` = "racochu" (from frontmatter `system: racochu`)
- **PASS — wikilink metadata:** `note.wikilinks` = JSON array containing exactly these normalized targets: "concepts/0001-rb-vault-alpha.concept", "0002-rb-vault-beta", "RB_VAULT_PLAIN", "0003-rb-vault-gamma", "0005-rb-vault-missing".

- **PASS — chunk tags:** hub chunk rows carry tags including `frontmatter`, `metadata`, `vault-node` (frontmatter chunk) plus `decision`, `rb-vault`.
- **PASS — chunk coverage:** hub recall returns **≥ 2 rows** (frontmatter chunk + ≥1 body chunk).

#### Step 6: V3 — see_also → recommendation edges (hub)

- Call `expandFileRelations(hub_id, memory_bank="tmp-vault", relation_types=["recommendation"])`.
- **PASS — source:** `source_file.id == hub_id`.
- **PASS — resolved:** `related_files` contains an entry with `id == alpha_id` (path form `concepts/0001-rb-vault-alpha.concept.md`) **and** an entry with `id == beta_id` (no-`.md` value `concepts/0002-rb-vault-beta.concept` retried → resolved).
- **PASS — self dropped:** NO entry with `id == hub_id` (the `see_also` self-reference).
- **PASS — ghost dropped:** NO entry whose path contains `0009-rb-vault-ghost` (nonexistent target).
- **FAIL signature:** alpha/beta missing ⇒ see_also edges not emitted/resolved.

#### Step 7: V4 — wikilinks → backlink edges across resolution forms (hub)

- Call `expandFileRelations(hub_id, memory_bank="tmp-vault", relation_types=["backlink"])`.
- **PASS — source:** `source_file.id == hub_id`.
- **PASS — path form:** `related_files` contains `id == alpha_id` (from `[[concepts/0001-rb-vault-alpha.concept]]`).
- **PASS — bare slug → typed node:** `related_files` contains `id == beta_id` (from `[[0002-rb-vault-beta]]` → `concepts/0002-rb-vault-beta.concept.md`).
- **PASS — bare exact-stem root:** `related_files` contains `id == plain_id` (from `[[RB_VAULT_PLAIN]]` → `RB_VAULT_PLAIN.md` at vault root).
- **PASS — self dropped:** NO entry with `id == hub_id` (from `[[0003-rb-vault-gamma]]`).
- **PASS — ghost dropped:** NO entry whose path contains `0005-rb-vault-missing`.
- **PASS — ambiguous dropped:** NO entry whose path contains `RB_VAULT_AMB` (from `[[RB_VAULT_AMB]]` — wait, the hub body has no `[[RB_VAULT_AMB]]` link; see Step 11 for the ambiguity assertion).
- **FAIL signature:** alpha/beta/plain missing ⇒ resolution ladder broken.

#### Step 8: V5 — Edges from the target node (alpha → hub, both types)

- Call `expandFileRelations(alpha_id, memory_bank="tmp-vault", relation_types=["recommendation", "backlink"])`.
- **PASS — see_also back-edge:** `related_files` contains `id == hub_id` (alpha's `see_also` → `recommendation`).
- **PASS — wikilink back-edge:** `related_files` contains `id == hub_id` (alpha's `[[0003-rb-vault-gamma]]` → `backlink`).
- **FAIL signature:** hub absent ⇒ edges are not one-directional in the way the spec intends (alpha must resolve its own links).

#### Step 9: V6 — Existence gate: no stubs for missing targets

- Call `searchFiles("RB_VAULT_GHOST", memory_bank="tmp-vault", limit=5)` → **0 file-backed groups** (ghost see_also target never created a stub file/memory).
- Call `searchFiles("RB_VAULT_MISSING", memory_bank="tmp-vault", limit=5)` → **0 file-backed groups** (ghost wikilink target).
- Call `recallMemory("RB_VAULT_GHOST", memory_bank="tmp-vault", limit=5)` → **0 rows**.
- **PASS:** vault strategy never emits dangling targets (contrast with obsidian's best-effort PENDING stubs).

#### Step 10: V7 — Body cleaning (no [[...]] in embedded text)

- Call `fetchFile(hub_id, memory_bank="tmp-vault")` → reconstructed content.
- **PASS — cleaned:** content contains `Related: concepts/0001-rb-vault-alpha.concept (path form).` with **no** `[[` or `]]` characters anywhere in the reconstructed body text.
- **FAIL signature:** any `[[` present ⇒ cleaning not applied.

#### Step 11: V8 — Ambiguous bare stem dropped (RB_VAULT_AMB)

The two files `concepts/RB_VAULT_AMB.concept.md` + `decisions/RB_VAULT_AMB.decision.md` both exist (both discovered-able — `amb_dec_id` non-empty in Step 3). Neither is referenced by a wikilink in this fixture (adding `[[RB_VAULT_AMB]]` to the hub would resolve via the walk to 2 candidates → drop). To verify the ambiguous-drop path end-to-end:

- Append an ambiguous link to the hub:
  ```bash
  echo "Ambiguous: [[RB_VAULT_AMB]] (two candidates — must be dropped)." >> tmp/vault/decisions/0003-rb-vault-gamma.decision.md
  ```
- Wait **≥3s** for debounce + re-chunking.
- Call `expandFileRelations(hub_id, memory_bank="tmp-vault", relation_types=["backlink"])`.
- **PASS — ambiguous dropped:** `related_files` contains **NO** entry whose path contains `RB_VAULT_AMB`.
- **PASS — other edges intact:** `related_files` still contains `alpha_id`, `beta_id`, `plain_id`.
- **PASS — files still chunked:** `searchFiles("RB_VAULT_AMB_CON_TOKEN", memory_bank="tmp-vault", limit=5)` → file-backed group exists (ambiguity drops the *edge*, not the *files*).

#### Step 12: V9 — Deprecated node still chunked (metadata only)

- Call `recallMemory("RB_VAULT_BETA_TOKEN", memory_bank="tmp-vault", limit=5)`; find beta rows (`file_enrichment.file.id == beta_id`).
- **PASS — still chunked:** beta recall returns ≥1 row (deprecated nodes are NOT muted).
- **PASS — metadata:** `note.status` = "deprecated"; `note.properties.deprecated` = JSON string/object containing `"superseded by alpha"`.
- **PASS — edge to deprecated still emitted:** re-check Step 6 result — `beta_id` present in hub's `recommendation` `related_files` (deprecation does not suppress edges).

#### Step 13: V10 — No-frontmatter node chunking (plain root)

- Call `recallMemory("RB_VAULT_PLAIN_TOKEN", memory_bank="tmp-vault", limit=5)`; find plain rows (`file_enrichment.file.id == plain_id`).
- **PASS — chunked:** ≥1 row returned; `file_enrichment.file.source_type == "vault"`.
- **PASS — no metadata:** rows do **NOT** expose `note.type` / `note.properties.*` (no frontmatter → no properties), consistent with obsidian no-frontmatter behavior.
- **PASS — still edge-reachable:** `plain_id` appeared in Step 7 (a node without frontmatter is still a valid wikilink edge target).

#### Step 14: Check Logs

- Check logs at `~/.local/share/racochu/logs` to verify the vault chunker was selected (look for `Chunker selected: sourceType="vault"` in the logs).

#### Step 15: Cleanup

- Delete all fixtures:
  ```bash
  rm -rf tmp/vault/_Vault-Home.md tmp/vault/RB_VAULT_INDEXTYPE.md tmp/vault/RB_VAULT_PLAIN.md tmp/vault/concepts tmp/vault/decisions
  ```
- Wait **≥3s** for debounce + forget.
- Call `recallMemory` for `RB_VAULT_HUB_TOKEN`, `RB_VAULT_ALPHA_TOKEN`, `RB_VAULT_BETA_TOKEN`, `RB_VAULT_PLAIN_TOKEN`, `RB_VAULT_HOME_TOKEN` (all `memory_bank="tmp-vault"`) → confirm 0 results.
- **PASS:** memories cleaned up.

### Expected Outcomes Summary

| Scenario | Check | Expected |
|----------|-------|----------|
| **V1** | Index files skipped | `_Vault-Home.md`, `_index.md`, `type: index` file → 0 chunks, 0 edges |
| **V2** | source_type | `vault` on content nodes |
| **V2** | Typed metadata | `note.type`, `note.status`, `note.created`/`note.modified` (from createdAt/updatedAt), `note.tags` |
| **V2** | Vault properties | `note.properties.id`, `note.properties.system`, `note.properties.see_also` |
| **V2** | Wikilinks metadata | `note.wikilinks` = 5 normalized targets |
| **V2** | Chunk tags/coverage | frontmatter chunk tags (`frontmatter`,`metadata`,`vault-node`); ≥2 chunks for hub |
| **V3** | see_also edges | hub → alpha (path) + hub → beta (no-.md retry); self + ghost dropped |
| **V4** | Wikilink edges | path form, bare-slug→typed, bare-exact-root all resolve; self + ghost dropped |
| **V5** | Target-node edges | alpha → hub via both `recommendation` and `backlink` |
| **V6** | Existence gate | No stubs/memories for ghost targets |
| **V7** | Body cleaning | No `[[`/`]]` in reconstructed hub content |
| **V8** | Ambiguity | `[[RB_VAULT_AMB]]` (2 candidates) → no edge; files still chunked |
| **V9** | Deprecated node | Still chunked; `note.status=deprecated` + `note.properties.deprecated`; edges unaffected |
| **V10** | No-frontmatter node | Chunked, no `note.properties.*`, still edge-reachable |
| — | Bank scoping | Every bank-scoped call uses `memory_bank="tmp-vault"` |
| — | Cleanup | Memories forgotten after file deletion |
