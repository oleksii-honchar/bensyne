---
type: runbook
system: racochu
title: "Troubleshooting"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-08-28T17:23:01Z"
tags: [troubleshooting, operations]
see_also: [memories/0008-mnemosyne-sse-deprecated.memory.md, memories/0009-mnemosyne-schema-versioning.memory.md, memories/0026-forgetfile-file-not-found-noop.memory.md]
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

**Cause 1:** Path misconfiguration or exclude patterns matching files.

**Fix:**
- Verify absolute paths or ~/ expansion in config
- Check exclude patterns: `['.git/**', '**/.git/**', 'node_modules/**']`
- Test with `NODE_ENV=development` for verbose logs

**Cause 2 — dot-named watched root + blanket dotfile exclude.** An exclude like `'**/.*'`
compiles to a regex that matches the watched root itself when the root is a dot-directory
(e.g. `~/.agent-sessions`). chokidar `ignored(root)===true` ⇒ zero events under the root;
startup force-reprocess masks the failure.

**Fix:**
- Root guard in `startWatchingSource` (never exclude the normalized root) + explicit
  per-directory dot excludes instead of `'**/.*'` (see
  [[decisions/0087-chokidar-dot-root-root-guard]])
- **Verify:** new watcher logs `Watcher ready; source="…"`; drop a probe file and expect
  `File added` within `debounceMs`. See [[memories/0023-chokidar-dot-root-self-exclusion]].

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

### "Failed to forget file after 3 retries" (FILE_NOT_FOUND noise)

**Symptom:** Recurring `ERROR: Failed to forget file after 3 retries` log spam
in racochu logs (e.g. `racochu.154.log`), with response text
`{"text":"Error calling tool 'forgetFile': forgetFile failed: FILE_NOT_FOUND — details: {...}"}`.
The referenced file exists on disk. Change/delete events for the file trigger
the storm.

**Cause:** Pre-DEC-0099 contract mismatch — bensyne-mcp raised
`ValidationError` on missing file rows; FastMCP wrapped it in a `text` field
with no `status`; racochu's `status`-only success check missed it.

**Fix:**
1. Upgrade to a bensyne-mcp build that includes DEC-0099 (server returns
   `Result.ok({"status": "FILE_NOT_FOUND"})`).
2. Upgrade to a racochu build that includes DEC-0100 (defensive client
   fallback for error-wrapped responses).
3. **Verify:** call `bensyne_getFileChunks` for the path; expect
   `status: "FILE_NOT_FOUND"` for a missing-row path. Re-trigger the change
   event; expect a debug-level log line and **zero** `ERROR`/`retry` log lines.

This is a no-op (the file had nothing to forget anyway), not data loss. File
rows are broadly missing for `agent-sessions` after the 2026-08-24
mass-forget recovery backfill, so this symptom is expected on legacy paths.
See [[memories/0026-forgetfile-file-not-found-noop]].

## Logs

- **Location:** `~/.local/share/rag-content-chunker/logs/`
- **Format:** Structured JSON via Pino, rolled by size (5MB)
- **Symlink:** `current.log` → active log file
- **Debug:** `NODE_ENV=development` for pretty-printed logs
