---
type: concept
system: racochu
title: "Session Metadata Service"
createdAt: "2026-08-06T12:00:00Z"
updatedAt: "2026-08-06T12:00:00Z"
tags: [infrastructure, caching, session, metadata]
see_also: [concepts/0017-agent-session-chunking.concept.md, concepts/0016-chunking-strategy-pattern.concept.md]
---

# Concept: Session Metadata Service

## What

An injectable NestJS service that extracts and caches session metadata from `session.md` frontmatter. Caches metadata with a 5-minute TTL and degrades gracefully — if `session.md` is missing or unparseable, returns empty metadata so chunking continues.

## Why

Agent session chunking requires metadata from the parent `session.md`. Without caching, every chunked file would trigger a filesystem read — for sessions with many files, this becomes a performance bottleneck. Graceful degradation ensures chunking continues even if `session.md` is temporarily unavailable.

## Key Details

**Implementation (verified in `src/infrastructure/services/session-metadata.service.ts`):**

```typescript
@Injectable()
class SessionMetadataService {
  private readonly cache = new Map<string, { metadata: SessionMetadata; timestamp: number }>()
  private readonly TTL_MS = 5 * 60 * 1000 // 5 minutes

  async extract(sessionPath: string): Promise<Result<SessionMetadata>> {
    const cached = this.cache.get(sessionPath)
    if (cached && Date.now() - cached.timestamp < this.TTL_MS) {
      return Result.ok(cached.metadata)
    }
    // ... read session.md, parse frontmatter, cache result
  }
}
```

**SessionMetadata interface (verified in `src/domain/session-metadata.type.ts`):**

| Field | Type | Description |
|-------|------|-------------|
| `sessionId` | `string` | Platform session ID (e.g., `ses_057e...`) |
| `createdAt` | `string` | Session creation timestamp (ISO 8601) |
| `status` | `string` | Session status (e.g., `in-progress`) |
| `phase` | `string` | Session phase (e.g., `implementation`) |
| `nextAgent` | `string` | Next agent in the workflow |

**Caching behavior:**
- **In-memory Map** — keyed by `sessionPath` (not file path)
- **5-minute TTL** — expires after 5 minutes; next read triggers filesystem refresh
- **Graceful degradation** — if `session.md` is missing or YAML parse fails, returns empty metadata with all fields as empty strings

**Not a:** Persistent cache — no database backing. On server restart, cache is empty and all metadata is re-read from filesystem.
