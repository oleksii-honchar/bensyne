---
id: 30-capture-90-ocr-fallback
title: "OCR failed — use snapshot JSON as text source instead"
entry: false
conditions:
  - "screenshot taken but OCR returned 'no text' or timed out"
veto: []
edges:
  - target: 30-capture/50-save-part.md
    when: "snapshot/JSON verbatim text available as fallback (proceed with part writing)"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# OCR failed — use snapshot JSON as text source instead

**Before starting:** Record your traversal transition to this node in your session memory bank.

OCR returned "no text" or timed out (common with small local VLM). This does NOT block progress. Use `take_snapshot` (a11y tree) from the chrome-debug instance as the primary text source for the part content. The screenshot remains saved as the visual record only. Proceed to write the part .md file using the snapshot-extracted text instead of OCR.
