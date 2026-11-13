import { isMatch, makeRe } from 'picomatch';

// Shared glob-matching utilities.
//
// Both the file watcher and the force-reprocess (and reconciliation) flows need
// identical exclude AND include semantics. Historically each had its own
// home-grown matcher, which drifted. This module is the single source of truth
// for both the per-source exclude deny-lists and the per-source include
// allow-lists, including the one scope composition (isPathInScope) every
// enforcement point uses: it is backed by picomatch so behavior matches
// standard glob semantics, and it normalizes patterns so they work against
// both absolute and relative paths.
//
// Contract of the scope layer (spec §4 / ADR-2):
// - Hard guards (DEFAULT_IGNORE_GLOBS in file-watcher.service.ts) are a
//   separate, always-on layer enforced at the call sites; include composes
//   strictly above them and never re-admits a hard-guard path (invariant I1).
// - Scope predicates are evaluated against FILE paths only: call sites never
//   pass directory paths for include evaluation (invariant I2 — directory
//   descent/pruning stays the existing exclude-only behavior). The functions
//   themselves are path-kind-agnostic by design (no stat calls); the
//   files-only rule is part of the call-site contract.
// - The same normalized pattern set matches both path bases (watcher =
//   absolute, batch scans = root-relative); no per-EP pattern rewriting
//   (invariant I3).
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

// Return true if the given path matches the include allow-list. An EMPTY
// patterns array allows everything (an absent include field is represented as
// "no include" by callers via isPathInScope). Patterns are normalized exactly
// like exclude patterns (see normalizePattern), so one pattern set works for
// both root-relative and absolute path bases. Blank patterns never match.
// Evaluated against file paths only — a call-site contract (invariant I2
// from the module header): extension patterns never match directory paths, so
// directory descent is never pruned by include.
export const isPathIncluded = (path: string, patterns: string[]): boolean => {
  if (!patterns || patterns.length === 0) {
    return true;
  }

  return patterns.some(pattern => {
    const normalized = normalizePattern(pattern);
    if (!normalized) {
      return false;
    }
    return isMatch(path, normalized, PICO_OPTIONS);
  });
};

// The one scope composition every enforcement point uses — reasoning order:
// hard guards (their own always-on layer at the call sites) ∧
// (no include ∨ included) ∧ ¬excluded.
// Include NEVER re-admits a path removed by the hard-guard layer or by an
// exclude pattern (invariant I1: include composes strictly above them, and an
// include∧exclude overlap is excluded). `include` is the raw per-source config
// value: undefined/absent or [] means "no include list" (include-neutral), so
// back-compat is exact for configs without include. Evaluated against file
// paths only (invariant I2 — see module header).
export const isPathInScope = (path: string, include: string[] | undefined, exclude: string[]): boolean => {
  const included = !include || isPathIncluded(path, include);
  return included && !isPathExcluded(path, exclude);
};
