---
id: 30-capture-10-script-extract
title: "Run the CDP-direct extractor and verify output"
entry: false
conditions:
  - "post page mounted and script available (skills/social-networks-navigator/scripts/threads-stitch.mjs)"
veto:
  - "proceeding before the script exits cleanly with a djb2 MATCH (browser hash == node hash)"
  - "hand-transcribing any block from the terminal (the script's .txt/.json ARE the artifact)"
edges:
  - target: 40-aggregate/10-aggregate.md
    when: "script printed count=N len=L hash=H (browser H) blocks=N with MATCH and N == expected part count"
  - target: 60-handoff/10-surface-problem.md
    when: "script errors ('no opener card', hash mismatch, navigation did not settle) — surface and re-run/adjust"
created: 2026-09-05
updated: 2026-09-05
status: active
---
# Run the CDP-direct extractor and verify output

**Before starting:** Record your traversal transition to this node in your session memory bank.

Run the script against the mounted post page. It writes (together):

- `stitched-post-<rootId>.txt` — full verbatim thread text, doc order
- `data-threads-spans-<rootId>.json` — metadata + per-block records

**Built-in integrity:** the browser computes a djb2 hash + base64 of the stitched text;
the script decodes locally, recomputes the hash, and prints
`count=N len=L hash=H (browser H) blocks=N`. Verify:

1. The line shows `(browser H)` == `H` (MATCH).
2. `N` (blocks) == the part count `M` from the `N / M` badges.
3. The `.txt` is full length `L` and readable (spot-check first/last block).

If the script reports `count=1` for a visible multi-part post — a wrong tab was used
(`--page-idx` from the script's own listing), or the opener wasn't the target. Do NOT
fall through to OCR just because a run failed; fix the tab/url and re-run. Only when the
script CANNOT attach at all (no Node, WebSocket blocked) do you use the OCR fallback.
