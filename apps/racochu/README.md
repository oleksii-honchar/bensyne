# racochu

File watcher that detects changes, semantically chunks content using Mastra RAG, and ingests chunks into Mnemosyne MCP for retrieval-augmented generation.

DDD-based NestJS CLI server. No Effect library — uses Result pattern for error handling.

Racochu = RAg COntent CHUnker 

## Quick Start

### Development

First-time setup on a fresh checkout:

```bash
npm install
npm run build
```

`npm run build` triggers the `prebuild` hook (`prisma generate`), which regenerates
the Prisma client into `src/generated/prisma/` — that directory is git-ignored and
never committed, so a fresh checkout only needs the two commands above; there is no
manual `prisma generate` step. Every later `npm run build` (including `nx run
racochu:build` and CI) regenerates the client from the current schema automatically,
which keeps it from going stale against schema changes.

1. Start Mnemosyne MCP (Docker):

   ```bash
   npm run bensyne:start
   ```

2. Start the chunker with dev config:

   ```bash
   npm run start:dev
   ```

   Watches `./watch-folder-dev` by default. Startup applies any pending Prisma
   migrations automatically (`prisma migrate deploy`) against the SQLite database in
   the app's `data/` directory — on a development database you never run schema
   commands by hand. Fresh databases are built from the committed migrations on first
   start.

3. Drop files into `watch-folder-dev/` — they are auto-chunked and ingested.

### Production

1. Create `~/.config/racochu.yaml` (see [Configuration](#configuration))
2. **Only for a database that predates migration tracking** (it was previously
   created without a migration history): before the very first start of the new
   build, run the idempotent baseline reconciler once — it handles the first-deploy
   `P3005 The database schema is not empty` error (and the known duplicate-column
   follow-up) by marking already-present migrations as applied, metadata-only —
   never destructive, never `db push`; on an already-current database it is a
   no-op:

   ```bash
   npm run db:baseline
   ```

   Fresh databases need nothing here — startup `migrate deploy` creates the schema
   from the committed migrations on its own. The script also works as a safe
   "is my schema current?" check (exit 0 = current; exit 1 = human review needed,
   nothing was changed).
3. Run:
   ```bash
   npm install
   npm run build
   npm run start:prod
   ```
   Or via npx:
   ```bash
   npx racochu
   ```

## Architecture

```
FileWatcherService (chokidar)
    │
    ▼ file:add/change/unlink
AppEventEmitter
    │
    ▼
ProcessFileUseCase
    │
    ├─► read file → detect file role (markdown, code, config, etc.)
    │
    ├─► ChunkContentUseCase (Mastra RAG MDocument)
    │       └─► semantic chunking (content-aware, recursive, per-key)
    │
    └─► IngestChunkUseCase
            └─► MnemosyneClient → MCP memory_remember tool
```

**Processing model:** Files are processed sequentially via a bounded async queue to avoid overwhelming Mnemosyne. Duplicate processing is prevented by the persistent **content-hash gate**: the hash recorded on each file's tracker row is matched against the current bytes before any work is scheduled — an unchanged file costs one indexed tracker read plus its SHA-256, no chunking and no bank calls (see [Hash gate & terminal skips](#hash-gate--terminal-skips)).

**Key components:**

- **FileWatcherService** — chokidar-based file system monitoring with configurable debounce
- **FileRoleDetector** — classifies files (markdown, TypeScript, JSON, YAML, etc.) for optimal chunking strategy
- **ContentChunkerService** — Mastra RAG MDocument wrapper for semantic chunking
- **MnemosyneClient** — raw HTTP client for Mnemosyne MCP (SSE session management, remember/recall/healthCheck)
- **SequentialProcessingQueue** — bounded concurrency, graceful shutdown with drain

## Configuration

**File:** `~/.config/racochu.yaml` (global default — dist runs via `nx run racochu:start`) or `dev.yaml` (dev runs via `nx run racochu:start:dev`, which sets `APP_CONFIG_PATH=dev.yaml` only for that target)

**Env override:** `APP_CONFIG_PATH=/path/to/config.yaml`

### Full Example

```yaml
watchSources:
  - id: my-docs
    path: /Users/me/docs
    exclude:
      - '.git/**'
      - '**/node_modules/**'
      - '**/.DS_Store'
    debounceMs: 3000
    ttlDays: 365      # optional: forget files older than this many days
    deleteDueFiles: false  # optional, requires ttlDays; true also deletes due files from disk

chunking:
  strategy: content-aware
  maxSizes:
    agentSessions: 400
    obsidianNotes: 500
    codeFiles: 400
    configuration: per-key
    plainText: 450
  overlap: 50
  hardCap: 600

enrichment:
  enabled: false

mcp:
  url: http://localhost:8765
  apiKey: your-token
  timeoutMs: 30000
  maxRetries: 3
  retryDelayMs: 1000

telemetry:
  enabled: false
```

### Configuration Reference

| Section            | Key          | Type     | Default                             | Description                                                     |
| ------------------ | ------------ | -------- | ----------------------------------- | --------------------------------------------------------------- |
| **watchSources[]** | id           | string   | —                                   | Unique identifier for this watch source                         |
|                    | path         | string   | —                                   | Directory to watch (supports `~/` expansion)                    |
|                    | exclude      | string[] | `['.git/**', '**/node_modules/**']` | Chokidar ignore patterns                                        |
|                    | debounceMs   | number   | 3000                                | ms to wait after last file modification before processing       |
|                    | ttlDays      | number   | — (no TTL)                          | Optional per-source retention in days; see [Source TTL](#source-ttl-ttldays) |
|                    | deleteDueFiles | boolean | — (off)                           | Optional; `true` also deletes due files from disk after they are forgotten (requires `ttlDays`); see [Source TTL](#source-ttl-ttldays) |
|                    | autoPopulate | boolean  | true                                | Auto-populate existing files on startup; set `false` to only watch for new/changed files |
| **chunking**       | strategy     | string   | `content-aware`                     | Chunking strategy (content-aware, recursive, config)            |
|                    | maxSizes     | object   | —                                   | Max token sizes per file role                                   |
|                    | overlap      | number   | 50                                  | Token overlap between chunks                                    |
|                    | hardCap      | number   | 600                                 | Absolute max tokens per chunk                                   |
| **mcp**            | url          | string   | —                                   | Mnemosyne MCP SSE endpoint (no trailing `/messages/` or `/mcp`) |
|                    | apiKey       | string   | —                                   | Bearer token for MCP authentication                             |
|                    | timeoutMs    | number   | 30000                               | HTTP request timeout                                            |
|                    | maxRetries   | number   | 3                                   | Retries per chunk on MCP error                                  |
|                    | retryDelayMs | number   | 1000                                | Base delay between retries (linear backoff)                     |
| **enrichment**     | enabled      | boolean  | false                               | Enable LLM-based chunk enrichment (future)                      |
| **telemetry**      | enabled      | boolean  | false                               | Enable OpenTelemetry metrics/traces                             |

### Source TTL (`ttlDays`)

Each `watchSources[]` entry may set an optional `ttlDays` — the retention period,
in days, after which tracked files for that source are **forgotten** (their
memories deleted via bensyne MCP `forgetFile` and their racochu trackers
cleaned up). Absent/omitted means **no TTL** — that source is never swept.

```yaml
watchSources:
  - id: agent-sessions
    path: ~/.agent-sessions
    ttlDays: 365         # optional; absent = no TTL
    deleteDueFiles: true # optional; requires ttlDays — see "Deleting due files" below
    sourceType: agent-sessions
```

The TTL sweep runs:

- **At startup** in all modes (non-fatal — a sweep failure is logged and boot continues), and
- **Once a day** while running in watch mode (`start`/`start:dev`), and
- **On demand** via `racochu --ttl-sweep` (optionally scoped with `-s/--source`; combine with `--dry-run` to preview).

`--dry-run` reports what *would* be forgotten — and, for a `deleteDueFiles`
source, what *would* be deleted (`wouldForget` / `wouldDelete` counts) —
without forgetting or deleting anything.

> **Mass-forget guard:** the sweep refuses to forget more than **20 files per
> source** in one run (same guard as exclude reconciliation). If a source has
> more expired files than that — e.g. the first backfill sweep after a year of
> accumulation — run it once with `RACOCHU_RECONCILE_FORCE_FORGET=1` to
> acknowledge the mass-forget and let the sweep proceed. A refused run
> additionally deletes **no** files: the delete step is bounded by the same
> guard by construction.

#### Deleting due files (`deleteDueFiles`)

A source may additionally set `deleteDueFiles: true` (optional, never implied;
it **requires `ttlDays`** — a config error otherwise). For such a source the
retention window ends in the complete lifecycle — **forget → untrack → unlink**:
after a due file's memories are forgotten and its tracker rows are removed, the
source file itself is deleted (`unlink`ed) from disk. The sweep summary reports
this in its `deletedFiles` counter (`wouldDelete` in a dry run).

This is the one place racochu destroys user data, and every existing safety
mechanism applies to it without exception: per-source opt-in, the activity
clock, the mass-forget guard (a refused run deletes nothing), and `--dry-run`
preview. Unlinks happen only strictly inside the source's declared directories
(realpath-checked — a file reached by a symlink that leads outside every
declared root is skipped whole, counted as `skippedConfinement`, and left
untouched). Failed unlinks are counted (`unlinkFailed`), never fatal; the
leftover file is inert to batch paths until its normal doors apply. A
previously deleted file never comes back: deleted files simply do not
enumerate, and the explicit `--recover`/`--force-reprocess` doors report them
with the existing file-absent semantics.

**Before enabling it for the first time on a source:**

1. Preview first: `racochu --ttl-sweep --dry-run -s <source-id>` — with the
   flag set it lists both `wouldForget` and `wouldDelete`.
2. Consider `exclude` patterns (e.g. `**/archive/**`) **before** enabling —
   kept archives are exactly the history one does not mean to delete.
3. Run the first real sweep immediately after such a dry-run: after
   enablement, the **first real sweep deletes every already-past-due file**
   (bounded — and acknowledged — by the mass-forget guard as above).

> **Safety notes:** the sweep only touches sources with `ttlDays` set; expiry is
> measured by the activity clock (see [Forget & activity semantics](#forget--activity-semantics));
> source files are **not** deleted from disk unless that source explicitly sets
> `deleteDueFiles: true` — without the flag only their memories and trackers are
> removed. With the flag, disk deletion is bounded by the mass-forget guard and
> confined to the source's declared directories, as described in
> [Deleting due files](#deleting-due-files-deleteduefiles).

### Forget & activity semantics

When a source has `ttlDays` set, "past due" is always measured from a file's
**last activity** — one rule, implemented once in `src/utils/ttl-activity.ts`
and shared verbatim by the TTL sweep, `--resume`, and startup auto-population:

- Last activity is the file's mtime first; only when the file is gone from
  disk does its tracker row's `updatedAt ?? createdAt` stand as the last known
  activity. A file is past due when `now − last activity > ttlDays` —
  strictly older than the window; a file exactly at the boundary is still
  active. `FileTracker.createdAt` by itself is audit-only.
- `ttlDays` is strictly **opt-in per source**. A source that omits it (e.g.
  permanent material like an obsidian bank) has no age gate anywhere and is
  never swept.
- Explicit intent is **never age-gated**: `--force-reprocess` (all, one source, or
  one file), watch `add`/`change` events, `--recover`, and re-embed all act on
  a past-due file exactly as before — the only batch path that also bypasses the
  content-hash gate is `--force-reprocess`. A file coming back through one of those
  doors is ingested with a fresh tracker row and a fresh retention period.
- There are deliberately **no "do not re-ingest" markers**: a genuine update
  (a real mtime change) re-arms the file by design, and the next batch pass
  treats it as eligible again. Batch skipping is re-derived every pass and
  behaves identically for never-tracked, already-forgotten, and still-tracked
  files.

## CLI Modes

Racochu is a CLI with one-shot maintenance modes and a default watch mode.
Pass the flag to select the mode (help: `racochu --help`):

| Flag | Mode |
| ---- | ---- |
| *(no flag)* | **Watch** — default: watch sources and ingest new/changed files continuously. **Auto-populates** all watched sources on startup to pick up everything that changed since the last run — cheap for unchanged files, gated (see [Hash gate & terminal skips](#hash-gate--terminal-skips)). Watch runs are single-instance: see [Running the watcher](#running-the-watcher-manual-operations--single-instance). |
| `--process-only` | Process existing files once, then exit (no watching). **Gated**: this is a safe catch-up pass — unchanged bytes are skipped by the content-hash gate at the cost of an indexed tracker read + a SHA-256, with no bank or LLM work. |
| `-f, --force-reprocess` | **Full rebuild, run on purpose** — re-chunks and re-ingests every file regardless of hash (the gate's documented override). Also the escape hatch for stale `CONTENT_FILTERED` skip-rows: after changing a source's `contentFilter` configuration, run `--force-reprocess` for that source to re-evaluate what is now processable. |
| `--reprocess-edges` | Two-pass reprocessing: after re-chunking files, re-resolve all edge targets via `resolve_file_ref` to fix ghost edges (see [Ghost-Edge Cleanup](#ghost-edge-cleanup--reprocess-edges)) |
| `-r, --resume` | **Cheap catch-up pass with bank-verified repair**: tracked files are verified against the bank first and proven loss is re-ingested (repair runs bypass the gate); everything else is re-queued only through the gate. Ends with a `resume finished:` summary. Note: bare `--resume` (and bare `--force-reprocess`) then stay in watch mode — pair with `--process-only` for an exit-only run. |
| `--recover` | Recover missing chunks for DB-tracked files, then exit |
| `--ttl-sweep` | Run the TTL sweep once, then exit (optionally scoped with `-s/--source`) |

`-s/--source <id>` scopes the one-shot modes (`--force-reprocess`, `--resume`,
`--process-only`, `--recover`, `--ttl-sweep`) to a single source id.
`--dry-run` reports what *would* change without changing anything.

`--recover` repairs chunk-level gaps for files already tracked in the local
database: it computes the expected chunk set locally (without LLM enrichment),
compares it against the stored chunk set via bensyne's read-only `getFileChunks`
tool, and re-ingests only the missing chunks (with enrichment when enabled).
Untracked files are never touched, and the process exits after the pass.

`--resume` / `--resume` are repair-first catch-up passes: files with a tracker
row are **verified against the bank before being trusted**, and any entry proven
absent from the bank (including stub rows — incomplete tracker entries) is
re-ingested even when its bytes are unchanged (verified repair bypasses the
hash gate). Every other file in the pass goes through the gate, so a second
resume over an unchanged corpus does near-zero work. Every run ends with a
`resume finished:` summary line (see [Hash gate & terminal skips](#hash-gate--terminal-skips)).
Stub and chunk-gap repair stays automatic — no manual intervention needed.

## Running the watcher (manual operations · single instance)

Racochu is a CLI tool the operator **starts manually, on purpose** — by design
there is no daemon and no supervisor, no auto-restart on crash or reboot, and
no scheduled reconciliation job. An optional cron of `--resume` is possible but
is deliberately **not part of this design**. Starting the watcher again after a
downtime window is cheap and safe: the startup auto-population pass skips
every unchanged file at the gate.

**Catching up without watching:** run a one-shot pass — `--process-only` (gated,
safe as catch-up) or, for the deliberate full rebuild, `npm run start:reprocess`
(`--force-reprocess`). `npm run start:resume` runs the same catch-up pass as
`--resume` and likewise stays watching afterwards (see below; add
`--process-only` to the underlying command for an exit-only run).

**Single instance.** A second watcher started while one is already running exits
with **exit code 1** and names the holder's pid:

```
another racochu watch instance holds the lock (pid <PID>) — exiting
```

The lock is the file `data/racochu.watch.lock` under the application root (the
same resolved data directory as the SQLite database file); it contains the holder
pid. It is removed when the holding process shuts down on SIGINT/SIGTERM. A
watcher killed hard leaves its lock file behind — the **stale pid is detected
and the lock is reclaimed automatically** on the next start (dead or unreadable
pid → the lock file is replaced, once, and acquisition retried; a live pid from
any live process still refuses).

**Modes that participate:** anything that keeps the watcher on participates in
the lock — the default watch start, and bare `--resume` / bare
`--force-reprocess`, which do not switch watching off: each first performs its
batch pass, then **continues as a watcher** and participates in the lock (if a
watcher already holds it, the batch pass still completes — only the watch
continuation is refused, with exit code 1). Auto-population does not re-run
in that combined flow: the batch pass already covered it. `--process-only`
forces watching off. Flags that always run and exit —
`--recover`, `--ttl-sweep`, `--re-embed`, `--reprocess-edges`,
and `--force-reprocess --process-only` — neither take the lock nor honor it.

**Downtime is a designed recovery case, not an incident.** While no watcher
runs, filesystem changes accumulate quietly. On the next watch start the startup
auto-population reconciles what was missed — an operation that is cheap for
unchanged content since the hash gate exists, so running
the watcher in short manual sessions is a supported operating style.

## Hash gate & terminal skips

Racochu does not re-ingest unchanged content. Every batch path (watch events,
`--process-only`, `--resume`, startup auto-population) first compares the
file's current SHA-256 against the hash stored on its tracker row. Only a
stored hash that equals the current bytes skips a file; every other case —
new file, no stored hash — proceeds normally.

- **Unchanged bytes** — one indexed lookup + the file's own hash read; no
  chunking, no classification, no bank calls. The log line (see
  [Logs](#logs)):

  ```
  Skipping unchanged file (hash gate): path="…", fileHash="a1b2c3d4e5f6"
  ```

- **Never-ingestable files** — empty/whitespace-only content, content excluded
  by the source's content filter, and files that produce zero chunks — are
  **recorded once, per their content hash**, as a *terminal skip*. The file is
  neither re-chunked nor re-classified on any later pass while its bytes are
  unchanged; the recorded verdict is reused. When the **content changes**, the
  new bytes no longer match the recorded hash and the file **is re-evaluated
  automatically** — a terminal skip is bound to bytes, never to a path
  forever. Each recording logs:

  ```
  terminal-skip-recorded reason=<EMPTY_CONTENT|CONTENT_FILTERED|ZERO_CHUNKS> path="…"
  ```

  The only forced re-evaluation is `--force-reprocess`, which bypasses the
  gate (for filtered files: the escape hatch after a `contentFilter` change,
  see the modes table).
- **The gate fails open.** If its inputs are unreadable (database error, no
  hash computable), the file is processed as if no gate existed — a degraded
  racochu may repeat work but never silently loses a file.

**Observing outcomes.** The per-file lines above plus the per-pass summary tell
you exactly what a run did — batch runs (resume, force-reprocess, auto-populate)
end with:

```
resume finished: files=…, gated-skips=…, terminal-skip-skips=…, verified-skips=…, re-ingested=…
force-reprocess finished: files=…, gated-skips=…, terminal-skip-skips=…, verified-skips=…, re-ingested=…
```

All of this is plain structured-log content (see [Logs](#logs)): grepping these
tokens after a run reproduces the per-outcome histogram — expect high
`gated-skips`/`verified-skips` and near-zero `re-ingested` on repeat starts over
unchanged data.

## Ghost-Edge Cleanup (`--reprocess-edges`)

**Two-pass reprocessing** fixes orphaned "ghost-edge" stubs in persona decision-tree
banks that can persist after a standard `--force-reprocess`.

### What are ghost edges?

Ghost edges occur when the bensyne-mcp consumer creates phantom file records
(ghost stubs) for edge targets that reference relative path handles instead of
absolute paths. Even after fixing the consumer to resolve edge targets before
deriving file ids, the orphaned ghost stubs remain in the database because
`--force-reprocess` re-chunks files but does not delete or re-resolve existing
`file_relations` before creating new ones.

### When to use it

Run `--reprocess-edges` when:
- You've upgraded from an older racochu version that emitted relative path handles
- You see phantom PENDING/unknown stubs in persona bank files
- After any edge-fix regression that causes edges to point at non-existent files
- As part of your regular persona reprocessing workflow (it's safe to run even
  when no ghost edges exist — it's idempotent)

### How it works

The `--reprocess-edges` flag triggers a two-pass reprocessing flow:

1. **First pass (re-chunk):** Materialize all files as usual — read each file,
   chunk it, and ingest the chunks into Mnemosyne. This is identical to
   `--force-reprocess`.

2. **Second pass (re-resolve edges):** After all files in the source have been
   reprocessed, iterate over every file in the bank, fetch its outgoing edges,
   re-resolve each edge target via `resolve_file_ref`, and update any edges
   whose target has changed (e.g., from a ghost stub id to the real file id).
   Orphaned ghost stubs that no longer have incoming edges are pruned.

### Example

Reprocess all persona sources with edge cleanup:

```bash
npx racochu --force-reprocess --process-only --reprocess-edges
```

Reprocess a single persona source with edge cleanup:

```bash
npx racochu --force-reprocess --process-only --reprocess-edges --source agent-persona-worker
```

Or use the provided script:

```bash
./scripts/reprocess-personas.sh
```

The script now automatically passes `--reprocess-edges` for all persona sources.

### Script: `reprocess-personas.sh`

The `scripts/reprocess-personas.sh` script is the recommended way to reprocess
persona decision-tree banks. It:
- Filters the config to include only persona sources (`agent-persona-*`)
- Passes `--force-reprocess --process-only --reprocess-edges` automatically
- Reports the resulting `file_relations` count per persona bank

```bash
# Reprocess all persona sources with edge cleanup
./scripts/reprocess-personas.sh

# Reprocess a single persona source
./scripts/reprocess-personas.sh --source agent-persona-worker

# Rebuild dist before running
./scripts/reprocess-personas.sh --build

# Kill a running racochu instance first
./scripts/reprocess-personas.sh --kill-running
```

## Scripts

| Script                    | Description                                                  |
| ------------------------- | ------------------------------------------------------------ |
| `npm run build`           | Compile TypeScript to `dist/`                                |
| `npm run start`           | Run compiled server                                          |
| `npm run start:dev`       | Run with nodemon + dev config (watches `./watch-folder-dev`) |
| `npm run start:prod`      | Run compiled server (production entry point)                 |
| `npm run test`            | Run unit tests (Jest)                                        |
| `npm run test:watch`      | Run unit tests in watch mode                                 |
| `npm run test:cov`        | Run unit tests with coverage                                 |
| `npm run test:e2e`        | Run e2e tests (requires Docker for Mnemosyne)                |
| `npm run test:e2e:watch`  | Run e2e tests in watch mode                                  |
| `npm run lint`            | Run ESLint                                                   |
| `npm run lint:fix`        | Run ESLint with auto-fix                                     |
| `npm run format`          | Run Prettier                                                 |
 | `npm run bensyne:start`   | Start Mnemosyne MCP via Docker Compose (bensyne)              |
 | `npm run bensyne:stop`    | Stop Mnemosyne MCP container                                  |
 | `npm run bensyne:logs`    | Tail Mnemosyne MCP logs                                       |
 | `scripts/reprocess-personas.sh` | Reprocess persona decision-tree banks with edge cleanup |

## Mnemosyne MCP Integration

The chunker communicates with Mnemosyne via SSE-based MCP:

1. **Session establishment:** `GET /sse` → receives `session_id` via SSE event
2. **Remember chunks:** `POST /messages/?session_id=XXX` with `tools/call` → `memory_remember`
3. **Recall (for verification):** `tools/call` → `memory_retrieve` with query parameter

MnemosyneClient handles session lifecycle transparently, including re-establishment after errors.

### Local Mnemosyne Setup

For development and e2e testing, run the included Docker Compose:

```bash
npm run bensyne:start
```

- Endpoint: `http://localhost:8765`
- Token: `e2e-test-token`
- Data directory: `./data/e2e`
- Build context: self-contained Dockerfile cloning mnemosyne-oss/mnemosyne at pinned commit

## Testing

### Unit Tests

```bash
npm run test          # All unit tests
npm run test:watch    # Watch mode
npm run test:cov      # With coverage report
```

Uses Result pattern for deterministic assertions — no exception handling in tests.

### E2E Tests

```bash
npm run test:e2e      # Full e2e suite (Mnemosyne Docker + FileWatcher flow)
```

Test suites:

- **Chunking and Mnemosyne Ingestion** — verifies ProcessFileUseCase → Mnemosyne via direct API calls
- **FileWatcher Flow** — full end-to-end: file drop → chokidar detection → chunking → ingestion → recall verification

**Requirements:** Docker running (for Mnemosyne container).

## File Roles & Chunking Strategies

Files are classified into roles, each with an optimized chunking strategy:

| Role           | Extensions                      | Strategy            | Token limit |
| -------------- | ------------------------------- | ------------------- | ----------- |
| Agent Sessions | .md (with patterns)             | Markdown-aware      | 400         |
| Obsidian Notes | .md                             | Semantic sections   | 500         |
| Code           | .ts, .js, .py, .go, .java, etc. | Recursive syntactic | 400         |
| Config         | .json, .yaml, .yml, .toml, .ini | Per-key             | per-key     |
| Plain text     | .txt, .log, others              | Text splitter       | 450         |

Role detection order: extension → path patterns → content heuristics.

## Logs

**Location:** `~/.local/share/racochu/logs/`

Logs are structured JSON via Pino, rolled by size (5MB). Symlink `current.log` always points to the active log file.

**Debug output:** Set `NODE_ENV=development` for human-readable pretty-printed logs.

## Graceful Shutdown

On SIGTERM/SIGINT:

1. Stop file watchers
2. Drain processing queue (wait for in-flight files)
3. Close Mnemosyne client sessions

Shutdown timeout: 30 seconds — kills remaining tasks if not drained.

## Troubleshooting

**Mnemosyne "no such column: timestamp" error:**
Stale database. Clean up: `rm -rf data/e2e/mnemosyne.db && npm run bensyne:start`

**Files not being watched:**

- Check `~/.config/racochu.yaml` watchSources path is correct
- Ensure path uses absolute path or `~/` expansion (no relative paths in production config)
- Verify exclude patterns don't accidentally match your files (e.g., `**/.git/**` doesn't match `.git/FETCH_HEAD` at root)

**"No session_id received from SSE endpoint":**
Mnemosyne MCP not reachable. Check:

- `npm run bensyne:logs` for errors
- `curl http://localhost:8765/sse` returns `event: endpoint` SSE event
- Correct URL in config (no trailing `/messages/` or `/mcp`)

**"unable to get local issuer certificate" in logs (MCP init / chunk ingestion):**

Racochu talks to `mcp.url` with Node's built-in `https` (no custom CA configuration in
`BensyneClient`). When the endpoint is fronted by a gateway with a self-signed local CA — e.g.
`https://lite-llm.lan/mcp/bensyne`, which is served by **Caddy with its local CA** — Node does
not trust that CA by default and every MCP call fails with `unable to get local issuer
certificate` (check `~/.local/share/racochu/logs/`).

> The e2e stack has the same requirement: `docker-compose.bensyne.yml` mounts a
> `litellm-ca.pem` into the bensyne container because Python/urllib also refuses the Caddy
> self-signed cert without it.

**Fix (macOS / Linux):**

Racochu runtime scripts automatically use the first existing PEM below when
`NODE_EXTRA_CA_CERTS` is unset:

1. `~/.config/racochu/extra-ca.pem`
2. `~/.config/better-opencode/extra-ca.pem` (shared with `start-dev.sh`)
3. `~/.local/share/racochu/certs/litellm-caddy-root.pem`

To make the choice explicit, or to use another CA bundle, export the variable
before starting Racochu:

```bash
export NODE_EXTRA_CA_CERTS="$HOME/.config/racochu/extra-ca.pem"
npm run start:dev
```

The PEM is machine-local trust material: do not commit it. Restart Racochu in
a fresh terminal after changing it, because Node reads the variable at process
startup.

**Fix (Windows):**

1. Export the Caddy local CA root from the Windows cert store to a PEM file:

   ```powershell
   $cert = Get-ChildItem -Path "Cert:\CurrentUser\Root" |
     Where-Object { $_.Subject -eq "CN=Caddy Local Authority - 2025 ECC Root" } |
     Select-Object -First 1
   $bytes = $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
   $b64 = [Convert]::ToBase64String($bytes, [System.Base64FormattingOptions]::InsertLineBreaks)
   New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.local\share\racochu\certs" | Out-Null
   Set-Content -LiteralPath "$env:USERPROFILE\.local\share\racochu\certs\litellm-caddy-root.pem" `
     -Value "-----BEGIN CERTIFICATE-----`n$b64`n-----END CERTIFICATE-----" -Encoding ascii
   ```

   (Exact cert subject may differ if Caddy has been re-keyed — search `Cert:\CurrentUser\Root`
   for `Subject -match "Caddy"`.)

2. Point Node at it (user-level, applies to all future terminals):

   ```powershell
   setx NODE_EXTRA_CA_CERTS "$env:USERPROFILE\.local\share\racochu\certs\litellm-caddy-root.pem"
   ```

3. **Restart racochu in a fresh terminal** — the env var is read at process start.

**Verify** (Node built-in https, same as `BensyneClient`):

```bash
node -e "const https=require('https');const r=https.request('https://lite-llm.lan/mcp/bensyne',{method:'POST',headers:{'Content-Type':'application/json'}},res=>{console.log('STATUS',res.statusCode);process.exit(0)});r.on('error',e=>{console.error('ERR',e.message);process.exit(1)});r.end())"
```

- TLS failure (`UNABLE_TO_GET_ISSUER_CERT_LOCALLY` / `ERR_TLS_CERT_ALTNAME_INVALID`) → Node still
  doesn't trust the CA.
- `HTTP 401/500` or a valid MCP `ping` response → TLS OK; any non-TLS error is expected without
  an auth header/api key.

**If the Caddy CA is ever re-keyed:** re-export the root from the store over the same PEM —
no code change needed. Do **not** commit the CA PEM to the repo (machine-local trust).

**Duplicate chunk processing:**
Not expected for unchanged files since the content-hash gate — repeats are
reported as `Skipping unchanged file (hash gate)`. Files that genuinely changed,
untracked files whose bytes differ from their recorded hash, or anything
processed via `--force-reprocess` is re-ingested by design; Mnemosyne also
handles dedup at storage level.

## Requirements

- Node.js >= 26.0.0
- npm >= 11.0.0
- Docker (for `npm run bensyne:start`)

## License

MIT
