---
type: runbook
system: racochu
title: "Troubleshooting"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [troubleshooting, operations]
see_also: [memories/0008-mnemosyne-sse-deprecated.memory.md, memories/0009-mnemosyne-schema-versioning.memory.md]
---

# Runbook: Troubleshooting

## Common Issues

### "no such column: timestamp"

**Cause:** Stale Mnemosyne database schema.

**Fix:**
```bash
rm -rf data/e2e/mnemosyne.db
npm run mnemosyne:start
```

### Files not being watched

**Cause:** Path misconfiguration or exclude patterns matching files.

**Fix:**
- Verify absolute paths or ~/ expansion in config
- Check exclude patterns: `['.git/**', '**/.git/**', 'node_modules/**']`
- Test with `NODE_ENV=development` for verbose logs

### "No session_id received from SSE endpoint"

**Cause:** Mnemosyne MCP not reachable or wrong URL.

**Fix:**
- Check `curl http://localhost:8765/mcp` (POST with initialize request)
- Verify URL in config has no trailing `/messages/` or `/mcp`
- Check Mnemosyne logs: `npm run mnemosyne:logs`

### Duplicate chunk processing on restart

**Cause:** In-memory dedup resets on restart.

**Fix:** Expected behavior — Mnemosyne handles dedup at storage level. See memory [[memories/0010-mnemosyne-dedup-inmemory-reset.memory]].

### "Received request before initialization was complete"

**Cause:** SSE transport deprecated — init handshake race.

**Fix:** Already resolved — codebase uses Streamable HTTP transport via mcp-proxy. See memory [[memories/0008-mnemosyne-sse-deprecated.memory]].

## Logs

- **Location:** `~/.local/share/rag-content-chunker/logs/`
- **Format:** Structured JSON via Pino, rolled by size (5MB)
- **Symlink:** `current.log` → active log file
- **Debug:** `NODE_ENV=development` for pretty-printed logs
