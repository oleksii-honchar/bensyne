import { z } from 'zod';

import { ValuesType } from '@/utils/values-type';

/**
 * D29 source-type value axis (spec §6.6): the real producers.
 * Strategy ≡ source type — a watch source's `sourceType` field IS its source type,
 * and the chunking layer is a `source_type → chunker` router.
 *
 * TS mirror of bensyne's `SourceType` minus the wire-side fallback: `unknown` is
 * the degrade-never-reject marker (`SOURCE_TYPE_UNKNOWN` below), present in the
 * contract for that reason only — never a configured watch-source value.
 *
 * Cross-app 1:1 lock (spec §14.11): bensyne asserts `set(SourceType) ==
 * {obsidian, agent-sessions, vault, unknown}`; this app asserts
 * `Object.values(SOURCE_TYPES) == [obsidian, agent-sessions, vault]`.
 */
export const SOURCE_TYPES = {
  OBSIDIAN: 'obsidian',
  AGENT_SESSIONS: 'agent-sessions',
  VAULT: 'vault',
} as const;

export type SourceType = ValuesType<typeof SOURCE_TYPES>;

/** D29 wire-side degrade marker — fallback only (bensyne `_coerce_source_type` semantics). */
export const SOURCE_TYPE_UNKNOWN = 'unknown';

/**
 * The canonical 4-value wire axis: `obsidian | agent-sessions | vault | unknown`.
 * Exactly the value set bensyne's `SourceType` accepts — what racochu sends is
 * exactly what bensyne accepts (D29: no legacy/unknown wire values ship).
 */
export const sourceTypeSchema = z.enum([
  SOURCE_TYPES.OBSIDIAN,
  SOURCE_TYPES.AGENT_SESSIONS,
  SOURCE_TYPES.VAULT,
  SOURCE_TYPE_UNKNOWN,
]);

export type WireSourceType = z.infer<typeof sourceTypeSchema>;
