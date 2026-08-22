import { guardBase64Content, isBase64Blob } from './base64-guard';

// Test fixtures (all base64 strings use only the [A-Za-z0-9+/] charset + '=' padding)
const LONG_B64_NO_PAD = 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFh'; // 64 chars, no padding
const LONG_B64_PADDED = 'YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE='; // 64 chars, = padding
const SHORT_B64 = 'aGVsbG8gd29ybGQ='; // 16 chars
const MEDIUM_B64 = 'YWFhYWFhYWFhYWFhYWFhYWFhYWE='; // 28 chars

describe('isBase64Blob', () => {
  describe('Rule 1 — pure base64 (whole trimmed content is base64)', () => {
    it('returns true for a pure base64 string of 64 chars (no padding)', () => {
      expect(isBase64Blob(LONG_B64_NO_PAD)).toBe(true);
    });

    it('returns true for a pure base64 string of 64 chars (with = padding)', () => {
      expect(isBase64Blob(LONG_B64_PADDED)).toBe(true);
    });

    it('returns true for a long pure base64 string (200 chars)', () => {
      expect(isBase64Blob('YWFh'.repeat(50))).toBe(true);
    });

    it('trims surrounding whitespace before detecting pure base64', () => {
      expect(isBase64Blob(`  ${LONG_B64_NO_PAD} \n`)).toBe(true);
    });

    it('detects a base64 blob that starts with padding-eligible characters', () => {
      // A base64 string that legitimately begins with '=' is not possible,
      // but verify a mixed-case/numeric/digit run still matches the charset.
      const mixed = 'AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/ABCDEF0123456789+/ABCDEF01'; // 65 chars
      expect(isBase64Blob(mixed)).toBe(true);
    });
  });

  describe('Rule 2 — single-field base64 envelope', () => {
    it('returns true for {"result":"<base64 64+ chars>"} (observed killer case)', () => {
      const envelope = `{"result":"${LONG_B64_NO_PAD}"}`;
      expect(isBase64Blob(envelope)).toBe(true);
    });

    it('returns true for envelope with a different single key', () => {
      const envelope = `{"data":"${LONG_B64_NO_PAD}"}`;
      expect(isBase64Blob(envelope)).toBe(true);
    });

    it('returns true for envelope whose value is padded base64', () => {
      const envelope = `{"result":"${LONG_B64_PADDED}"}`;
      expect(isBase64Blob(envelope)).toBe(true);
    });

    it('returns true for an envelope with internal whitespace after the colon', () => {
      const envelope = `{"result": "${LONG_B64_NO_PAD}"}`;
      expect(isBase64Blob(envelope)).toBe(true);
    });

    it('trims whitespace around the envelope JSON', () => {
      const envelope = `  \n {"result":"${LONG_B64_NO_PAD}"} \n  `;
      expect(isBase64Blob(envelope)).toBe(true);
    });

    it('returns true for a multi-line pretty-printed single-field envelope', () => {
      const envelope = `{
  "result": "${LONG_B64_NO_PAD}"
}`;
      expect(isBase64Blob(envelope)).toBe(true);
    });
  });

  describe('negative cases — returns false', () => {
    it('returns false for normal prose', () => {
      expect(isBase64Blob('This is normal prose with words and spaces.')).toBe(false);
    });

    it('returns false for markdown content with headings and formatting', () => {
      const markdown = '# Title\n\nThis is a **markdown** document with *formatting*.';
      expect(isBase64Blob(markdown)).toBe(false);
    });

    it('returns false for an empty string', () => {
      expect(isBase64Blob('')).toBe(false);
    });

    it('returns false for a whitespace-only string', () => {
      expect(isBase64Blob('   \n \t  ')).toBe(false);
    });

    it('returns false for short base64 (16 chars < 64)', () => {
      expect(isBase64Blob(SHORT_B64)).toBe(false);
    });

    it('returns false for medium base64 (28 chars < 64)', () => {
      expect(isBase64Blob(MEDIUM_B64)).toBe(false);
    });

    it('returns false for base64 interspersed with surrounding text', () => {
      const mixed = `Here is the token: ${LONG_B64_NO_PAD} and some more text after it.`;
      expect(isBase64Blob(mixed)).toBe(false);
    });

    it('returns false for base64 split by internal whitespace', () => {
      const split = 'YWFhYWFh YWFhYWFh YWFhYWFh YWFhYWFh YWFhYWFh YWFhYWFh YWFhYWFh YWFhYWFh';
      expect(isBase64Blob(split)).toBe(false);
    });

    it('returns false for base64 where invalid characters dominate', () => {
      const invalid = 'YWFhYWFh!@#$%^&*() YWFhYWFh~`{}[] YWFhYWFh<>?\\|" YWFhYWFh()_+-=\\|';
      expect(isBase64Blob(invalid)).toBe(false);
    });

    it('returns false for a multi-key JSON object', () => {
      const multi = `{"result":"${LONG_B64_NO_PAD}","extra":"x"}`;
      expect(isBase64Blob(multi)).toBe(false);
    });

    it('returns false for an empty JSON object', () => {
      expect(isBase64Blob('{}')).toBe(false);
    });

    it('returns false for a JSON array even of base64 strings', () => {
      expect(isBase64Blob(`["${LONG_B64_NO_PAD}"]`)).toBe(false);
    });

    it('returns false for a JSON primitive string value', () => {
      expect(isBase64Blob(`"${LONG_B64_NO_PAD}"`)).toBe(false);
    });

    it('returns false for an envelope whose value is not base64', () => {
      expect(isBase64Blob('{"result":"hello world"}')).toBe(false);
    });

    it('returns false for an envelope whose single value is a number', () => {
      expect(isBase64Blob('{"result":1234567890}')).toBe(false);
    });

    it('returns false for an envelope whose value is base64 but < 64 chars', () => {
      const envelope = `{"result":"${SHORT_B64}"}`;
      expect(isBase64Blob(envelope)).toBe(false);
    });

    it('returns false for invalid JSON that starts with {', () => {
      expect(isBase64Blob('{not valid json')).toBe(false);
    });

    it('returns false when only part of the content is a base64 blob', () => {
      const partial = `prefix text\n${LONG_B64_NO_PAD}\nsuffix text`;
      expect(isBase64Blob(partial)).toBe(false);
    });
  });
});

describe('guardBase64Content', () => {
  it('returns sanitized:true with a placeholder for a pure base64 blob', () => {
    const result = guardBase64Content(LONG_B64_NO_PAD);
    expect(result.sanitized).toBe(true);
    expect(result.content).toBe('[base64 content omitted: 64 bytes]');
    expect(result.content).not.toContain(LONG_B64_NO_PAD);
  });

  it('returns sanitized:true with a placeholder for an envelope blob', () => {
    const envelope = `{"result":"${LONG_B64_NO_PAD}"}`;
    const result = guardBase64Content(envelope);
    expect(result.sanitized).toBe(true);
    expect(result.content).toBe(`[base64 content omitted: ${envelope.length} bytes]`);
    expect(result.content).not.toContain(LONG_B64_NO_PAD);
  });

  it('returns sanitized:false with unchanged content for normal prose', () => {
    const prose = 'This is normal prose.';
    const result = guardBase64Content(prose);
    expect(result.sanitized).toBe(false);
    expect(result.content).toBe(prose);
  });

  it('returns sanitized:false with unchanged content for short base64', () => {
    const result = guardBase64Content(SHORT_B64);
    expect(result.sanitized).toBe(false);
    expect(result.content).toBe(SHORT_B64);
  });

  it('returns sanitized:false with unchanged content for a multi-key JSON object', () => {
    const multi = `{"result":"${LONG_B64_NO_PAD}","extra":"x"}`;
    const result = guardBase64Content(multi);
    expect(result.sanitized).toBe(false);
    expect(result.content).toBe(multi);
  });

  it('returns sanitized:false with unchanged content for an empty string', () => {
    const result = guardBase64Content('');
    expect(result.sanitized).toBe(false);
    expect(result.content).toBe('');
  });

  it('returns sanitized:false with unchanged content for markdown prose', () => {
    const markdown = '# Heading\n\nSome body text here.';
    const result = guardBase64Content(markdown);
    expect(result.sanitized).toBe(false);
    expect(result.content).toBe(markdown);
  });

  it('placeholder reflects the byte length of the original content', () => {
    const long = 'YWFh'.repeat(80); // 320 chars
    const result = guardBase64Content(long);
    expect(result.sanitized).toBe(true);
    expect(result.content).toBe(`[base64 content omitted: ${long.length} bytes]`);
  });

  it('does not mutate or leak the original blob into the placeholder', () => {
    const long = 'YWFh'.repeat(100);
    const result = guardBase64Content(long);
    expect(result.sanitized).toBe(true);
    expect(result.content.length).toBeLessThan(long.length);
    expect(result.content.startsWith('[base64 content omitted:')).toBe(true);
    expect(result.content.endsWith('bytes]')).toBe(true);
  });
});
