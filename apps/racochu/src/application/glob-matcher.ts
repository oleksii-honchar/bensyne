import { isMatch, makeRe } from 'picomatch';

// Shared glob-matching utilities.
//
// Both the file watcher and the force-reprocess (and reconciliation) flows need
// identical exclude semantics. Historically each had its own home-grown matcher,
// which drifted. This module is the single source of truth: it is backed by
// picomatch so behavior matches standard glob semantics, and it normalizes
// patterns so they work against both absolute and relative paths.
//
// All functions are pure: no DI, no logger, no side effects.

// Match dotfiles and dot-directories (e.g. .git, .smart-env). Required for the
// watcher and for excluding dotfile directories; mirrors the watcher's behavior.
const PICO_OPTIONS = { dot: true } as const;

// Normalize a glob pattern into its canonical, depth-flexible form:
// trim surrounding whitespace, strip leading slashes so absolute-style patterns
// behave like relative ones, and add the any-depth prefix so the pattern matches
// at any path depth for both absolute and relative input paths.
// Deterministic: the same input always yields the same output.
export const normalizePattern = (pattern: string): string => {
  const trimmed = pattern.trim();
  if (trimmed === '') {
    return '';
  }

  const withoutLeadingSlash = trimmed.replace(/^\/+/, '');
  if (withoutLeadingSlash.startsWith('**/')) {
    return withoutLeadingSlash;
  }

  return `**/${withoutLeadingSlash}`;
};

// Return true if the given path matches any of the exclude patterns.
// Patterns are normalized (see normalizePattern) before matching, so an
// any-depth directory pattern or a '*.log' extension pattern matches regardless
// of path depth. Blank patterns never match. An empty patterns array returns
// false.
export const isPathExcluded = (path: string, patterns: string[]): boolean => {
  if (!patterns || patterns.length === 0) {
    return false;
  }

  return patterns.some(pattern => {
    const normalized = normalizePattern(pattern);
    if (!normalized) {
      return false;
    }
    return isMatch(path, normalized, PICO_OPTIONS);
  });
};

// Compile each pattern into a RegExp for consumers that need a raw regex (e.g.
// chokidar's `ignored` callback, where picomatch's matcher API is insufficient
// for directory avoidance). Blank patterns are skipped so the caller never
// receives a broken regex. Returns an empty array for empty/blank-only input.
export const buildIgnoreRegexes = (patterns: string[]): RegExp[] =>
  patterns
    .map(pattern => normalizePattern(pattern))
    .filter((pattern): pattern is string => Boolean(pattern))
    .map(pattern => makeRe(pattern, PICO_OPTIONS));
