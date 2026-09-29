---
id: 30-capture-90-ocr-fallback
title: "OCR loop — FALLBACK ONLY (script could not attach)"
entry: false
conditions:
  - "script cannot attach (no Node >= 22, WebSocket blocked, tab unreachable)"
veto:
  - "using OCR when the script CAN run (script-first is primary; see 10-script-extract.md)"
  - "hand-typing Cyrillic — OCR text or snapshot JSON is the source"
edges:
  - target: 40-aggregate/10-aggregate.md
    when: "all parts 1/M … M/M captured (scroll→screenshot→OCR→save per part) and their .md files exist"
  - target: 60-handoff/10-surface-problem.md
    when: "OCR cannot produce text and snapshot JSON is also unavailable for a needed part"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# OCR loop — fallback only

**Before starting:** Record your traversal transition to this node in your session memory bank.

Only when the CDP-direct script cannot run. Per-part loop, one at a time (never batch):

1. `evaluate_script` scroll one viewport (`window.scrollBy(0, window.innerHeight * 0.9)`), `sleep 1–2`
2. `take_screenshot` → **extract PNG from the JSON tool-response** (`.result.attachments[0].url`
   base64 → PNG beside it), copy to `materials/screenshots/`
3. OCR each part (`hugging-xberg-extract_bytes`) → save `.ocr.md`; on OCR fail, use
   `take_snapshot` a11y text
4. Write `materials/posts/<rootPostId>/parts/<partPostId>.md` (frontmatter + verbatim text + EN translation)

The full OCR procedure (screenshot JSON→PNG extraction, part `.md` format) is archived at
`archive/30-capture-*.md` in this persona's folder — read those when the fallback is active.
