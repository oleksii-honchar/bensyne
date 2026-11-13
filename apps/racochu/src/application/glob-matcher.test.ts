import {
  buildIgnoreRegexes,
  isPathExcluded,
  isPathIncluded,
  isPathInScope,
  normalizePattern,
} from './glob-matcher';

describe('glob-matcher', () => {
  describe('normalizePattern', () => {
    it('is deterministic — same input always yields same output', () => {
      expect(normalizePattern('node_modules/**')).toBe(normalizePattern('node_modules/**'));
      expect(normalizePattern('**/tool-responses/**')).toBe(normalizePattern('**/tool-responses/**'));
    });

    it('preserves patterns that already start with **/', () => {
      expect(normalizePattern('**/tool-responses/**')).toBe('**/tool-responses/**');
      expect(normalizePattern('**/node_modules/**')).toBe('**/node_modules/**');
    });

    it('prepends **/ to relative patterns so they match at any depth', () => {
      expect(normalizePattern('node_modules/**')).toBe('**/node_modules/**');
      expect(normalizePattern('.git/**')).toBe('**/.git/**');
    });

    it('prepends **/ to extension patterns', () => {
      expect(normalizePattern('*.log')).toBe('**/*.log');
    });

    it('strips a leading slash before normalizing', () => {
      expect(normalizePattern('/x/**')).toBe('**/x/**');
    });

    it('strips leading slashes even when **/ follows', () => {
      expect(normalizePattern('/**/x/**')).toBe('**/x/**');
    });

    it('trims surrounding whitespace', () => {
      expect(normalizePattern('  node_modules/**  ')).toBe('**/node_modules/**');
    });

    it('returns an empty string for blank input', () => {
      expect(normalizePattern('')).toBe('');
      expect(normalizePattern('   ')).toBe('');
    });
  });

  describe('isPathExcluded', () => {
    it('returns true for a file inside an excluded directory (absolute path)', () => {
      expect(isPathExcluded('/a/b/tool-responses/x.log', ['**/tool-responses/**'])).toBe(true);
    });

    it('returns false for a file outside the excluded directory', () => {
      expect(isPathExcluded('/a/b/normal.log', ['**/tool-responses/**'])).toBe(false);
    });

    it('returns true for node_modules files (absolute path)', () => {
      expect(isPathExcluded('/a/b/node_modules/pkg/file.js', ['**/node_modules/**'])).toBe(true);
    });

    it('returns true for a relative path when the pattern matches at depth', () => {
      expect(isPathExcluded('a/b/tool-responses/x.log', ['**/tool-responses/**'])).toBe(true);
      expect(isPathExcluded('tool-responses/x.log', ['**/tool-responses/**'])).toBe(true);
    });

    it('handles ** across multiple path segments', () => {
      expect(isPathExcluded('/a/b/c/d/x/file.txt', ['**/x/**'])).toBe(true);
      expect(isPathExcluded('/a/x/y/x/file.txt', ['**/x/**'])).toBe(true);
      expect(isPathExcluded('/a/b/y/file.txt', ['**/x/**'])).toBe(false);
    });

    it('matches dotfile directories with dot: true semantics', () => {
      expect(isPathExcluded('/a/.smart-env/config.json', ['**/.smart-env/**'])).toBe(true);
      expect(isPathExcluded('/a/b/.git/config', ['**/.git/**'])).toBe(true);
    });

    it('matches by basename via the **/ prefix for extension patterns', () => {
      expect(isPathExcluded('/a/sub/x.log', ['*.log'])).toBe(true);
      expect(isPathExcluded('/a/sub/x.txt', ['*.log'])).toBe(false);
    });

    it('matches when any of multiple patterns matches', () => {
      expect(
        isPathExcluded('/a/b/node_modules/pkg/f.js', ['**/tool-responses/**', '**/node_modules/**']),
      ).toBe(true);
      expect(
        isPathExcluded('/a/b/tool-responses/x.log', ['**/node_modules/**', '**/tool-responses/**']),
      ).toBe(true);
    });

    it('returns false when no pattern matches', () => {
      expect(isPathExcluded('/a/b/normal.log', ['**/node_modules/**', '**/tool-responses/**'])).toBe(false);
    });

    it('returns false for an empty patterns array', () => {
      expect(isPathExcluded('/a/b/anything.log', [])).toBe(false);
    });

    it('ignores blank patterns without matching everything', () => {
      expect(isPathExcluded('/a/b/x.log', [''])).toBe(false);
      expect(isPathExcluded('/a/b/x.log', ['', '   '])).toBe(false);
    });

    it('handles patterns given with a leading slash', () => {
      expect(isPathExcluded('/a/b/tool-responses/x.log', ['/tool-responses/**'])).toBe(true);
    });
  });

  describe('isPathIncluded', () => {
    it('allows every path when the include list is empty (absent include allows all)', () => {
      expect(isPathIncluded('/a/b/anything.txt', [])).toBe(true);
      expect(isPathIncluded('notes/whatever.png', [])).toBe(true);
    });

    it('returns true for paths matching an include extension pattern (root-relative)', () => {
      // Probe cases (materials/script-picomatch-include-probe.mjs) 1–2:
      // '**/*.md' matches 'session.md' and 'findings/findings.md'.
      expect(isPathIncluded('session.md', ['**/*.md'])).toBe(true);
      expect(isPathIncluded('findings/findings.md', ['**/*.md'])).toBe(true);
    });

    it('returns true for paths matching an include extension pattern (absolute)', () => {
      // Probe case 4 (corrected finding): the normalized '**/' prefix matches
      // all depths, so the same pattern set matches absolute paths too.
      expect(isPathIncluded('/abs/root/session.md', ['**/*.md'])).toBe(true);
      expect(isPathIncluded('/abs/root/findings/findings.md', ['**/*.md'])).toBe(true);
    });

    it('returns false when no pattern matches', () => {
      expect(isPathIncluded('/a/b/notes.txt', ['**/*.md'])).toBe(false);
      expect(isPathIncluded('a/b/c.ts', ['**/*.md', '**/*.mmd'])).toBe(false);
    });

    it('matches when any of multiple patterns matches', () => {
      expect(isPathIncluded('/a/b/notes.mmd', ['**/*.md', '**/*.mmd'])).toBe(true);
      expect(isPathIncluded('/a/b/notes.md', ['**/docs/**', '**/*.md'])).toBe(true);
    });

    it('matches directory-anchored patterns — the dir itself and its contents', () => {
      // Probe cases 5–6: dir-anchored include patterns CAN match directory
      // paths (call sites are still contractually files-only — see I2).
      expect(isPathIncluded('docs', ['**/docs/**'])).toBe(true);
      expect(isPathIncluded('docs/notes.md', ['**/docs/**'])).toBe(true);
      expect(isPathIncluded('/abs/root/docs/notes.md', ['**/docs/**'])).toBe(true);
    });

    it('normalizes include patterns through the same pipeline as excludes', () => {
      // Probe case 7: a bare '.md' normalizes to '**/.md' — a basename glob,
      // not an extension glob; extension include lists are written '*.md'.
      expect(isPathIncluded('a.md', ['.md'])).toBe(false);
      expect(isPathIncluded('a/sub/x.md', ['.md'])).toBe(false);
      expect(isPathIncluded('a/sub/x.md', ['*.md'])).toBe(true);
      // Leading-slash patterns behave like relative ones (normalizePattern).
      expect(isPathIncluded('/a/x.md', ['/x.md'])).toBe(true);
    });

    it('ignores blank patterns without matching everything', () => {
      expect(isPathIncluded('/a/b/x.log', [''])).toBe(false);
      expect(isPathIncluded('/a/b/x.log', ['', '   '])).toBe(false);
    });
  });

  describe('isPathInScope — spec §4 semantics truth table', () => {
    it("row: include absent, not excluded → in scope (today's behavior)", () => {
      expect(isPathInScope('/a/b/anything.txt', undefined, ['**/node_modules/**'])).toBe(true);
    });

    it("row: include absent, excluded → out of scope (today's behavior)", () => {
      expect(isPathInScope('/a/node_modules/pkg/file.js', undefined, ['**/node_modules/**'])).toBe(false);
    });

    it('row: empty include list behaves as absent (allow-all)', () => {
      expect(isPathInScope('/a/b/anything.txt', [], ['**/node_modules/**'])).toBe(true);
    });

    it('row: empty include list, excluded → out of scope', () => {
      expect(isPathInScope('/a/node_modules/pkg/file.js', [], ['**/node_modules/**'])).toBe(false);
    });

    it('row: include non-empty, matched, not excluded → in scope (new)', () => {
      expect(isPathInScope('notes/session.md', ['**/*.md'], ['**/*.png'])).toBe(true);
      expect(isPathInScope('/abs/root/notes/session.md', ['**/*.md'], [])).toBe(true);
    });

    it('row: include non-empty, not matched → out of scope regardless of exclude', () => {
      expect(isPathInScope('notes/session.txt', ['**/*.md'], [])).toBe(false);
      expect(isPathInScope('notes/session.txt', ['**/*.md'], ['**/drafts/**'])).toBe(false);
    });

    it('row: include matched AND exclude matched → out of scope (exclude wins)', () => {
      expect(isPathInScope('drafts/session.md', ['**/*.md'], ['**/drafts/**'])).toBe(false);
    });
  });

  describe('invariant I1 — hard guards are never re-admitted by include', () => {
    // Hard guards (DEFAULT_IGNORE_GLOBS in file-watcher.service.ts) live in a
    // separate always-on layer above this module; include composes strictly
    // above them. Tested via the composition: included but excluded ⇒ out.
    it('keeps .git files out of scope even when the include pattern matches them', () => {
      const include = ['**/*.md'];
      expect(isPathIncluded('/repo/.git/README.md', include)).toBe(true);
      expect(isPathInScope('/repo/.git/README.md', include, ['**/.git/**'])).toBe(false);
    });

    it('keeps node_modules files out of scope even when the include pattern matches them', () => {
      const include = ['**/*.js'];
      expect(isPathIncluded('/repo/node_modules/pkg/index.js', include)).toBe(true);
      expect(isPathInScope('/repo/node_modules/pkg/index.js', include, ['**/node_modules/**'])).toBe(false);
    });

    it('keeps dot-file guard names out of scope even when the include pattern matches them', () => {
      const include = ['**/.env*'];
      expect(isPathIncluded('/repo/.env.local', include)).toBe(true);
      expect(isPathInScope('/repo/.env.local', include, ['**/.env*'])).toBe(false);
    });
  });

  describe('invariant I2 — include is evaluated against files only, never directory paths', () => {
    // The functions are path-kind-agnostic by design (no stat calls). The
    // files-only rule is a call-site contract: extension include patterns
    // never match directory paths, so directory descent stays exclude-only.
    it('extension include patterns do not match directory paths (root-relative and absolute)', () => {
      // Probe case 3: '**/*.md' vs 'findings' → false.
      expect(isPathIncluded('findings', ['**/*.md'])).toBe(false);
      expect(isPathIncluded('/abs/root/findings', ['**/*.md'])).toBe(false);
    });

    it('files living under directories that no extension include pattern matches remain in scope', () => {
      // Descent is not include-pruned: the file itself, not its directory,
      // is evaluated.
      expect(isPathInScope('findings/findings.md', ['**/*.md'], [])).toBe(true);
      expect(isPathInScope('/abs/root/findings/findings.md', ['**/*.md'], [])).toBe(true);
    });
  });

  describe('invariant I3 — one normalized pattern set serves both path bases (no per-EP rewriting)', () => {
    // Transplanted probe fixtures: the SAME pattern set produces identical
    // results for root-relative and absolute paths (i3: watcher=absolute,
    // batch=root-relative).
    const INCLUDE = ['**/*.md', '**/docs/**'];
    const parityCases: { relative: string; absolute: string; expected: boolean }[] = [
      { relative: 'session.md', absolute: '/abs/root/session.md', expected: true },
      { relative: 'findings/findings.md', absolute: '/abs/root/findings/findings.md', expected: true },
      { relative: 'docs/notes.md', absolute: '/abs/root/docs/notes.md', expected: true },
      { relative: 'notes.txt', absolute: '/abs/root/notes.txt', expected: false },
      { relative: 'docs', absolute: '/abs/root/docs', expected: true },
    ];

    it('returns identical results for root-relative and absolute fixtures with one pattern set', () => {
      for (const { relative, absolute, expected } of parityCases) {
        expect(isPathIncluded(relative, INCLUDE)).toBe(expected);
        expect(isPathIncluded(absolute, INCLUDE)).toBe(expected);
        expect(isPathInScope(relative, INCLUDE, [])).toBe(expected);
        expect(isPathInScope(absolute, INCLUDE, [])).toBe(expected);
      }
    });

    it('parity also holds through scope composition with shared excludes', () => {
      const exclude = ['**/drafts/**'];
      expect(isPathInScope('drafts/a.md', INCLUDE, exclude)).toBe(false);
      expect(isPathInScope('/abs/root/drafts/a.md', INCLUDE, exclude)).toBe(false);
      expect(isPathInScope('findings/b.md', INCLUDE, exclude)).toBe(true);
      expect(isPathInScope('/abs/root/findings/b.md', INCLUDE, exclude)).toBe(true);
    });
  });

  describe('buildIgnoreRegexes', () => {
    it('returns an array of RegExp instances', () => {
      const regexes = buildIgnoreRegexes(['**/node_modules/**', '*.log']);
      expect(Array.isArray(regexes)).toBe(true);
      expect(regexes.every(r => r instanceof RegExp)).toBe(true);
    });

    it('correctly matches node_modules paths', () => {
      const [re] = buildIgnoreRegexes(['**/node_modules/**']);
      expect(re.test('/a/node_modules/pkg/file.js')).toBe(true);
      expect(re.test('/a/node_modules/file.js')).toBe(true);
      expect(re.test('/a/src/file.js')).toBe(false);
    });

    it('correctly matches extension patterns at any depth', () => {
      const [re] = buildIgnoreRegexes(['*.log']);
      expect(re.test('/a/b/c.log')).toBe(true);
      expect(re.test('/c.log')).toBe(true);
      expect(re.test('/a/b/c.txt')).toBe(false);
    });

    it('correctly matches dotfile directory patterns', () => {
      const [re] = buildIgnoreRegexes(['**/.git/**']);
      expect(re.test('/a/b/.git/config')).toBe(true);
      expect(re.test('/a/b/config')).toBe(false);
    });

    it('produces independent regexes per pattern', () => {
      const [nm, log] = buildIgnoreRegexes(['**/node_modules/**', '*.log']);
      expect(nm.test('/a/node_modules/f.js')).toBe(true);
      expect(nm.test('/a/b/x.log')).toBe(false);
      expect(log.test('/a/b/x.log')).toBe(true);
      expect(log.test('/a/node_modules/f.js')).toBe(false);
    });

    it('skips blank patterns instead of producing a broken regex', () => {
      expect(buildIgnoreRegexes([])).toEqual([]);
      expect(buildIgnoreRegexes(['', '   '])).toEqual([]);
    });

    it('is deterministic — identical input yields identical regex source', () => {
      const a = buildIgnoreRegexes(['**/node_modules/**']);
      const b = buildIgnoreRegexes(['**/node_modules/**']);
      expect(a[0].source).toBe(b[0].source);
    });
  });
});
