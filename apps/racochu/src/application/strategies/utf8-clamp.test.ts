import { clampUtf8 } from './utf8-clamp';

describe('clampUtf8', () => {
  test('ASCII text below limit returns unchanged', () => {
    const result = clampUtf8('hello world', 100);
    expect(result).toBe('hello world');
  });

  test('ASCII text above limit truncates at byte boundary', () => {
    const result = clampUtf8('hello world', 5);
    expect(result).toBe('hello');
  });

  test('Cyrillic text above limit truncates at code-point boundary', () => {
    // Each Cyrillic char is 2 bytes in UTF-8
    const text = 'Привет мир';
    const result = clampUtf8(text, 6); // 6 bytes = 3 full chars
    expect(result).toBe('При');
    // Verify each character is valid
    for (const char of result) {
      expect(char).toMatch(/^[\u0400-\u04FF]$/);
    }
  });

  test('CJK/emoji text above limit truncates at code-point boundary', () => {
    // Emoji is 4 bytes in UTF-8
    const text = 'Hello 🚀 World';
    const result = clampUtf8(text, 7); // 7 bytes = "Hello " + start of emoji
    expect(result).toBe('Hello ');
    // Verify no partial emoji
    expect(result).not.toContain('\uD83D');
  });

  test('Edge: maxBytes exactly at multi-byte char boundary', () => {
    const text = '你好';
    // Each Chinese char is 3 bytes
    const result = clampUtf8(text, 3);
    expect(result).toBe('你');
  });

  test('Edge: maxBytes in the middle of a multi-byte char', () => {
    const text = '你好';
    // 4 bytes is in the middle of second char (starts at byte 3, ends at byte 6)
    const result = clampUtf8(text, 4);
    // Should back up to first char boundary
    expect(result).toBe('你');
  });

  test('Edge: maxBytes = 0 returns empty string', () => {
    const result = clampUtf8('hello', 0);
    expect(result).toBe('');
  });

  test('Mixed ASCII and multi-byte content', () => {
    const text = 'Hello мир';
    // ASCII "Hello " is 6 bytes, "м" starts at byte 7
    const result = clampUtf8(text, 7);
    expect(result).toBe('Hello ');
  });
});