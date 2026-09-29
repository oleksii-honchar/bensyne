---
id: 30-capture-40-ocr
title: "OCR screenshot and save OCR result"
entry: false
conditions:
  - "screenshot PNG extracted and saved to materials/screenshots/"
veto:
  - "hand-typing any Cyrillic/Cyrillic-equivalent text (OCR or snapshot JSON only)"
edges:
  - target: 30-capture/50-save-part.md
    when: "OCR completed successfully with extractable text"
  - target: 30-capture/90-ocr-fallback.md
    when: "OCR returned 'no text' or timed out (snapshot JSON is fallback text source)"
created: 2026-09-03
updated: 2026-09-03
status: active
---
# OCR screenshot and save OCR result

**Before starting:** Record your traversal transition to this node in your session memory bank.

Run the HuggingFace VLM on the extracted PNG: `hugging-xberg-extract_bytes(data: "<abs path PNG>", response_format: "markdown")`. One screenshot may show several parts stacked — split by N / M badges. If multiple parts appear, note which each OCR section corresponds to before proceeding. **Store raw OCR to disk**: create `materials/screenshots/<partId>-part<N>-<seq>.ocr.md` with frontmatter (source, ocrTool, sessionId, agent, createdAt) and body = verbatim OCR text.
