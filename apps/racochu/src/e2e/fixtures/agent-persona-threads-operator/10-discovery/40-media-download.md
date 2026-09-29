---
id: 10-discovery-40-media-download
title: "Media download — feed-only, soft-flag-safe"
entry: false
conditions:
  - "user asks to collect images/videos attached to feed posts (or media is part of a feed request)"
  - "feed cards visible in the logged-in Home feed (post pages NOT required)"
veto:
  - "mounting post pages for media (the feed-only path is the soft-flag-safe way)"
  - "using raw Node curl/fetch of CDN URLs (403 — must fetch in page context with credentials: include)"
  - "classifying avatars as post media (skip t51.2885-19/-19; post media is t51.82787-15 / t51.71878-15)"
  - "selecting a non-first srcset variant when full-res is wanted (first = 1086w, no stp= transform)"
edges:
  - target: 40-aggregate/10-aggregate.md
    when: "media downloaded and deduped per pid into media-archive/<pid>/<author>-<n>.<ext>"
  - target: 60-handoff/10-surface-problem.md
    when: "challenge/wall or zero media found — surface"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# Media download — feed-only, soft-flag-safe

**Before starting:** Record your traversal transition to this node in your session memory bank.

Download attached images/videos for feed posts **without mounting any post page**
(works even when the §soft-flag stopped post-page mounts):

```bash
node <skill>/scripts/threads-feed-media.mjs [--out-dir media-archive] [--limit N] [--max-pages N] [--skip N]
```

- Collects `<img>` (post images `t51.82787-15`, video covers `t51.71878-15`) and
  `<video>` (mp4) from feed cards; **skips avatars** (`t51.2885-19`/`-19` — the `-15`
  suffix is the discriminator, NOT just `t51.82787`).
- For images picks the **first srcset variant** (1086w, no `stp=` transform) = the
  full-res original; falls back to `currentSrc` (thumbnail).
- Fetches **in page context** (`fetch(url, { credentials: "include" })` → base64 → disk).
  The browser's CDN session authorizes it (raw Node `curl` → 403).
- Writes `media-archive/<pid>/<author>-<n>.<ext>`; dedupes by pid+URL; paced
  (700–1400 ms/media, 2–4 s/post). Handles hyphen pids.
- **Verified 2026-09-05:** 14 files from 4 feed posts (9 jpg + 3 webp + 2 mp4, 2.15 MB),
  full-res images 127–296 KB, 0 failures — all without a single post-page mount.
