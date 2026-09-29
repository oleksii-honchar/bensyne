---
id: 30-capture-20-scroll-into-view
title: "Scroll part into view (with pacing)"
entry: false
conditions:
  - "post page confirmed; target part not yet fully visible"
veto:
  - "clicking per-part Reply or navigation links instead of scrolling (anti-pattern from canonical flow)"
  - "scrolling more than one viewport at a time (one part scroll cycle only)"
edges:
  - target: 30-capture/30-screenshot.md
    when: "target part is fully within the viewport"
  - target: 30-capture/20-scroll-into-view.md
    when: "part still not fully visible after scrolling (loop scroll until in view)"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# Scroll part into view (with pacing)

**Before starting:** Record your traversal transition to this node in your session memory bank.

Use evaluate_script to scroll the page by approximately one viewport height toward the target part: `window.scrollBy(0, window.innerHeight * 0.9)`. **Pacing:** sleep 1–2 seconds between scroll and screenshot. The goal is to bring the target N / M badge and its content fully into view — only that part, not further down (one scroll per capture cycle).
