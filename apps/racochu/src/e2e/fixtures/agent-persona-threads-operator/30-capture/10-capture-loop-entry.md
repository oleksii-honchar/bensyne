---
id: 30-capture-10-capture-loop-entry
title: "Extract with script (primary) or OCR fallback"
entry: false
conditions:
  - "post page confirmed (location.href ends /post/<rootId>) with parts stacked in view"
  - "skill scripts available: skills/social-networks-navigator/scripts/threads-stitch.mjs"
veto:
  - "using OCR when the script can run (script-first is the validated primary path)"
  - "hand-typing any thread text (script verbatim or OCR/snapshot JSON only)"
edges:
  - target: 30-capture/10-script-extract.md
    when: "script available and Node >= 22 — run the CDP-direct extractor (PRIMARY)"
  - target: 30-capture/90-ocr-fallback.md
    when: "script unavailable (no Node, WebSocket blocked, tab not attachable) — OCR loop (FALLBACK ONLY)"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# Enter part capture loop — script-first

**Before starting:** Record your traversal transition to this node in your session memory bank.

The post page shows stacked thread parts, each as its own `div.xrvj5dj` card with its
own `/post/<partId>` link. **PRIMARY path (validated 2026-09-05): run the
CDP-direct script** — it talks to Chrome over WebSocket, extracts the whole thread
verbatim from the DOM, computes a djb2 hash in-browser, and writes two verified
artifacts. No screenshots, no OCR, no hand-typing.

```
node <skill>/scripts/threads-stitch.mjs "<post URL>" [--out-dir DIR] [--session-id SID]
```

- Auto-matches an open tab by pid; or point explicitly with `--page-idx N` (from the
  script's own type==page listing — NOT MCP pageId).
- Add `--navigate` if no tab is pre-mounted (client-side click/pushState routing).
- **Verification is built-in** — the script prints `count=N len=L hash=H (browser H) blocks=N`.
  A mismatch exits nonzero. `count` must equal the visible part count (`M`); if it is 1
  for a multi-part post, re-check the tab choice.

Only if the script cannot attach at all, use the OCR fallback (next node).
