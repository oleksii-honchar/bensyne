---
type: adr
id: ADR-0006
title: "RotatingFileHandler for Application Logging"
status: accepted
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [logging, file, rotation]
see_also: ["memories/0003-bensyne-file-logging-rotation.memory.md"]
---

# ADR-0006: RotatingFileHandler for Application Logging

## Context

Bensyne needs persistent logging for operational debugging and audit trail. Console-only logging is lost on restart and provides no historical analysis capability.

## Decision

Use Python's `RotatingFileHandler` for file logging alongside console output. The `setup_logging()` function in `src/utils/logging.py` creates both a `StreamHandler` (stdout) and a `RotatingFileHandler` (file) on startup.

**Configuration:**
- Log file: `~/.local/share/bensyne/logs/bensyne.log` (default, configurable via `log_file` parameter)
- Rotation: 10 MB per file, 3 backups retained
- Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- Level: configurable via `LOG_LEVEL` env var (default: INFO)

## Rationale

1. **RotatingFileHandler prevents unbounded growth** — 10 MB rotation with 3 backups caps disk usage at ~30 MB
2. **No external dependencies** — uses Python stdlib only
3. **Both stdout and file** — console for live monitoring, file for historical analysis
4. **Auto-creates parent directories** — `mkdir -p` equivalent on first write
5. **Duplicate handler protection** — `if not logger.handlers` prevents repeated calls from adding extra handlers

## Alternatives Considered

1. **Console-only logging** — no persistence, lost on restart
2. **TimeRotatingFileHandler** — rotates by time, not size; could create many small files
3. **External logging service** — overkill, adds infrastructure complexity

## Consequences

- **Positive:** Persistent logs for debugging and audit; bounded disk usage
- **Negative:** Disk I/O on every log write
- **Mitigation:** 10 MB rotation threshold means I/O impact is minimal; buffered writes in Python stdlib
