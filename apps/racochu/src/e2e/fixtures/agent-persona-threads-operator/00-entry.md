---
id: 00-entry
title: "Enter: load grounding and navigator skill, resolve target"
entry: true
conditions:
  - "user requests Threads post scraping (a specific handle, post URL, thread) OR feed reading/analysis (\"read my feed\", \"top-N posts\", \"scroll the feed\") OR media collection for feed posts"
veto:
  - "navigating Threads without the social-networks-navigator skill loaded"
  - "attempting to mutate or interact with Threads content (write operations prohibited)"
  - "using OCR when the script-first path is available (validated 2026-09-05)"
edges:
  - target: 10-discovery/10-discover.md
    when: "target handle or post URL identified and chrome-debug instance available"
  - target: 10-discovery/30-feed-walk.md
    when: "user asks to read/analyze the feed, top-N posts, or scroll the thread feed (logged-in profile)"
  - target: 10-discovery/40-media-download.md
    when: "user asks to collect images/videos from feed posts (feed-only, soft-flag-safe)"
  - target: 60-handoff/10-surface-problem.md
    when: "which thread/post to scrape is ambiguous or unknown"
  - target: 60-handoff/20-check-browser.md
    when: "chrome-debug instance on :9222 not running (pre-flight check)"
  - target: self-reflect.md
    when: "task completed and results evaluated"
created: 2026-09-03
updated: 2026-09-05
status: active
---
# Enter: load grounding and navigator skill, resolve target

**Before starting:** Record your traversal transition to this node in your session memory bank.

Read `~/.rules/olho/always-apply/*.mdc` and `10-tools.mdc`, load the `social-networks-navigator` skill, then identify the target Threads post to scrape from user input (handle + post URL, a profile handle to discover, **or a feed-read / media request**). If the target is ambiguous, surface to the user. Verify chrome-debug instance on :9222 is running before proceeding.

**Primary path (validated 2026-09-05):** after mounting the post page, extract with
`scripts/threads-stitch.mjs` (CDP-direct, djb2-verified, no OCR). Feed discovery
uses `scripts/threads-feed-scroll.mjs` (+ serial `threads-read-posts-batch.mjs`);
media-only requests use `scripts/threads-feed-media.mjs` (feed-only, no post mount). OCR
is fallback only — see the 30-capture nodes.
