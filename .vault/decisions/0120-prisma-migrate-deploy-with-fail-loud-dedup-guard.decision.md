---
type: decision
id: DEC-0120
system: racochu
title: "Startup Schema via prisma migrate deploy + Fail-Loud Dedup Row-Count Guard"
status: accepted
createdAt: "2026-11-01T13:54:35Z"
updatedAt: "2026-11-01T13:54:35Z"
tags: [prisma, migrations, schema, startup, data-safety, deduplication]
supersedes: []
superseded_by: []
see_also:
  - decisions/0028-file-memory-tracking-prisma-sqlite.decision.md
  - decisions/0119-file-hash-ingest-gate-and-terminal-skip-quarantine.decision.md
  - runbooks/0004-prisma-setup.runbook.md
  - runbooks/0002-production-deployment.runbook.md
---

# DEC-0120: Startup Schema via prisma migrate deploy + Fail-Loud Dedup Row-Count Guard

## Context

`PrismaService.ensureSchema()` ran `npx prisma db push --accept-data-loss` at **every startup**.
The local `FileTracker` DB is the dedup state itself (~8k rows accumulated since Aug 31 that the
DEC-0119 hash gate depends on); one schema drift could silently wipe it, and every file would
instantly look "untracked" to resume — a latent full-corpus mass-re-ingest amplifier
(findings item E).

## Decision

1. Replace `db push --accept-data-loss` with **`prisma migrate deploy`** against committed
   migrations. `prisma/migrations/0_init` is baselined from the live schema
   (`prisma migrate diff --from-empty --to-schema-datamodel --script`); operator marks existing
   DBs once with `prisma migrate resolve --applied 0_init` (metadata-only) before first deploy.
   Subsequent schema changes ship as individual **additive** migrations — first:
   `20261031_add_skip_reason` (`ALTER TABLE … ADD COLUMN`, DEC-0119's `skipReason`).
2. Add a **fail-loud startup guard** in `ensureSchema()`: `FileTracker` row count before and
   after the schema step; any decrease aborts the process with
   `dedup state must not shrink (was N, now M)`. Fresh/empty DB (0→0 or missing file) is unaffected.
   The throw is an intentional fail-fast at the infrastructure seam, consistent with the existing
   `ensureSchema` rethrow and the repo's Result boundary.
3. Keep `PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION` env plumbing while migrate still needs it
   (non-interactive deploy should not prompt). CI drift check (`prisma migrate diff --exit-code`)
   deliberately deferred.

## Alternatives Considered

| Alternative | Pros | Cons | Why rejected |
|-------------|------|------|--------------|
| `db push` without `--accept-data-loss` | No destructive surprise by default | Refuses non-interactively with a cryptic exit code; no migration history | Kept only as fallback if baselining slips |
| "The DB is a cache, let it wipe" | Simplest possible policy | Post-gate a wipe is *safe* but costs ~8k files of full-price re-chunk/enrich LLM compute | Pure avoidable waste; unnecessary |

## Consequences

- **Positive:** reviewable, reversible migration audit trail (DEC-0028 chose Prisma+SQLite;
  migrations are the tool's own next step); the remaining class of "destructive surprise"
  becomes a fail-loud stop instead of a silent mass-re-ingest mode.
- **Negative:** a genuine intentional DB swap now needs the documented operator override
  (replace DB + start fresh) instead of silent acceptance.
- **Neutral:** rollout ordering constraint — the guard never fires against the baselining itself
  (`migrate resolve --applied` is metadata-only); guard logic covered by unit tests
  (`prisma.service.test.ts`, "migrate deploy + dedup-state guard").
