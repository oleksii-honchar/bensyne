# racochu

File watcher that detects changes, semantically chunks content using Mastra RAG, and ingests chunks into Mnemosyne MCP for retrieval-augmented generation.

DDD-based NestJS CLI server. No Effect library — uses Result pattern for error handling.

Racochu = RAg COntent CHUnker 

## Quick Start

### Development

1. Start Mnemosyne MCP (Docker):

   ```bash
   npm run bensyne:start
   ```

2. Start the chunker with dev config:

   ```bash
   npm run start:dev
   ```

   Watches `./watch-folder-dev` by default.

3. Drop files into `watch-folder-dev/` — they are auto-chunked and ingested.

### Production

1. Create `~/.config/racochu.yaml` (see [Configuration](#configuration))
2. Run:
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

**Processing model:** Files are processed sequentially via a bounded async queue to avoid overwhelming Mnemosyne. Duplicate processing is prevented by tracking in-memory hashes of recently processed files.

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
    ttlDays: 365   # optional: forget files older than this many days

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
    ttlDays: 365   # optional; absent = no TTL
    sourceType: agent-sessions
```

The TTL sweep runs:

- **At startup** in all modes (non-fatal — a sweep failure is logged and boot continues), and
- **Once a day** while running in watch mode (`start`/`start:dev`), and
- **On demand** via `racochu --ttl-sweep` (optionally scoped with `-s/--source`; combine with `--dry-run` to preview).

`--dry-run` reports what *would* be forgotten without deleting anything.

> **Mass-forget guard:** the sweep refuses to forget more than **20 files per
> source** in one run (same guard as exclude reconciliation). If a source has
> more expired files than that — e.g. the first backfill sweep after a year of
> accumulation — run it once with `RACOCHU_RECONCILE_FORCE_FORGET=1` to
> acknowledge the mass-forget and let the sweep proceed.
>
> **Safety notes:** the sweep only touches sources with `ttlDays` set; expiry is
> measured from first ingest (`FileTracker.createdAt`); the source files
> themselves are never deleted from disk — only their memories and trackers.

## CLI Modes

Racochu is a CLI with one-shot maintenance modes and a default watch mode.
Pass the flag to select the mode (help: `racochu --help`):

| Flag | Mode |
| ---- | ---- |
| *(no flag)* | **Watch** — default: watch sources and ingest new/changed files continuously. **Auto-populates** all watched sources on startup, processing existing files to seed the Mnemosyne database. |
| `--process-only` | Process existing files once, then exit (no watching) |
| `-f, --force-reprocess` | Force re-process all sources (sequential reprocess of every file) |
| `--reprocess-edges` | Two-pass reprocessing: after re-chunking files, re-resolve all edge targets via `resolve_file_ref` to fix ghost edges (see [Ghost-Edge Cleanup](#ghost-edge-cleanup--reprocess-edges)) |
| `-r, --resume` | Resume missing chunks: re-process only files with missing stored chunks |
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

`--resume` now includes verification that detects and repairs stub rows
(incomplete file tracker entries). Files with missing or partial chunk records
are automatically re-processed, eliminating the need for manual intervention
to fix stub row issues.

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
Normal on restart — in-memory dedup is reset. Mnemosyne handles dedup at storage level.

## Requirements

- Node.js >= 26.0.0
- npm >= 11.0.0
- Docker (for `npm run bensyne:start`)

## License

MIT
