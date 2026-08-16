---
type: memory
title: "Bensyne Log File Location and Rotation"
createdAt: "2026-08-07T18:01:00Z"
updatedAt: "2026-08-07T18:01:00Z"
tags: [logging, file, rotation, operational]
see_also:
  - "adrs/0006-rotating-file-handler-logging.adr.md"
deprecated:
  date: null
  reason: null
  superseded_by: null
---

# Memory: Bensyne Log File Location and Rotation

## Fact

Bensyne logs to `~/.local/share/bensyne/logs/bensyne.log` with RotatingFileHandler — 10 MB rotation, 3 backups retained.

## Context

The `setup_logging()` function in `src/utils/logging.py` creates both a StreamHandler (stdout) and RotatingFileHandler (file) on startup. The log file path is configurable via the `log_file` parameter; the default is `~/.local/share/bensyne/logs/bensyne.log`.

## Impact

Operational debugging requires knowing the log location. Log rotation prevents disk exhaustion — max ~30 MB of log files at any time. The `LOG_LEVEL` environment variable controls logging verbosity (default: INFO).
