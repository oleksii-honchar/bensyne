---
type: memory
system: racochu
title: "Mnemosyne SQLite schema versioning gotcha"
createdAt: "2026-07-31T07:30:00Z"
updatedAt: "2026-07-31T07:30:00Z"
tags: [mnemosyne, sqlite, migration]
see_also: []
---

# Mnemosyne SQLite Schema Versioning Gotcha

**Fact:** `rm -rf data/e2e/mnemosyne.db` is required when Mnemosyne schema changes — no migration path.

**Context:** Error: "no such column: timestamp" when new version of Mnemosyne client connects to old database. Docker volume or data folder persists stale schema.

**Impact:** After Mnemosyne upgrade or adding new columns, delete the database file and restart. Production needs manual migration procedure.
