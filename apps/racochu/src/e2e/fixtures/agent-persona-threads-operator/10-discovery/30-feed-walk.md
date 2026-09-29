---
id: 10-discovery-30-feed-walk
title: "Feed walk — discover post URLs, then serial reads"
entry: false
conditions:
  - "user asks to read/analyze the Threads feed, top-N posts, or scroll the thread feed"
  - "logged-in Home feed available in the chrome-debug instance"
veto:
  - "numeric tab index selection (CDP /json index != MCP pageId; match by root pathname + Home title)"
  - "using getAttribute(\"href\") on post links (returns relative URL — use a.href property)"
  - "pid regex without hyphen support ([A-Za-z0-9_-]+ — pids like Dc4K99UHz-K exist)"
  - "cold --navigate deep-link open as PRIMARY (SSR-bounces to Home; use SPA-click)"
  - "exceeding the human-paced volume cap (serial reads one post at a time, one tab)"
edges:
  - target: 10-discovery/30-feed-walk.md
    when: "soft-flag NOT observed — continue the walk / reads"
  - target: 60-handoff/10-surface-problem.md
    when: "soft-flag observed (post pages stop mounting: SSR bounce / SPA-click ignored / articles=0) — STOP, wait >= 24h"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# Feed walk — discover post URLs, then serial reads

**Before starting:** Record your traversal transition to this node in your session memory bank.

Walk the logged-in Home feed and read the top posts **serially and human-paced**:

```bash
node <skill>/scripts/threads-feed-scroll.mjs [--max-steps N] [--out data-feed-pids.json] [--tab PAGE_IDX]
```

- Paced scroll (1.5–2.5 s/step) collecting deduped pids; stops at `--max-steps` / 2
  no-new-pid jumps. Exit codes: 0 ok · 1 error · **2 challenge/wall abort → STOP** · 3 usage.
- For top-N: `--max-steps` sized to N×~1.3, then rank by feed order and read the first N
  with the **serial batch reader** `threads-read-posts-batch.mjs`:
  SPA-click the post's own link → read pause 2–4.5 s → extract per pid via
  `threads-stitch.mjs` **without `--navigate`** (the post is already mounted) →
  back/close → feed pause 3–5 s.
- Outputs: `data-feed-pids.json` + `data-feed-scroll.log` (walk); per post
  `stitched-post-<pid>.txt` + `data-threads-spans-<pid>.json` (reads).

**Soft-flag stop (validated 2026-09-05):** after ~11 serial reads the post page stopped
mounting on every path — cold `Page.navigate` SSR-bounced to Home; SPA-click did nothing;
profile-warm + `pushState` routed the URL but `articles=0`; the threads.net mirror also
bounced. Feed/profile still rendered. **Treat as an early stop condition: STOP the read
loop, wait ≥24 h, do not retry same-day; feed-only media remains safe.**
