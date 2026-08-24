import { buildIgnoreRegexes, isPathExcluded, normalizePattern } from './glob-matcher';

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
