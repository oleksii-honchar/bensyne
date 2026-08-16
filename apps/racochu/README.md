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

**File:** `~/.config/racochu.yaml` (production) or `dev.yaml` (development via `APP_CONFIG_PATH` env var)

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

**Duplicate chunk processing:**
Normal on restart — in-memory dedup is reset. Mnemosyne handles dedup at storage level.

## Requirements

- Node.js >= 26.0.0
- npm >= 11.0.0
- Docker (for `npm run bensyne:start`)

## License

MIT
