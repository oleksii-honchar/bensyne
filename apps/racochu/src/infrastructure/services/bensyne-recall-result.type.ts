/**
 * A single recall result as returned by the bensyne `recallMemory` MCP tool.
 *
 * The base shape mirrors today's mnemosyne pass-through (`content` is the
 * memory text). Bensyne may additively extend each result with a
 * `file_enrichment` block (file metadata, relations, summary chain, traversal
 * handles — see bensyne FileEnrichmentService / spec §2.1). Racochu does NOT
 * own or parse that shape: it is an opaque passthrough (`unknown | null`,
 * never `any`). Absent key ⇒ undefined; pure memories ⇒ null from bensyne.
 */
export interface BensyneRecallResult {
  content: string;
  /**
   * Additive, bensyne-owned enrichment block (Task 13 / S6 tolerance).
   * - absent (key not present) ⇒ `undefined` — pre-enrichment responses map byte-identical
   * - `null` — pure memory with no file context (bensyne Phase 3 contract)
   * - object — file-based memory; shape owned by bensyne, passed through untouched
   */
  file_enrichment?: unknown | null;
}
