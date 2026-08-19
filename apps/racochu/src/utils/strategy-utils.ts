const FRONTMATTER_REGEX = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/;

/**
 * Splits frontmatter from body using the standard YAML frontmatter regex.
 * Returns null for frontmatter when none is found.
 */
export function splitFrontmatter(content: string): { frontmatter: string | null; body: string } {
  const match = FRONTMATTER_REGEX.exec(content);
  if (!match) {
    return { frontmatter: null, body: content };
  }
  return {
    frontmatter: match[1],
    body: match[2] || '',
  };
}

const WIKILINK_REGEX = /\[\[([^[\]|#]+)(?:#[^[\]|]*)?(?:\|[^[\]]*)?\]\]/g;

/**
 * Extracts deduplicated wikilink targets from text.
 *
 * Coverage:
 * - `[[Note]]` → `['Note']`
 * - `[[Note|alias]]` → `['Note']`
 * - `[[Note#Section]]` → `['Note']`
 * - `[[Note#Section|alias]]` → `['Note']`
 * - `![[embed]]` → `['embed']`
 * - Deduplicates preserving first-occurrence order
 * - Returns empty array when no wikilinks present
 * - Skips empty brackets `[[ ]]` (trimmed target is empty)
 */
export function extractWikilinks(text: string): string[] {
  const targets = new Set<string>();
  for (const match of text.matchAll(WIKILINK_REGEX)) {
    const target = match[1].trim();
    if (target !== '') {
      targets.add(target);
    }
  }
  return Array.from(targets);
}
