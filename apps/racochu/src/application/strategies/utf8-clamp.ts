/**
 * clampUtf8 — truncate a string to a maximum UTF-8 byte length at a code-point boundary.
 *
 * UTF-8 continuation bytes always have the high two bits as 10 (0x80-0xBF).
 * When truncating, we back up from maxBytes to find a byte that is NOT a
 * continuation byte (either ASCII or the start of a multi-byte sequence).
 *
 * @param text - The input text to clamp.
 * @param maxBytes - Maximum UTF-8 byte length.
 * @returns The clamped text at a code-point boundary.
 */
export function clampUtf8(text: string, maxBytes: number): string {
  const buf = Buffer.from(text, 'utf8');

  if (buf.length <= maxBytes) {
    return text;
  }

  if (maxBytes === 0) {
    return '';
  }

  // Back up from maxBytes to find a non-continuation byte at the truncation point.
  // If the byte at end is a continuation byte (0x80-0xBF), we're cutting mid-character,
  // so we need to back up until we're at a character boundary.
  let end = maxBytes;
  while (end < buf.length && (buf[end] & 0xc0) === 0x80) {
    end--;
  }

  return buf.subarray(0, end).toString('utf8');
}