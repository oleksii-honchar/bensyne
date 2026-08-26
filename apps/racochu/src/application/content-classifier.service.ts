// Content classifier — pure heuristics for detecting machine-generated dump
// files (git merge-tree output, diff dumps, base64 blobs, etc.) that should
// never be chunked or enriched.
//
// Path-based `exclude` globs cannot catch this class of file, so ingestion
// gates run this sniffer on the raw content BEFORE chunking. It is deliberately
// cheap: a single regex + length scan over the lines, plus a token-diversity
// pass. No LLM, no DI, no logger, no fs access — pure functions only
// (mirrors glob-matcher.ts).

export interface ContentFilterOptions {
  // Master switch — when false every trigger below is ignored.
  enabled?: boolean;
  // Any single line longer than this (chars) triggers immediately.
  maxLineLength?: number;
  // Lines longer than this (chars) count toward the long-line ratio.
  longLineChars?: number;
  // Max allowed ratio of longLineChars-exceeding lines to total lines.
  longLineRatio?: number;
  // Regex source strings matched line-by-line (git-diff/merge-tree markers).
  markerPatterns?: string[];
  // Max allowed ratio of marker-matched lines to total lines.
  markerRatio?: number;
  // Min unique/total token ratio; below this triggers.
  minTokenDiversity?: number;
}

export interface ContentClassification {
  filtered: boolean;
  reasons: string[];
}

export const DEFAULT_CONTENT_FILTER_OPTIONS: Required<ContentFilterOptions> = {
  enabled: true,
  maxLineLength: 100_000,
  longLineChars: 10_000,
  longLineRatio: 0.001,
  markerPatterns: [
    '^diff --git',
    '^@@ -\\d+,\\d+ \\+\\d+,\\d+ @@',
    '^index [0-9a-f]{7,}\\.\\.[0-9a-f]{7,}',
    'added in remote',
    '(?:their|our) \\d{6}',
  ],
  markerRatio: 0.05,
  minTokenDiversity: 0.1,
};

const LINE_SPLIT = /\r?\n/;
const WHITESPACE_SPLIT = /\s+/;

// Classify raw content with the configured heuristics. Any single trigger
// marks the content as filtered and reports the matching reason strings.
// Deterministic: identical input + options always yields identical output.
// Empty/whitespace-only content is never filtered (handled elsewhere).
export const classifyContent = (content: string, options?: ContentFilterOptions): ContentClassification => {
  const opts: Required<ContentFilterOptions> = {
    ...DEFAULT_CONTENT_FILTER_OPTIONS,
    ...options,
    markerPatterns: options?.markerPatterns ?? DEFAULT_CONTENT_FILTER_OPTIONS.markerPatterns,
  };

  if (!opts.enabled) {
    return { filtered: false, reasons: [] };
  }
  if (content.trim() === '') {
    return { filtered: false, reasons: [] };
  }

  const reasons: string[] = [];
  const lines = content.split(LINE_SPLIT);
  const totalLines = lines.length;

  // Long-line: any single line above maxLineLength.
  let longestLine = 0;
  for (const line of lines) {
    if (line.length > longestLine) {
      longestLine = line.length;
    }
  }
  if (longestLine > opts.maxLineLength) {
    reasons.push(
      `long-line: single line of ${longestLine} chars exceeds maxLineLength (${opts.maxLineLength})`,
    );
  }

  // Long-line ratio: share of lines longer than longLineChars.
  let longLineCount = 0;
  for (const line of lines) {
    if (line.length > opts.longLineChars) {
      longLineCount += 1;
    }
  }
  const longLineRatio = totalLines > 0 ? longLineCount / totalLines : 0;
  if (longLineRatio > opts.longLineRatio) {
    reasons.push(
      `long-line: ${longLineCount}/${totalLines} lines exceed longLineChars (${opts.longLineChars}); ratio ${longLineRatio} > ${opts.longLineRatio}`,
    );
  }

  // Machine-marker regexes: share of lines matching any pattern.
  const markerRegexes = opts.markerPatterns.map(pattern => new RegExp(pattern));
  let markerLineCount = 0;
  for (const line of lines) {
    if (markerRegexes.some(regex => regex.test(line))) {
      markerLineCount += 1;
    }
  }
  const markerRatio = totalLines > 0 ? markerLineCount / totalLines : 0;
  if (markerRatio > opts.markerRatio) {
    reasons.push(
      `marker: ${markerLineCount}/${totalLines} lines match machine markers; ratio ${markerRatio} > ${opts.markerRatio}`,
    );
  }

  // Token diversity: unique whitespace-delimited tokens / total tokens.
  const tokens = content.split(WHITESPACE_SPLIT).filter(token => token !== '');
  const uniqueTokenCount = new Set(tokens).size;
  const tokenDiversity = tokens.length > 0 ? uniqueTokenCount / tokens.length : 0;
  if (tokenDiversity < opts.minTokenDiversity) {
    reasons.push(
      `diversity: ${uniqueTokenCount}/${tokens.length} unique tokens; ratio ${tokenDiversity} < ${opts.minTokenDiversity}`,
    );
  }

  return reasons.length > 0 ? { filtered: true, reasons } : { filtered: false, reasons: [] };
};
