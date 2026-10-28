const MS_PER_DAY = 86_400_000;

export interface IsPastDueInput {
  /** File mtime in epoch ms — authoritative activity clock when the caller has a stat result. Omit when the file is absent (ENOENT). */
  readonly mtimeMs?: number;
  /** Row updatedAt — fallback activity clock, used only when mtimeMs is absent. */
  readonly rowUpdatedAt?: Date | null;
  /** Row createdAt — last-resort fallback activity clock. */
  readonly rowCreatedAt: Date;
  /** Per-source retention window in days. Not a positive number → never past due (opt-in gate). */
  readonly ttlDays: number | null | undefined;
}

/**
 * Pure activity-clock rule (spec §3.1): an item is past due when its last
 * activity is STRICTLY older than `ttlDays`. Clock precedence:
 * mtimeMs (authoritative) → rowUpdatedAt → rowCreatedAt; all values are
 * normalized to epoch ms here. The caller performs any fs.stat — this helper
 * never does I/O.
 */
export function isPastDue(input: IsPastDueInput, now: number): boolean {
  const { mtimeMs, rowUpdatedAt, rowCreatedAt, ttlDays } = input;

  if (ttlDays == null || ttlDays <= 0) {
    return false;
  }

  const clockMs: number = mtimeMs ?? rowUpdatedAt?.getTime() ?? rowCreatedAt.getTime();

  return now - clockMs > ttlDays * MS_PER_DAY;
}
