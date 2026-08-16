import { Injectable } from '@nestjs/common';
import { ContentChunk } from '../../domain/content-chunk.entity';
import { EnhancementConfig } from '../../infrastructure/config/config-schemas';

const STOPWORDS = new Set([
  'the',
  'a',
  'an',
  'is',
  'it',
  'in',
  'on',
  'at',
  'to',
  'for',
  'of',
  'and',
  'or',
  'but',
  'not',
  'this',
  'that',
  'was',
  'are',
  'were',
  'be',
  'has',
  'have',
  'had',
  'do',
  'does',
  'did',
  'will',
  'would',
  'could',
  'should',
  'may',
  'might',
  'must',
  'can',
  'his',
  'her',
  'their',
  'our',
  'your',
  'my',
  'with',
  'from',
  'by',
  'as',
  'about',
  'into',
  'through',
  'during',
  'before',
  'after',
  'above',
  'below',
  'between',
  'among',
  'upon',
]);

/**
 * Rule-based tag extraction service for chunks.
 * Extracts tags from chunk content using keyword patterns and metadata.
 * Never throws — always produces a valid tag array.
 */
@Injectable()
export class TagExtractionService {
  /**
   * Extract tags from a chunk based on configured rules.
   * If tagging is disabled, returns empty array.
   */
  extract(chunk: ContentChunk, config: EnhancementConfig): string[] {
    const tagsConfig = config.tags;

    if (!tagsConfig?.enabled) {
      return [];
    }

    const maxTags = tagsConfig.maxTags ?? 10;
    const allTags = new Set<string>();

    // Stage 1: File-type tag
    const fileTypeTag = this.extractFileTypeTag(chunk);
    if (fileTypeTag) {
      allTags.add(fileTypeTag);
    }

    // Stage 2: Location tag
    const locationTag = this.extractLocationTag(chunk);
    if (locationTag) {
      allTags.add(locationTag);
    }

    // Stage 3: Keyword extraction from text
    const keywordTags = this.extractKeywordTags(chunk.text);
    for (const tag of keywordTags) {
      allTags.add(tag);
    }

    // Stage 4: Metadata tags from Mastra keywords
    const metadataTags = this.extractMetadataTags(chunk.metadata);
    for (const tag of metadataTags) {
      allTags.add(tag);
    }

    // Enforce maxTags with priority:
    // keywords > metadata > location > file-type
    const tagsArray = Array.from(allTags);
    return this.enforceMaxTags(tagsArray, maxTags);
  }

  /**
   * Extract file-type tag from chunk language or metadata extension.
   * Format: "file-type:{type}"
   */
  private extractFileTypeTag(chunk: ContentChunk): string | null {
    const type = chunk.language ?? chunk.metadata?.extension;
    if (!type || type.trim() === '') {
      return null;
    }
    return `file-type:${type.trim().toLowerCase()}`;
  }

  /**
   * Extract location tag from chunk memory bank.
   * Format: "location:{memoryBank}"
   */
  private extractLocationTag(chunk: ContentChunk): string | null {
    const memoryBank = chunk.memoryBank;
    if (!memoryBank || memoryBank.trim() === '') {
      return null;
    }
    return `location:${memoryBank}`;
  }

  /**
   * Extract significant keywords from chunk text.
   * Filters stopwords and short words, returns first 5 unique words.
   */
  private extractKeywordTags(text: string): string[] {
    if (!text || text.trim() === '') {
      return [];
    }

    // Split on non-alphanumeric characters, filter and deduplicate
    const words = text
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, ' ')
      .split(/\s+/);
    const seen = new Set<string>();
    const result: string[] = [];

    for (const word of words) {
      if (result.length >= 5) {
        break;
      }
      if (word.length < 4) {
        continue;
      }
      if (STOPWORDS.has(word)) {
        continue;
      }
      if (seen.has(word)) {
        continue;
      }
      seen.add(word);
      result.push(word);
    }

    return result;
  }

  /**
   * Extract tags from Mastra keywords metadata.
   * Supports comma, semicolon, pipe, and space separators.
   */
  private extractMetadataTags(metadata: Record<string, string> | undefined): string[] {
    if (!metadata || !metadata.keywords) {
      return [];
    }

    const keywords = metadata.keywords;
    if (!keywords.trim()) {
      return [];
    }

    // Split on common separators: comma, semicolon, pipe, and spaces
    const tags = keywords
      .split(/[;,|]+/)
      .map(t => t.trim().toLowerCase())
      .filter(t => t.length > 0);

    return tags;
  }

  /**
   * Enforce maxTags limit with priority order.
   * Truncation order (dropped first to last): metadata tags → keyword tags → location tag → file-type tag
   * This means file-type and location tags have the highest priority and are preserved first.
   */
  private enforceMaxTags(tags: string[], maxTags: number): string[] {
    if (tags.length <= maxTags) {
      return tags;
    }

    // Categorize tags by priority (for truncation)
    const keywordTags: string[] = [];
    const locationTags: string[] = [];
    const fileTypeTags: string[] = [];

    for (const tag of tags) {
      if (tag.startsWith('file-type:')) {
        fileTypeTags.push(tag);
      } else if (tag.startsWith('location:')) {
        locationTags.push(tag);
      } else {
        // All other tags are keywords or metadata-derived (same truncation priority)
        keywordTags.push(tag);
      }
    }

    // Build result: add highest-priority tags FIRST so they're always preserved
    // file-type and location are added first, keywords fill remaining space
    const result: string[] = [];

    // Add file-type tags first (highest priority — always preserved if possible)
    for (const tag of fileTypeTags) {
      if (result.length >= maxTags) break;
      result.push(tag);
    }

    // Add location tags (second highest priority)
    for (const tag of locationTags) {
      if (result.length >= maxTags) break;
      result.push(tag);
    }

    // Add keyword tags last (lowest priority — dropped first if over limit)
    for (const tag of keywordTags) {
      if (result.length >= maxTags) break;
      result.push(tag);
    }

    return result;
  }
}
