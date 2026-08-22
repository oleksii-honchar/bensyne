/**
 * Base64 blob guard (ReDoS prevention).
 *
 * mnemosyne's fact-extractor regex catastrophically backtracks (ReDoS) on long
 * whitespace-free mixed-case letter runs with no version number. Whole-file
 * base64 blobs (e.g. `{"result":"<base64>"}` or a bare base64 string) are a
 * real-world trigger that hangs the ingest pipeline. This module detects such
 * whole-file base64 blobs so the caller can replace their content with a
 * placeholder before it ever reaches mnemosyne.
 *
 * Detection is intentionally conservative: a file is flagged only when its
 * ENTIRE trimmed content is a base64 blob (pure, or a single-field JSON
 * envelope). Normal prose, markdown, multi-key JSON, and partial base64
 * (interspersed with other text/whitespace) are NOT flagged.
 *
 * The guard never decodes or partially sanitizes — it either replaces the whole
 * content with a placeholder or leaves it untouched.
 */

/** Pure base64 charset + up to two trailing padding characters. */
const PURE_BASE64_REGEX = /^[A-Za-z0-9+/]+={0,2}$/;

/** Minimum base64 length (chars) to be considered a whole-file blob. */
const MIN_BASE64_LENGTH = 64;

/**
 * Checks whether a string is a pure base64 token of at least MIN_BASE64_LENGTH
 * characters. The input must be already trimmed by the caller.
 */
function isPureBase64(text: string): boolean {
  if (text.length < MIN_BASE64_LENGTH) {
    return false;
  }
  return PURE_BASE64_REGEX.test(text);
}

/**
 * Returns true when the given content's trimmed form is a whole-file base64 blob.
 *
 * Matches either:
 * 1. Pure base64 — the entire trimmed content is base64 (≥ 64 chars), OR
 * 2. Single-field envelope — the trimmed content is a JSON object with exactly
 *    one key whose value is a base64 string (≥ 64 chars).
 */
export function isBase64Blob(content: string): boolean {
  const trimmed = content.trim();

  // Rule 1: pure base64.
  if (isPureBase64(trimmed)) {
    return true;
  }

  // Rule 2: single-field base64 envelope (fast reject before parsing).
  if (trimmed.length >= 2 && trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed)) {
        const entries = Object.entries(parsed as Record<string, unknown>);
        if (entries.length === 1) {
          const [key, value] = entries[0];
          // Guard against JSON keys like "__proto__" leaking onto Object.prototype.
          const isOwnKey = Object.prototype.hasOwnProperty.call(parsed, key);
          if (isOwnKey && typeof value === 'string' && isPureBase64(value)) {
            return true;
          }
        }
      }
    } catch {
      // Not valid JSON — not a blob by this rule.
    }
  }

  return false;
}

/**
 * Result of guarding a file's content for base64 blobs.
 */
export interface Base64GuardResult {
  /**
   * The content to use downstream: the original content when nothing was
   * detected, or a short placeholder when a whole-file base64 blob was found.
   */
  content: string;
  /** True only when the content was detected as a base64 blob and replaced. */
  sanitized: boolean;
}

/**
 * Builds the placeholder string that replaces a detected base64 blob.
 */
function buildPlaceholder(content: string): string {
  return `[base64 content omitted: ${content.length} bytes]`;
}

/**
 * Replaces a whole-file base64 blob's content with a placeholder so it never
 * reaches mnemosyne (ReDoS trigger). Non-blobs are returned unchanged.
 *
 * Pure and side-effect free — safe to unit test in isolation.
 */
export function guardBase64Content(content: string): Base64GuardResult {
  if (isBase64Blob(content)) {
    return { content: buildPlaceholder(content), sanitized: true };
  }
  return { content, sanitized: false };
}
