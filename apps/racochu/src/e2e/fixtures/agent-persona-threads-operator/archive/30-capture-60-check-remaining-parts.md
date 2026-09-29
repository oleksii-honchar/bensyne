---
id: 30-capture-60-check-remaining-parts
title: "Check for remaining parts — loop or exit capture"
entry: false
conditions:
  - "just-completed part .md written (N/M of thread <rootId>)"
veto:
  - "scraping past the last M/M part (overflow into unrelated content)"
edges:
  - target: 30-capture/10-capture-loop-entry.md
    when: "more parts remain to capture (M/N not yet reached final part)"
  - target: 40-aggregate/10-aggregate.md
    when: "all parts 1/M … M/M have been captured and their .md files exist"
created: 2026-09-03
updated: 2026-09-04
status: active
---
# Check for remaining parts — loop or exit capture

**Before starting:** Record your traversal transition to this node in your session memory bank.

After completing a part (scroll → screenshot → OCR → save), check whether more parts remain by scrolling down and looking for additional N / M badges on the thread page. If another part exists in the stack, return to the capture loop entry (scroll to bring it into view). If this was the final part (M/M), exit the capture loop and proceed to stitching. **Sanity check:** verify that all expected parts 1/M through M/M have corresponding `.md` files in `materials/posts/<rootPostId>/parts/` before proceeding.
