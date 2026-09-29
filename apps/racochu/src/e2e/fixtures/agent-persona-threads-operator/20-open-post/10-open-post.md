---
id: 20-open-post-10-open-post
title: "Open the post page (thread view) with feed-redirect gotcha"
entry: false
conditions:
  - "target root post ID is known from discovery"
  - "chrome-debug instance confirmed running with authenticated session"
veto:
  - "clicking Reply links or per-part links instead of clicking the post's own URL link (anti-pattern)"
  - "proceeding to scroll without verifying href ends in /post/<rootId>"
edges:
  - target: 30-capture/10-capture-loop-entry.md
    when: "verified post page with Thread heading, view count, and stacked parts visible"
  - target: 60-handoff/10-surface-problem.md
    when: "post page loads but shows error (404, deleted post, or private thread)"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# Open the post page (thread view) with feed-redirect gotcha

**Before starting:** Record your traversal transition to this node in your session memory bank.

Navigate to the post URL (`https://www.threads.net/@<handle>/post/<rootId>`) using chrome-debug. Sleep 3 seconds for render. **Critical gotcha:** Threads usually renders the target post inside the "For you" feed — the URL stays at `threads.com/` even after navigation. If this happens, click the post's own link (NOT per-part navigation): use evaluate_script to find and click the anchor element matching `/post/<rootId>`. **Confirm** that `location.href` ends in `/post/<rootId>` — this is the only valid indicator you're on the actual thread page. The post page holds every part stacked in order, each with its own N / M badge and URL.
