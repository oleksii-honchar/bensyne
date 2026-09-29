---
id: 50-verify-10-verify-completeness
title: "Verify — integrity (script path) or file inventory (OCR fallback)"
entry: false
conditions:
  - "script outputs exist (stitched-post-<rootId>.txt + data-threads-spans-<rootId>.json), or OCR part .mds exist"
veto:
  - "accepting a script run whose printed djb2 did NOT match (browser H == node H)"
  - "closing with a partial thread (script N != part count M, or fallback .md files missing)"
edges:
  - target: 50-verify/20-sanity-check.md
    when: "script MATCH and N == M, or all OCR part .mds present AND aggregate stitched all parts"
  - target: 60-handoff/10-surface-problem.md
    when: "hash mismatch / N != M / any part file missing — surface, don't close"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# Verify — check integrity of the extraction

**Before starting:** Record your traversal transition to this node in your session memory bank.

**Script path (primary):** confirm the run line
`count=N len=L hash=H (browser H) blocks=N` has `browser H == H` (MATCH) and
`N == M` (part count from the badges). Byte-compare `stitched-post-<rootId>.txt`
against the canonical if re-running; recompute djb2:

```bash
node -e 'const fs=require("fs");const s=fs.readFileSync("stitched-post-<rootId>.txt","utf8");let x=5381;for(const c of Buffer.from(s,"utf8"))x=((x*33)^c)>>>0;console.log(x)'
```

**OCR fallback path:** verify each `materials/posts/<rootPostId>/parts/<partPostId>.md`
exists for N/M 1..M, plus the stitched aggregate. Missing file or dropped part = failure.
