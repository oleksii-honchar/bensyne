/**
 * Identity-only metadata extracted from a session.md frontmatter.
 * Used by the AgentSessionChunkingStrategy to enrich chunks with session context.
 *
 * Live session state (status, phase, nextAgent) is NOT metadata here — it lives in
 * history.jsonl, the single source of truth for session state.
 */
export interface SessionMetadata {
  sessionId: string; // Platform session ID (e.g., ses_057e2d847ffeJkvVN1hTxIim8L)
  createdAt: string; // Session creation timestamp
}
