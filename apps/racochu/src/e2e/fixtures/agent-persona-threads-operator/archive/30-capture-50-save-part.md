---
id: 30-capture-50-save-part
title: "Write the part .md file immediately (never hand-type)"
entry: false
conditions:
  - "OCR text extracted and saved to .ocr.md"
veto:
  - "hand-typing Ukrainian or any Cyrillic text from the screenshot"
edges:
  - target: 30-capture/60-check-remaining-parts.md
    when: "part .md written with frontmatter, header, and OCR-sourced content"
created: 2026-09-03
updated: 2026-09-04
status: active
---
# Write the part .md file immediately

**Before starting:** Record your traversal transition to this node in your session memory bank.

Write the captured part to `materials/posts/<rootPostId>/parts/<partPostId>.md` using ONLY OCR-extracted text (never hand-typed). File must include:
- **Frontmatter:** sessionId, agent: threads-operator, createdAt, postId, author, `part: N/M of thread <rootId>`, url
- **Header:** Post: "<first words...>" (Part N/M of thread <rootId>)
- **Engagement info:** like/reply/repost counts from the snapshot
- **Screenshot list:** reference to the saved PNG and .ocr.md files
- **Original text** — verbatim from OCR (e.g., Ukrainian), never transcribed by hand
- **English translation**

After writing, sleep 2–3 seconds before checking for remaining parts.
