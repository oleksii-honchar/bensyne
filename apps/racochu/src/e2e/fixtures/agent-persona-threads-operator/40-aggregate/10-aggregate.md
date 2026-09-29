---
id: 40-aggregate-10-aggregate
title: "Aggregate — build the reading-friendly post document from script output"
entry: false
conditions:
  - "script succeeded (stitched-post-<rootId>.txt + data-threads-spans-<rootId>.json) OR all OCR fallback part .mds exist"
veto:
  - "aggregating with any missing part .md files (partial thread is an incomplete record)"
  - "stitching refs-only (parts index table without each part's verbatim text inline)"
edges:
  - target: 50-verify/10-verify-completeness.md
    when: "context.md created successfully with ALL M parts' verbatim content stitched in order"
created: 2026-09-03
updated: 2026-09-04
status: active
---
# Build the reading-friendly post document (from script output)

**Before starting:** Record your traversal transition to this node in your session memory bank.

**PRIMARY (script path):** the script already produced `stitched-post-<rootId>.txt`
(all parts verbatim, doc order) + `data-threads-spans-<rootId>.json`. When the caller
wants the reading-friendly aggregate (UA + EN), build it FROM that stitched text —
never re-OCR, never hand-type.

**Fallback (OCR path):** stitch per-part `.md`s as before (read EVERY part file in
order, embed verbatim UA + EN inline). Storage layout (per-post folder):

```
materials/posts/<rootPostId>/
  parts/<partPostId>.md   ← already written during capture
  context.md              ← THIS final stitched document (write now)
```

Steps:
1. `mkdir -p materials/posts/<rootPostId>` (folder already holds `parts/` and screenshots)
2. Read EVERY part file `parts/<partPostId>.md` for parts 1/M … M/M **in order**, extracting each part's verbatim original text (UA) and English translation.
3. Write `materials/posts/<rootPostId>/context.md` containing:
- **Frontmatter:** sessionId, agent: threads-operator, createdAt, postId (root), author, `thread: M parts`
- **Header block:** root URL, view count, root engagement (Like/Reply/Repost totals)
- **Parts index table:** one row per part, with N/M, part post ID, short title (first words), link to `parts/<partPostId>.md`
- **ALL parts' content stitched inline, in order 1/M … M/M:** for each part, `### Part N/M — <short title>` followed by the part's **verbatim original text** (UA) and **English translation** — actual text lifted from each part file, NOT links/refs. No part is dropped; only the root part inline is NOT acceptable (see veto).
- **Thread replies (if captured):** any visible reply content added below the parts.
- Reference to the canonical flow at the bottom of the file

Result: `context.md` is the single read-the-whole-post document; `parts/` retains source-of-truth per part.
