/**
 * Metadata extracted from a session.md frontmatter.
 * Used by the AgentSessionChunkingStrategy to enrich chunks with session context.
 */
export interface SessionMetadata {
  sessionId: string; // Platform session ID (e.g., ses_057e2d847ffeJkvVN1hTxIim8L)
  createdAt: string; // Session creation timestamp
  status: string; // Current session status
  phase: string; // Current session phase
  nextAgent: string; // Next agent in the workflow
}
