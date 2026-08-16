/**
 * Metadata extracted from an Obsidian note frontmatter.
 * Used by the ObsidianChunkingStrategy to enrich chunks with note context.
 */
export interface NoteMetadata {
  aliases: string[]; // Obsidian note aliases
  tags: string[]; // Obsidian note tags
  created: string; // Note creation date
  modified: string; // Note modification date
  source: string; // Note source
  status: string; // Note status
  type: string; // Note type
  /** Raw frontmatter `base:` value */
  base: string;
  /** All remaining frontmatter keys, lowercased, stringified */
  properties: Record<string, string>;
}
