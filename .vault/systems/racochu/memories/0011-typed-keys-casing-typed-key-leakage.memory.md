---
type: memory
title: "TYPED_KEYS Casing Fix — Capitalized Keys Leak into Properties"
createdAt: "2026-08-08T13:55:00Z"
updatedAt: "2026-08-08T13:55:00Z"
tags: [obsidian, frontmatter, casing, gotcha]
see_also: ["adrs/0026-generic-frontmatter-preservation.adr.md"]
---

# Memory: TYPED_KEYS Casing Fix — Capitalized Keys Leak into Properties

## Fact

TYPED_KEYS exclusion uses original key casing from YAML — `TYPED_KEYS.has(key)` instead of `TYPED_KEYS.has(key.toLowerCase())`. Capitalized frontmatter keys (e.g. `Tags`, `Created`) were not excluded and leaked into the `properties` map, creating duplicate data at `note.tags` (typed) and `note.properties.tags` (from `Tags`).

## Context

The TYPED_KEYS set contains lowercase keys: `aliases, tags, created, modified, source, status, type, base`. YAML frontmatter keys are case-sensitive — Obsidian properties like `Tags` or `Created` are valid and common. The loop iterating `Object.entries(parsed)` receives the original key casing.

## Impact

Capitalized typed keys appeared in both typed fields and properties, creating duplicate/misleading metadata on chunks. Fixed at line 40 of `obsidian-chunking.strategy.ts`: `TYPED_KEYS.has(key.toLowerCase())` ensures case-insensitive exclusion. Test added: capitalized `Tags`, `Created`, `Aliases` don't appear in properties.
