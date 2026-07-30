# Better Mnemosyne

Multi-tenant, namespace-aware MCP server for mnemosyne-oss. Dynamically routes memory operations to isolated SQLite bank instances per namespace via streamable HTTP transport (FastMCP).

## Why This Exists

mnemosyne-oss is excellent as a single-agent memory backend — but it has two hard limitations for multi-context deployments:

- **Single database:** All memories go into one SQLite DB. There's no built-in namespace routing, so agent sessions, vaults, projects, and users share the same memory pool.
- **SSE-only transport:** The built-in MCP server only supports SSE and stdio. It does not support the streamable HTTP transport that modern MCP clients expect.

**Better-mnemosyne solves both:**
- Embeds mnemosyne-oss directly and adds a namespace router on top — each namespace gets its own SQLite bank (`default`, `agent-sessions`, `obsidian-vault`, etc.), created dynamically on first request.
- Uses FastMCP to expose the same MCP tools over native streamable HTTP transport.

From the client side, it looks like a standard Mnemosyne MCP server. You just add `namespace: "your-context"` to route memories to the right bank.

## Overview

Better Mnemosyne replaces the traditional mcp-proxy → stdio bridge architecture with a native streamable HTTP MCP server. It dynamically forks mnemosyne-oss instances per namespace on first request, providing a singular MCP interface for remembering and recalling memories across isolated namespaces.

### Architecture

```
┌─────────────┐     MCP (streamable HTTP)     ┌──────────────────────────────────────┐
│   Client    │ ◄──────────────────────────►  │        Better Mnemosyne              │
│  (Agent/    │                               │                                      │
│   Tool)     │                               │  ┌────────────────────────────────┐  │
└─────────────┘                               │  │      Namespace Router          │  │
                                              │  │                                │  │
                                              │  │  default ──► MnemosyneClient   │  │
                                              │  │  projectA ─► MnemosyneClient   │  │
                                              │  │  projectB ─► MnemosyneClient   │  │
                                              │  │                                │  │
                                              │  │  • Double-checked locking      │  │
                                              │  │  • LRU eviction (max 50)       │  │
                                              │  │  • Default never evicted       │  │
                                              │  └────────────────────────────────┘  │
                                              │                                      │
                                              │  ┌────────────────────────────────┐  │
                                              │  │      Bank Manager              │  │
                                              │  │                                │  │
                                              │  │  default → data/mnemosyne.db   │  │
                                              │  │  projectA → data/banks/        │  │
                                              │  │            projectA/           │  │
                                              │  │            mnemosyne.db        │  │
                                              │  └────────────────────────────────┘  │
                                              └──────────────────────────────────────┘
```

### Key Features

- **Namespace isolation:** Each namespace gets its own SQLite database
- **Dynamic instantiation:** Instances created on first request (no idle processes)
- **LRU eviction:** Oldest non-default instances evicted when over limit (default: 50)
- **Default fallback:** Requests without namespace use the "default" bank
- **Streamable HTTP:** Native MCP protocol over HTTP (no stdio proxy)
- **Health monitoring:** Built-in health, readiness, and log endpoints

## Quick Start

### Docker Run (Production)

```bash
# Pull and run with persistent data volume
docker run -d \
  --name better-mnemosyne \
  -p 3000:3000 \
  -v /data/mnemosyne/data:/data/mnemosyne/data \
  tuiteraz/better-mnemosyne:latest

# Verify health
curl http://localhost:3000/health
# {"status": "healthy", "instances": 1, "namespaces": ["default"]}
```

### Docker Compose

```bash
# Production
docker-compose up -d

# Development (with source code mount)
docker-compose -f docker-compose.dev.yml up -d
```

## Local Development

### Prerequisites

- Python 3.12+
- Docker (optional, for containerized runs)

### Setup

```bash
# Clone and enter project
cd /path/to/better-mnemosyne

# Run setup script (creates .venv, installs dependencies)
./scripts/setup.sh

# Activate virtual environment
source .venv/bin/activate
```

### Run Dev Server

```bash
# Using start script (uses ./data/dev as data directory)
./scripts/start.sh

# Or directly with main.py
python3.12 main.py --port 3000 --data-dir ./data/dev --log-level DEBUG
```

### Run Tests

```bash
# Unit and integration tests
./scripts/test.sh

# Or directly with pytest
pytest src/tests/ -v
```

## Docker

### Build Image

```bash
# Using build script
./scripts/build.sh

# Or manually
docker build -t better-mnemosyne .
```

### Run Container

```bash
# Basic run with data volume
docker run -p 3000:3000 -v ./data:/data/mnemosyne/data better-mnemosyne

# With custom port and log level
docker run -p 3001:3000 better-mnemosyne python main.py --port 3000 --log-level DEBUG
```

### Docker Compose (Production)

See `docker-compose.yml`:

```yaml
version: '3.8'

services:
  better-mnemosyne:
    image: tuiteraz/better-mnemosyne:latest
    ports:
      - "3000:3000"
    volumes:
      - /data/mnemosyne/data:/data/mnemosyne/data
    environment:
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

### Docker Compose (Development)

See `docker-compose.dev.yml` — mounts source code for live development:

```bash
docker-compose -f docker-compose.dev.yml up -d
```

## API Reference

### MCP Tools

All tools support an optional `namespace` parameter (default: `"default"`).

| Tool | Description | Required Params | Optional Params |
|------|-------------|-----------------|-----------------|
| `mnemosyne_remember` | Store a durable memory | `content` (string) | `namespace`, `importance` (0.0-1.0), `source`, `scope`, `valid_until`, `extract_entities`, `extract`, `metadata`, `veracity` |
| `mnemosyne_recall` | Search for relevant memories | `query` (string) | `namespace`, `limit` (int, default 5) |
| `mnemosyne_forget` | Permanently delete a memory | `memory_id` (string) | `namespace` |
| `mnemosyne_update` | Update memory content or importance | `memory_id` (string) | `namespace`, `content`, `importance` |
| `mnemosyne_sleep` | Trigger memory consolidation | — | `namespace` |
| `mnemosyne_stats` | Return memory statistics | — | `namespace` |
| `mnemosyne_list_namespaces` | List all active namespaces | — | — |

### Namespace Parameter

- **Type:** `string`
- **Default:** `"default"`
- **Behavior:** 
  - Requests without `namespace` use the default bank (`{data_dir}/mnemosyne.db`)
  - Requests with `namespace` route to `{data_dir}/banks/{namespace}/mnemosyne.db`
  - New namespaces are created dynamically on first access
  - Default namespace is never evicted

### Health Endpoints

| Endpoint | Method | Description | Response |
|----------|--------|-------------|----------|
| `/health` | GET | Overall health status | `{"status": "healthy", "instances": N, "namespaces": [...]}` |
| `/health/ready` | GET | Readiness check (startup) | `{"status": "ready"}` (200) or `{"status": "starting"}` (503) |
| `/health/log` | GET | Log level and recent entries | `{"log_level": "INFO", "recent_logs": [...]}` |

### Example MCP Request/Response

**Remember (with namespace):**

```json
// Request (via MCP protocol)
{
  "method": "tools/call",
  "params": {
    "name": "mnemosyne_remember",
    "arguments": {
      "content": "User prefers dark mode in the dashboard",
      "namespace": "user-123",
      "importance": 0.8,
      "source": "user"
    }
  }
}

// Response
{
  "status": "stored",
  "memory_id": "mem-abc123",
  "namespace": "user-123"
}
```

**Recall (from specific namespace):**

```json
// Request
{
  "method": "tools/call",
  "params": {
    "name": "mnemosyne_recall",
    "arguments": {
      "query": "UI preferences",
      "namespace": "user-123",
      "limit": 3
    }
  }
}

// Response
{
  "results": [
    {
      "memory_id": "mem-abc123",
      "content": "User prefers dark mode in the dashboard",
      "importance": 0.8,
      "source": "user"
    }
  ],
  "namespace": "user-123"
}
```

**List Namespaces:**

```json
// Request
{
  "method": "tools/call",
  "params": {
    "name": "mnemosyne_list_namespaces",
    "arguments": {}
  }
}

// Response
{
  "namespaces": [
    {"name": "default", "bank": "default", "status": "active", "memory_count": 0},
    {"name": "user-123", "bank": "user-123", "status": "active", "memory_count": 0},
    {"name": "project-alpha", "bank": "project-alpha", "status": "active", "memory_count": 0}
  ]
}
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Python log level | `INFO` |
| `PYTHONUNBUFFERED` | Enables unbuffered stdout (for Docker) | `1` |
| `PYTHONPATH` | Python module search path | `/app/src` |

### YAML Configuration

Edit `config/default.yaml`:

```yaml
server:
  name: "better-mnemosyne"
  version: "1.0.0"
  transport: "streamable-http"
  host: "0.0.0.0"
  port: 3000

logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  log_file: null

instance_pool:
  max_instances: 50
  eviction_timeout: 300
  data_dir: "/data/mnemosyne/data"
  default_bank: "default"
```

### CLI Arguments

Arguments passed to `main.py` override YAML config:

| Argument | Description | Default |
|----------|-------------|---------|
| `--port` | Port to listen on | `3000` (from config) |
| `--data-dir` | Data directory for SQLite databases | `/data/mnemosyne/data` (from config) |
| `--log-level` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` (from config) |

Example:

```bash
python3.12 main.py --port 8080 --data-dir ./my-data --log-level DEBUG
```

## Usage Examples

### Store Memory in Custom Namespace

```bash
# Via MCP client (conceptual — actual call depends on your MCP client)
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "mnemosyne_remember",
      "arguments": {
        "content": "Project Alpha uses TypeScript and FastAPI",
        "namespace": "project-alpha",
        "importance": 0.9
      }
    },
    "id": 1
  }'
```

### Recall from Specific Namespace

```bash
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "mnemosyne_recall",
      "arguments": {
        "query": "tech stack",
        "namespace": "project-alpha"
      }
    },
    "id": 2
  }'
```

### List Active Namespaces

```bash
curl -X POST http://localhost:3000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "mnemosyne_list_namespaces",
      "arguments": {}
    },
    "id": 3
  }'
```

### Connect via MCP Client

Configure your MCP client (e.g., Claude Desktop, Cursor, VS Code extension) with:

```json
{
  "mcpServers": {
    "better-mnemosyne": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

## Architecture Details

### Namespace Routing

- **Default instance:** Created at server startup for the "default" namespace
- **Dynamic creation:** When a request arrives with a new namespace, the router creates a new MnemosyneClient instance
- **Double-checked locking:** Ensures thread-safe instance creation under concurrent requests
- **Instance caching:** Subsequent requests to the same namespace reuse the cached instance

### Instance Pool and Eviction

- **Max instances:** Configurable limit (default: 50) prevents unbounded growth
- **LRU eviction:** When the limit is reached, the oldest (first created) non-default instance is evicted
- **Default protection:** The "default" namespace instance is never evicted
- **Eviction trigger:** Happens synchronously during instance creation (not on a timer)

### Data Layout

```
{data_dir}/
├── mnemosyne.db              # Default namespace
└── banks/
    ├── project-alpha/
    │   └── mnemosyne.db      # project-alpha namespace
    ├── user-123/
    │   └── mnemosyne.db      # user-123 namespace
    └── ...
```

## Troubleshooting

### Port Already in Use

**Symptom:** `OSError: [Errno 48] Address already in use`

**Fix:**
```bash
# Find process using port 3000
lsof -i :3000

# Kill it or use a different port
python main.py --port 3001
```

### Data Directory Permissions

**Symptom:** `PermissionError: [Errno 13] Permission denied`

**Fix:**
```bash
# Ensure data directory exists and is writable
mkdir -p /data/mnemosyne/data
chmod 755 /data/mnemosyne/data

# In Docker, ensure volume mount has correct permissions
docker run -v $(pwd)/data:/data/mnemosyne/data better-mnemosyne
```

### Server Not Responding

**Symptom:** Health check returns 503 or no response

**Fix:**
```bash
# Check if server started
curl http://localhost:3000/health

# Check logs
curl http://localhost:3000/health/log

# Run with DEBUG logging
python main.py --log-level DEBUG
```

### Namespace Not Found in list_namespaces

**Note:** `mnemosyne_list_namespaces` only returns namespaces that have active instances. If an instance was evicted due to the max_instances limit, it won't appear until a new request creates it again.

**Fix:** Make a request to the namespace to recreate its instance, then list again.

### Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `ValidationError: content is required` | `mnemosyne_remember` called without content | Include `content` parameter |
| `ValidationError: query is required` | `mnemosyne_recall` called without query | Include `query` parameter |
| `ValidationError: memory_id is required` | `mnemosyne_forget`/`update` called without memory_id | Include `memory_id` parameter |
| Connection refused | Server not running | Start server with `./scripts/start.sh` or `python main.py` |

## License

MIT License — see [LICENSE](LICENSE) for details.
