import { isPastDue, type IsPastDueInput } from './ttl-activity';

const DAY_MS = 86_400_000;

// Deterministic wall clock for all cases (fixed epoch-ms values).
const NOW = 1_700_000_000_000;
const FRESH = NOW - 60_000; // 1 minute ago — never past due for day-scale TTLs
const OLD = NOW - 40 * DAY_MS; // 40 days ago — past due at ttlDays: 30

interface ClockCase {
  readonly name: string;
  readonly input: IsPastDueInput;
  readonly expected: boolean;
}

describe('isPastDue', () => {
  describe('mtime is the authoritative clock when provided', () => {
    const cases: readonly ClockCase[] = [
      {
        name: 'old row + fresh mtime → false (recent file activity keeps a stale row alive)',
        input: { mtimeMs: FRESH, rowUpdatedAt: new Date(OLD), rowCreatedAt: new Date(OLD), ttlDays: 30 },
        expected: false,
      },
      {
        name: 'fresh row + old mtime → true (file inactivity pages even a fresh row)',
        input: { mtimeMs: OLD, rowUpdatedAt: new Date(FRESH), rowCreatedAt: new Date(FRESH), ttlDays: 30 },
        expected: true,
      },
    ];
    it.each(cases)('$name', ({ input, expected }) => {
      expect(isPastDue(input, NOW)).toBe(expected);
    });
  });

  describe('row fallback order when mtimeMs is absent (ENOENT expressed by omission)', () => {
    const cases: readonly ClockCase[] = [
      {
        name: 'no mtime, fresh rowUpdatedAt + old createdAt → false (updatedAt wins over createdAt)',
        input: { rowUpdatedAt: new Date(FRESH), rowCreatedAt: new Date(OLD), ttlDays: 30 },
        expected: false,
      },
      {
        name: 'no mtime, old rowUpdatedAt + fresh createdAt → true (updatedAt wins even when createdAt is fresher)',
        input: { rowUpdatedAt: new Date(OLD), rowCreatedAt: new Date(FRESH), ttlDays: 30 },
        expected: true,
      },
      {
        name: 'no mtime, rowUpdatedAt null → createdAt fallback → old createdAt is past due',
        input: { rowUpdatedAt: null, rowCreatedAt: new Date(OLD), ttlDays: 30 },
        expected: true,
      },
      {
        name: 'no mtime, rowUpdatedAt absent → fresh createdAt fallback → not past due',
        input: { rowCreatedAt: new Date(FRESH), ttlDays: 30 },
        expected: false,
      },
      {
        name: 'no mtime, rowUpdatedAt absent → old createdAt fallback → past due',
        input: { rowCreatedAt: new Date(OLD), ttlDays: 30 },
        expected: true,
      },
    ];
    it.each(cases)('$name', ({ input, expected }) => {
      expect(isPastDue(input, NOW)).toBe(expected);
    });
  });

  describe('boundary is strictly greater (== ttlDays is NOT past due)', () => {
    interface BoundaryCase {
      readonly name: string;
      readonly ageMs: number;
      readonly ttlDays: number;
      readonly expected: boolean;
    }
    const cases: readonly BoundaryCase[] = [
      { name: 'ttlDays 30: age exactly 30 days in ms → false', ageMs: 30 * DAY_MS, ttlDays: 30, expected: false },
      { name: 'ttlDays 30: age one ms past 30 days → true', ageMs: 30 * DAY_MS + 1, ttlDays: 30, expected: true },
      { name: 'ttlDays 1: age exactly 1 day → false', ageMs: DAY_MS, ttlDays: 1, expected: false },
      { name: 'ttlDays 1: age one ms past 1 day → true', ageMs: DAY_MS + 1, ttlDays: 1, expected: true },
      { name: 'ttlDays 30: age zero → false', ageMs: 0, ttlDays: 30, expected: false },
    ];
    it.each(cases)('$name', ({ ageMs, ttlDays, expected }) => {
      expect(isPastDue({ mtimeMs: NOW - ageMs, rowCreatedAt: new Date(NOW), ttlDays }, NOW)).toBe(expected);
    });

    it('same boundary reached through a Date row field → identical verdicts', () => {
      expect(
        isPastDue({ rowCreatedAt: new Date(NOW - 30 * DAY_MS), ttlDays: 30 }, NOW),
      ).toBe(false);
      expect(
        isPastDue({ rowCreatedAt: new Date(NOW - 30 * DAY_MS - 1), ttlDays: 30 }, NOW),
      ).toBe(true);
    });
  });

  describe('epoch/Date normalization: one instant expressed through any clock slot gives an identical verdict', () => {
    // Same effective clock instant supplied via each precedence slot — epoch ms in
    // mtimeMs, Date objects on the row fields — must produce ONE shared verdict.
    const sameInstantVerdicts = (ageMs: number, ttlDays: number): readonly boolean[] => [
      isPastDue({ mtimeMs: NOW - ageMs, rowCreatedAt: new Date(NOW), ttlDays }, NOW),
      isPastDue({ rowUpdatedAt: new Date(NOW - ageMs), rowCreatedAt: new Date(NOW), ttlDays }, NOW),
      isPastDue({ rowCreatedAt: new Date(NOW - ageMs), ttlDays }, NOW),
    ];

    it('40-day-old instant via mtimeMs / rowUpdatedAt / rowCreatedAt → all true', () => {
      const verdicts = sameInstantVerdicts(40 * DAY_MS, 30);
      expect(verdicts).toEqual([true, true, true]);
    });

    it('fresh instant via mtimeMs / rowUpdatedAt / rowCreatedAt → all false', () => {
      const verdicts = sameInstantVerdicts(60_000, 30);
      expect(verdicts).toEqual([false, false, false]);
    });

    it('exact-boundary instant via any slot → all false (no rounding drift between representations)', () => {
      const verdicts = sameInstantVerdicts(30 * DAY_MS, 30);
      expect(verdicts).toEqual([false, false, false]);
    });
  });

  describe('ttlDays guards: the gate is strictly opt-in (positive number required)', () => {
    const guardCases: ReadonlyArray<{ name: string; ttlDays: number | null | undefined }> = [
      { name: 'null', ttlDays: null },
      { name: 'undefined', ttlDays: undefined },
      { name: 'negative', ttlDays: -1 },
      { name: 'large negative', ttlDays: -365 },
      { name: 'zero (not a positive number)', ttlDays: 0 },
    ];
    it.each(guardCases)('ttlDays %s → never past due for any age', ({ ttlDays }) => {
      const ancient = NOW - 400 * DAY_MS;
      expect(isPastDue({ mtimeMs: ancient, rowCreatedAt: new Date(ancient), ttlDays }, NOW)).toBe(false);
      expect(isPastDue({ rowCreatedAt: new Date(ancient), ttlDays }, NOW)).toBe(false);
    });
  });
});
