---
id: 50-verify-20-sanity-check
title: "Sanity check and close"
entry: false
conditions:
  - "script extraction verified (hash MATCH, N == M) or OCR .mds + aggregate present"
veto:
  - "closing on an unverified extraction (no hash MATCH in script mode)"
edges:
  - target: 60-handoff/10-surface-problem.md
    when: "completeness verified — surface results to the user for confirmation"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# Sanity check and close

**Before starting:** Record your traversal transition to this node in your session memory bank.

Confirm the thread was fully and correctly extracted before presenting:

- **Script path:** `count=N` matches part count `M`; djb2 hash MATCH (`browser H` == `H` in
  the run line, or node recompute matches); `stitched-post-<rootId>.txt` is full length `L`
  and readable (spot-check first + last block). The `.txt` + `.json` are the artifacts.
- **OCR fallback path:** all `parts/*.md` for 1/M..M/M, screenshots, and aggregate present.

Present to the user: thread part count, files written (`stitched-post-<rootId>.txt`,
`data-threads-spans-<rootId>.json`, optional aggregate `.md`), the verified hash, and any
notes (truncation, unavailable tab, fallback used).
