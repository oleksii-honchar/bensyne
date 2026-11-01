---
type: runbook
system: racochu
title: "Production Deployment"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [production, deployment]
see_also: [concepts/0011-namespace-routing.concept.md, decisions/0120-prisma-migrate-deploy-with-fail-loud-dedup-guard.decision.md, decisions/0121-manual-cli-watch-operation-with-instance-lock.decision.md, runbooks/0011-verify-racochu-ingest-gate-holding.runbook.md]
---

# Runbook: Production Deployment

## Goal

Deploy RAG Content Chunker as a production service watching configured sources.

## Prerequisites

- Node.js >= 26.0.0
- Remote Mnemosyne MCP server (better-mnemosyne) accessible
- Config file location writable: `~/.config/rag-content-chunker.yaml`

## Steps

1. **Create config:**
   ```bash
   cp .env.tpl ~/.config/rag-content-chunker.yaml
   ```
   Configure watch sources with namespaces:
   ```yaml
   watchSources:
     - id: agent-sessions
       path: ~/.agent-sessions
       namespace: agent-sessions
     - id: vault-knowledge
       path: ~/.vault
       namespace: vault
   mcp:
     url: https://your-mnemosyne-server.lan/mcp/mnemosyne
     apiKey: your-token
   ```

2. **Build:**
   ```bash
   npm install
   npm run build
   ```

3. **Run:**
   ```bash
   npm run start:prod
   ```
   Or via npx:
   ```bash
   npx rag-content-chunker
   ```

## Verification

- Check logs: `~/.local/share/rag-content-chunker/logs/current.log`
- Verify Mnemosyne connectivity: watch a file change, check ingestion logs
- Monitor queue: logs show "File processed: ... chunks=N"

## Rollback

- Stop: SIGTERM (graceful drain) or SIGINT
- Restore config: backup before editing

---

## Update 2026-11-01 — racochu deployment/operation model changes (DEC-0120, DEC-0121)

- **Startup schema lifecycle changed:** `ensureSchema()` no longer runs
  `prisma db push --accept-data-loss`; it runs `prisma migrate deploy` against committed
  migrations with a fail-loud FileTracker row-count guard (`dedup state must not shrink …`
  aborts startup). **Operator step for pre-existing DBs (once, before first deploy):**
  `npx prisma migrate resolve --applied 0_init`. Details: decision DEC-0120, runbook 0004.
- **Operating stance: no daemon (by operator directive 2026-10-31).** Watch mode is started
  manually from the CLI (`npm start` / `dist/src/main.js`). A second watcher start is refused:
  `another racochu watch instance holds the lock (pid X) — exiting` (exit 1) —
  this message is **expected behavior**, not a failure to fix. `autoPopulate` stays ON. (DEC-0121)
- **CLI semantics:** `--process-only` is now gated (safe catch-up); `--force-reprocess` is the
  deliberate full-rebuild override. README modes table is the surface of record.
- **Post-deploy acceptance:** one manual watch start must show large `gated-skips`/
  `verified-skips` and near-zero real work in the batch summary; repeated starts keep it flat —
  runbook 0011.
