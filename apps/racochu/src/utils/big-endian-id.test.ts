import { generateId } from './big-endian-id';

describe('big-endian-id generateId', () => {
  it('returns a bigint, not a string', () => {
    const id = generateId();

    expect(typeof id).toBe('bigint');
  });

  it('returns a positive 64-bit integer (fits signed BigInt range)', () => {
    const id = generateId();

    expect(id).toBeGreaterThan(0n);
    expect(id).toBeLessThanOrEqual(9223372036854775807n);
  });

  it('returns monotonically increasing ids across calls', () => {
    const ids = [generateId(), generateId(), generateId(), generateId(), generateId()];

    for (let i = 1; i < ids.length; i++) {
      expect(ids[i]).toBeGreaterThan(ids[i - 1]);
    }
  });

  it('returns unique ids across many calls', () => {
    const ids = new Set<string>();
    for (let i = 0; i < 1000; i++) {
      ids.add(generateId().toString());
    }

    expect(ids.size).toBe(1000);
  });
});
