---
type: decision
id: DEC-0080
system: bensyne-mcp
title: "Read-Only getFileChunks MCP Tool for Chunk Verification"
status: accepted
createdAt: "2026-08-26T07:18:26Z"
updatedAt: "2026-08-31T14:57:53Z"
tags: [recover, mcp-tool, verification, read-only, file-chunks]
supersedes: []
superseded_by: []
see_also:
  - decisions/0106-getfilechunks-observability-only.decision.md
  - decisions/0084-recover-hash-gate-chunk-set-check.decision.md
  - decisions/0085-recover-memory-status-point-reads.decision.md
  - decisions/0048-dual-hash-wire-contract.decision.md
  - concepts/0001-hash-index.concept.md
  - concepts/0006-file-chunk-relation.concept.md
  - specifications/0007-racochu-recover-mode.spec.md
---

# DEC-0080: Read-Only getFileChunks MCP Tool for Chunk Verification

## Context

Racochu recover needs a zero-LLM, state-accurate "what chunks are stored for file X" surface.
The only existing verification primitive, `rememberMemory`, proceeds to save + embedding on a
hash miss — unusable as a probe. `fetchFile` composes content via N `mnemosyne.get` calls
(heavy, content transfer). The local `FileMemoryTracker` cannot detect partial chunk loss.

## Decision

Add a read-only MCP tool `getFileChunks(file_path, memory_bank)` to bensyne-mcp. It derives
`file_id = derive_file_id(bank, path)` locally (`file_{sha256("bank:path")[:32]}`, deterministic),
reads the `files` row and `file_chunks` rows (pure SQLite — no mnemosyne, no embedding, no
writes), and returns `{status, file_id, file_hash, total_chunks, chunks:[{chunk_index,
content_hash, memory_id, memory_status}]}`. Racochu consumes it via `BensyneClient.getFileChunks()`
(`status: "FILE_NOT_FOUND"` is a business state, parsed as `Result.ok`, not a transport error).

## Alternatives Considered

- `fetchFile(file_id, include_metadata=true)` — zero LLM but N mnemosyne round-trips + full
  content transfer; kept as fallback (injectable stored-chunk reader).
- `rememberMemory` as probe — rejected: hash miss triggers embedding + state mutation.
- Local-only check (what `--resume` does) — rejected: cannot verify chunk completeness.

## Consequences

- Verification path is zero-LLM: one MCP round-trip + N cheap point reads per file.
- Requires a bensyne-mcp deployment with the new tool; missing tool must abort recover loudly.
- Additive — no existing tool changes; wire contract snake_case (DEC-0048).
- 2026-08-31: a WARNING log (`"getFileChunks: file row not found"` with `memory_bank`, `file_path`, `derived_file_id`) fires on missing rows — response contract remains byte-identical (DEC-0107).
