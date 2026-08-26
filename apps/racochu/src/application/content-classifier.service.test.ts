import {
  classifyContent,
  DEFAULT_CONTENT_FILTER_OPTIONS,
} from './content-classifier.service';

// Representative excerpt of the REAL problem file
// (`/Users/oleksii.honchar/.agent-sessions/26/07/07/260707-1033-fork-upgrade-plan/materials/merge-tree-output.txt`):
// a `git merge-tree` dump — 28,570 lines, a single ~1.8 MB line, and hundreds
// of `added in remote` / `their  100644` / `@@ -0,0 +1,N @@` markers — that was
// ingested as 858 chunks. This fixture is the first 60 lines of that file:
// 4 of 60 lines (6.7%) match the marker patterns, above the 5% marker ratio.
const MERGE_TREE_EXCERPT = [
  'added in remote',
  '  their  100644 57d0e502d5855bd14208313fa99a4cecac1faeee .vault/_Vault-Home.md',
  '@@ -0,0 +1,20 @@',
  '+---',
  '+type: index',
  '+title: "Vault Home"',
  '+createdAt: "2026-06-08T18:32:00Z"',
  '+updatedAt: "2026-06-10T20:00:00Z"',
  '+tags: []',
  '+---',
  '+',
  '+# Vault Home',
  '+',
  '+This vault captures durable knowledge about the better-opencode project — a fork of OpenCode with patches, custom configurations, and development changes. Use the indexes below to navigate decisions, concepts, specifications, architecture, runbooks, and atomic memories.',
  '+',
  '+## Indexes',
  '+',
  '+- [[adrs/_index]] — Architecture Decision Records',
  '+- [[concepts/_index]] — Domain Concepts',
  '+- [[specifications/_index]] — Specifications',
  '+- [[architectures/_index]] — Architecture Maps (C4)',
  '+- [[runbooks/_index]] — Operational Runbooks',
  '+- [[memories/_index]] — Atomic Memories',
  'added in remote',
  '  their  100644 57185caea5ee8e8903411d81bd7e959b6159370b .vault/adrs/0001-system-prompt-persistence.adr.md',
  '@@ -0,0 +1,158 @@',
  '+---',
  '+type: adr',
  '+id: ADR-0001',
  '+title: "Persist System Prompt in Session Database"',
  '+status: proposed',
  '+createdAt: "2026-06-08T21:00:00Z"',
  '+updatedAt: "2026-06-08T21:00:00Z"',
  '+tags: [system-prompt, persistence, database, session-storage]',
  '+see_also:',
  '+  - "architectures/better-opencode/components/0001-session-storage.component.md"',
  '+  - "concepts/0002-system-prompt.concept.md"',
  '+  - "concepts/0001-session-model.concept.md"',
  '+---',
  '+',
  '+# ADR-0001: Persist System Prompt in Session Database',
  '+',
  '+## Context',
  '+',
  '+The system prompt in better-opencode is composed at runtime and injected as part of the LLM API request. It is **never stored** in the SQLite database — only user and assistant messages are persisted.',
  '+',
  '+This creates limitations:',
  '+- The system prompt is invisible in session history / UI',
  '+- Sessions cannot be replayed with their original system prompt',
  '+- Session export is incomplete (missing the system prompt)',
  '+',
  '+### Current State',
  '+',
  '+| Content | Persisted? | How |',
  '+|---------|-----------|-----|',
  '+| Full system prompt | **No** | Runtime-only, injected at LLM request time |',
  '+| User messages | Yes | `messages` table, role=user |',
  '+| Assistant messages | Yes | `messages` table, role=assistant |',
  '+| `User.system` field | Yes (but limited) | As `system` field in `MessageTable.data` JSON — only stores the user-provided system text, not the full composed prompt |',
  '+| Injected system messages (tool hooks) | Yes | As **user** messages wrapped in `<system-reminder>` tags |',
].join('\n');

const MARKDOWN_FIXTURE = [
  '# Project Notes',
  '',
  'This is a normal markdown document with varied content for the classifier.',
  '',
  '## Section',
  '',
  '- bullet one',
  '- bullet two',
  '',
  'A final paragraph with enough unique tokens to pass every heuristic check.',
].join('\n');

const TYPESCRIPT_FIXTURE = [
  'export interface User {',
  '  id: string;',
  '  name: string;',
  '}',
  '',
  'export const greet = (user: User): string => {',
  "  return 'Hello, ' + user.name;",
  '};',
  '',
  'export const count = (items: string[]): number => items.length;',
].join('\n');

const PROSE_FIXTURE = [
  'The quick brown fox jumps over the lazy dog near the riverbank.',
  'Every morning the gardener waters the tulips and trims the hedges.',
  'The committee reviewed the proposal carefully before approving the budget.',
  'Scientists study the climate records to predict next seasons weather.',
  'A well-written paragraph contains varied vocabulary and clear sentences.',
].join('\n');

// 1000 lines where exactly one line is 150_000 chars: the long-line *ratio*
// is 1/1000 = 0.001 which does NOT exceed the default 0.001, so only the
// maxLineLength trigger can fire. Filler lines stay token-diverse so the
// diversity heuristic cannot fire either.
const LONG_LINE_CONTENT = [
  'x'.repeat(150_000),
  ...Array.from({ length: 999 }, (_, i) => `line number ${i}`),
].join('\n');

// 100 lines where 6 lines are git-diff hunk headers: marker ratio 6% > 5%.
const MARKER_CONTENT = [
  ...Array.from({ length: 94 }, (_, i) => `regular prose line number ${i}`),
  ...Array.from({ length: 6 }, () => '@@ -0,0 +1,20 @@'),
].join('\n');

// Repetitive token stream: 2 unique tokens out of 1000 → diversity 0.002.
const LOW_DIVERSITY_CONTENT = Array.from(
  { length: 500 },
  () => 'alpha beta',
).join(' ');

describe('content-classifier', () => {
  describe('real-world fixture (git merge-tree dump excerpt)', () => {
    it('filters a representative excerpt of merge-tree-output.txt with default options', () => {
      const result = classifyContent(MERGE_TREE_EXCERPT);
      expect(result.filtered).toBe(true);
      expect(result.reasons.some(reason => reason.startsWith('marker:'))).toBe(true);
    });

    it('is deterministic — identical input yields identical output', () => {
      const first = classifyContent(MERGE_TREE_EXCERPT);
      const second = classifyContent(MERGE_TREE_EXCERPT);
      expect(first).toEqual(second);
    });
  });

  describe('long-line heuristic', () => {
    it('filters when a single line exceeds maxLineLength', () => {
      const result = classifyContent(LONG_LINE_CONTENT);
      expect(result.filtered).toBe(true);
      expect(result.reasons.some(reason => reason.startsWith('long-line:'))).toBe(true);
    });

    it('filters when the ratio of long lines exceeds longLineRatio', () => {
      // 2 of 1000 lines are 15_000 chars → ratio 0.002 > 0.001; none exceed
      // maxLineLength (100_000), so only the ratio trigger can fire.
      const content = [
        ...Array.from({ length: 998 }, () => 'normal line'),
        ...Array.from({ length: 2 }, () => 'y'.repeat(15_000)),
      ].join('\n');
      const result = classifyContent(content);
      expect(result.filtered).toBe(true);
      expect(result.reasons.some(reason => reason.startsWith('long-line:'))).toBe(true);
    });

    it('does not filter when a long line is below maxLineLength and the ratio is not exceeded', () => {
      // 15_000-char line among 1000 lines: below maxLineLength, ratio 0.001.
      const content = [
        'z'.repeat(15_000),
        ...Array.from({ length: 999 }, (_, i) => `line number ${i}`),
      ].join('\n');
      const result = classifyContent(content);
      expect(result.filtered).toBe(false);
    });
  });

  describe('marker heuristic', () => {
    it('filters when the ratio of marker-matched lines exceeds markerRatio', () => {
      const result = classifyContent(MARKER_CONTENT);
      expect(result.filtered).toBe(true);
      expect(result.reasons.some(reason => reason.startsWith('marker:'))).toBe(true);
    });

    it('does not filter when the marker ratio stays at or below markerRatio', () => {
      // 5 of 100 lines match → exactly 5%, which does not exceed 5%.
      const content = [
        ...Array.from({ length: 95 }, (_, i) => `regular prose line number ${i}`),
        ...Array.from({ length: 5 }, () => '@@ -0,0 +1,20 @@'),
      ].join('\n');
      const result = classifyContent(content);
      expect(result.filtered).toBe(false);
    });

    it('matches the diff --git, index, hunk, and their/our header patterns', () => {
      // 8 of 100 lines match the five default patterns (8% > 5% marker ratio).
      const content = [
        ...Array.from({ length: 92 }, (_, i) => `regular prose line number ${i}`),
        'diff --git a/package.json b/package.json',
        'diff --git a/src/app.ts b/src/app.ts',
        'index abcdef1234567..89abcdef12345 100644',
        'index fedcba7654321..1234567890abc 100644',
        'added in remote',
        'our 123456',
        '@@ -0,0 +1,20 @@',
        '@@ -10,5 +10,7 @@',
      ].join('\n');
      const result = classifyContent(content);
      expect(result.filtered).toBe(true);
      expect(result.reasons.some(reason => reason.startsWith('marker:'))).toBe(true);
    });
  });

  describe('token diversity heuristic', () => {
    it('filters when unique/total token ratio is below minTokenDiversity', () => {
      const result = classifyContent(LOW_DIVERSITY_CONTENT);
      expect(result.filtered).toBe(true);
      expect(result.reasons.some(reason => reason.startsWith('diversity:'))).toBe(true);
    });
  });

  describe('normal content is not filtered (conservative defaults)', () => {
    it('does not filter normal markdown', () => {
      expect(classifyContent(MARKDOWN_FIXTURE).filtered).toBe(false);
    });

    it('does not filter normal TypeScript', () => {
      expect(classifyContent(TYPESCRIPT_FIXTURE).filtered).toBe(false);
    });

    it('does not filter plain-text prose', () => {
      expect(classifyContent(PROSE_FIXTURE).filtered).toBe(false);
    });

    it('returns an empty reasons array when not filtered', () => {
      expect(classifyContent(MARKDOWN_FIXTURE).reasons).toEqual([]);
    });
  });

  describe('edge cases', () => {
    it('does not filter empty content', () => {
      expect(classifyContent('')).toEqual({ filtered: false, reasons: [] });
    });

    it('does not filter whitespace-only content', () => {
      expect(classifyContent('   \n\t  \n  ')).toEqual({ filtered: false, reasons: [] });
    });
  });

  describe('configurable thresholds via ContentFilterOptions', () => {
    it('raises maxLineLength so a long line no longer triggers', () => {
      const result = classifyContent(LONG_LINE_CONTENT, { maxLineLength: 200_000 });
      expect(result.filtered).toBe(false);
    });

    it('lowers markerRatio so a low marker density triggers', () => {
      // 3 of 100 marker lines = 3%: below default 5%, above custom 2%.
      const content = [
        ...Array.from({ length: 97 }, (_, i) => `regular prose line number ${i}`),
        ...Array.from({ length: 3 }, () => '@@ -0,0 +1,20 @@'),
      ].join('\n');
      expect(classifyContent(content).filtered).toBe(false);
      expect(classifyContent(content, { markerRatio: 0.02 }).filtered).toBe(true);
    });

    it('raises minTokenDiversity so a moderately repetitive stream triggers', () => {
      // 15 unique tokens over 120 tokens = 12.5%: above default 10%, below 20%.
      const content = Array.from(
        { length: 8 },
        () => 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen',
      ).join(' ');
      expect(classifyContent(content).filtered).toBe(false);
      expect(classifyContent(content, { minTokenDiversity: 0.2 }).filtered).toBe(true);
    });

    it('accepts custom markerPatterns', () => {
      const content = [
        ...Array.from({ length: 94 }, (_, i) => `regular prose line number ${i}`),
        ...Array.from({ length: 6 }, () => 'MERGE CONFLICT MARKER'),
      ].join('\n');
      expect(classifyContent(content).filtered).toBe(false);
      const result = classifyContent(content, { markerPatterns: ['^MERGE CONFLICT MARKER$'] });
      expect(result.filtered).toBe(true);
    });
  });

  describe('enabled flag', () => {
    it('enabled: false disables every trigger', () => {
      const result = classifyContent(MERGE_TREE_EXCERPT, { enabled: false });
      expect(result).toEqual({ filtered: false, reasons: [] });
    });
  });

  describe('defaults', () => {
    it('exposes conservative defaults', () => {
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.enabled).toBe(true);
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.maxLineLength).toBe(100_000);
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.longLineChars).toBe(10_000);
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.longLineRatio).toBe(0.001);
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.markerPatterns).toEqual([
        '^diff --git',
        '^@@ -\\d+,\\d+ \\+\\d+,\\d+ @@',
        '^index [0-9a-f]{7,}\\.\\.[0-9a-f]{7,}',
        'added in remote',
        '(?:their|our) \\d{6}',
      ]);
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.markerRatio).toBe(0.05);
      expect(DEFAULT_CONTENT_FILTER_OPTIONS.minTokenDiversity).toBe(0.1);
    });

    it('classifyContent with no options behaves identically to explicit defaults', () => {
      const without = classifyContent(MERGE_TREE_EXCERPT);
      const withDefaults = classifyContent(MERGE_TREE_EXCERPT, DEFAULT_CONTENT_FILTER_OPTIONS);
      expect(without).toEqual(withDefaults);
    });
  });
});
