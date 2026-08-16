import { extractWikilinks } from './strategy-utils';

describe('extractWikilinks', () => {
  it('handles [[Note]] — basic link', () => {
    expect(extractWikilinks('[[Note]]')).toEqual(['Note']);
  });

  it('handles [[Note|alias]] — link with alias, returns target only', () => {
    expect(extractWikilinks('[[Note|alias]]')).toEqual(['Note']);
  });

  it('handles [[Note#Section]] — link with section, returns target only', () => {
    expect(extractWikilinks('[[Note#Section]]')).toEqual(['Note']);
  });

  it('handles [[Note#Section|alias]] — link with section and alias, returns target only', () => {
    expect(extractWikilinks('[[Note#Section|alias]]')).toEqual(['Note']);
  });

  it('handles ![[embed]] — embed syntax', () => {
    expect(extractWikilinks('![[embed]]')).toEqual(['embed']);
  });

  it('deduplicates — [[A]] [[B]] [[A]] returns [A, B]', () => {
    expect(extractWikilinks('[[A]] [[B]] [[A]]')).toEqual(['A', 'B']);
  });

  it('returns empty array when no wikilinks present', () => {
    expect(extractWikilinks('no links here')).toEqual([]);
  });

  it('returns empty array for empty input', () => {
    expect(extractWikilinks('')).toEqual([]);
  });

  it('skips [[ ]] — empty brackets', () => {
    expect(extractWikilinks('[[ ]]')).toEqual([]);
  });

  it('multiple distinct links — all captured, first-occurrence order', () => {
    const text = 'See [[Note A]] and [[Note B]] for details. Also check [[Note C|C alias]].';
    expect(extractWikilinks(text)).toEqual(['Note A', 'Note B', 'Note C']);
  });

  it('mixed variants — basic, alias, section, embed', () => {
    const text = '[[Basic]] ![[Embed]] [[With#Section]] [[With#Section|alias]]';
    expect(extractWikilinks(text)).toEqual(['Basic', 'Embed', 'With']);
  });
});
