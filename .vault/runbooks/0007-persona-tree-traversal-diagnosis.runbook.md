---
type: runbook
system: shared
title: "Diagnose Persona Decision-Tree Traversal Failures"
createdAt: "2026-08-28T10:58:47Z"
updatedAt: "2026-08-28T10:58:47Z"
tags: [operations, persona, troubleshooting, racochu, bensyne-mcp]
supersedes: []
superseded_by: []
see_also:
  - decisions/0089-persona-tree-walk-tilde-expansion.decision.md
  - decisions/0090-persona-entry-node-tool.decision.md
  - decisions/0091-file-tools-file-id-contract.decision.md
  - decisions/0092-recall-bank-scoping-per-bank-clients.decision.md
  - decisions/0093-load-first-rule-system-prompt.decision.md
---

# Runbook: Diagnose Persona Decision-Tree Traversal Failures

Persona agents navigate their decision trees via Bensyne MCP tools, one node at a time.
When traversal breaks, four symptom classes recur. This runbook maps symptoms to
root-cause checks, based on the 2026-08-28 investigation
(session 260828-0855-persona-tree-usage-investigation).

**Environment map:**
- Persona node files: `~/Documents/agent-rules-n-skills/agent-personas/<agent>/`
- Racochu config: `~/.config/racochu.yaml` (persona watch sources — check for `~`)
- Per-bank DBs: `~/www/olho/bensyne/apps/bensyne-mcp/data/banks/<bank>/{mnemosyne.db, file_metadata.db, hash_index.db}`
- Logs: racochu `~/.local/share/racochu/logs/racochu.*.log`; bensyne-mcp `~/.local/share/bensyne/logs/bensyne.log*`

## Symptom 1 — `expandFileRelations` returns `related_files: []`

**Likely cause:** `decision_next` edges never materialized (ingestion tree-walk failure).

1. Count relations:
   ```bash
   sqlite3 <bank>/file_metadata.db "SELECT COUNT(*) FROM file_relations;"
   ```
   0 rows → edges missing.
2. Grep racochu logs for tree-walk failures:
   ```bash
   rg "Persona tree walk failed|ENOENT" ~/.local/share/racochu/logs/ | tail
   ```
3. Check `racochu.yaml` persona paths for a leading `~` — the chunking strategy must
   expand it (DEC-0090). `path.resolve('~/…')` treats `~` literally → silent ENOENT →
   all edges dropped as "dangling" (and `logDanglingTargets` stays silent when
   `fileIndex` is empty).
4. **Fix + re-ingest:** the code fix alone does not backfill — `file_relations` are
   written only at materialization. Force-reprocess the affected persona banks.

## Symptom 2 — `FILE_NOT_FOUND` from `expandFileRelations` / `fetchFile`

**Likely cause:** a **memory id** was passed where a **file id** is required (DEC-0092).

1. Check the id shape: memory ids are 16-hex (e.g. `0f2f59982885ec29`); file ids are
   `file_<32hex>`.
2. Get the correct file id from: `getPersonaEntryNode` (returns `file_id`), a recall
   result's `file_enrichment.file.id`, or `searchFiles` result `file.id`.
3. Verify the memory exists in mnemosyne.db (it does — only the id type is wrong):
   ```bash
   sqlite3 <bank>/mnemosyne.db "SELECT content FROM memories WHERE id='<id>';"
   ```

## Symptom 3 — `recallMemory` cannot find the entry node / returns empty

**Likely causes (check in order):**

1. **Wrong bank** — correct isolation, not a bug (DEC-0093). Persona nodes live in
   `persona_<agent>`, never in `agent-sessions`. Always pass the persona bank.
2. **Lexical-only FTS** — `fts_working` indexes `content` only; `persona.entry`,
   `node_id`, tags are not indexed. The literal query `"entry node"` matches nothing.
   - **Use `getPersonaEntryNode(memory_bank)`** (DEC-0091) — deterministic.
   - Fallback: `recallMemory` with content-bearing terms from the entry node body.
3. **Transient empty recall / MCP churn** — retry once; cross-check with
   `getPersonaStatus(memory_bank)` (node_memories > 0 means the tree is there).

## Symptom 4 — Agent loads skills late / never traverses

**Likely cause:** load-first rule missing from the effective system prompt (DEC-0094).

1. Check the installed prompt:
   ```bash
   rg -l "Load \`agent-persona-base\` and \`bensyne\` skills first" ~/.config/opencode/agents/*.md
   ```
2. Re-sync wrappers: `agents.sh` from `~/Documents/agent-rules-n-skills/` — ⚠️ note
   the flagged stale `agents/opencode/` source (v2.0.x) can regress live v2.2 prompts;
   verify version parity before/after.

## Verification

- `file_relations > 0` for the persona bank in question.
- `getPersonaEntryNode(persona_<agent>)` returns a node with a valid `file_id`.
- `expandFileRelations(file_id, persona_<agent>, ["decision_next"])` returns edges with
  `when` descriptions; traversal of 2+ nodes succeeds with zero node-file fs reads.

## Rollback

All checks are read-only. Fixes are: racochu strategy fix (DEC-0090 — revert + re-ingest),
skills/wrapper text (revert via git in `agent-rules-n-skills`), re-ingestion (idempotent,
file-backed).
