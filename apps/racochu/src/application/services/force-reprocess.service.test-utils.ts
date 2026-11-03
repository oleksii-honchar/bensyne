/**
 * Test utilities for ForceReprocessService (T6 / spec C8).
 *
 * Provides the scripted-outcome vocabulary for per-run summary counter tests:
 * each file in a batch run is scripted to a `ProcessFileOutcome` kind exactly
 * as ProcessFileUseCase.execute would return it (real ingest with memoryIds,
 * hash-gate skip, terminal skip, failure). Loop-level outcomes that never
 * reach execute() (verified-healthy skips, activity-expired skips) are
 * scripted through the other fakes by the tests themselves.
 */

import { FileTracker, FileTrackerSkipReason } from '../../domain/file-tracker.aggregate';
import { Result } from '../../utils/result';
import { BatchRunSummary } from './force-reprocess.service';

/** Scriptable outcome kinds returned by a faked ProcessFileUseCase.execute. */
export type ScriptedOutcomeKind = 'ingest' | 'gated-skip' | 'terminal-skip' | 'failure';

/**
 * Build the Result a real ProcessFileUseCase.execute would return for one
 * outcome kind (C8 summary classification inputs — the additive `skipped`
 * marker set by the use case at its skip return sites). Typed at the
 * unknown-payload seam on purpose: the service loop classifies through a
 * local narrowing, exactly as it does with the real Result.
 */
export function anOutcomeFor(
  kind: ScriptedOutcomeKind,
  memoryIds: string[] = ['mem-ingested-1'],
): Result<unknown> {
  switch (kind) {
    case 'ingest':
      return Result.ok({ memoryIds });
    case 'gated-skip':
      return Result.ok({ memoryIds: [], skipped: 'unchanged' });
    case 'terminal-skip':
      return Result.ok({ memoryIds: [], skipped: 'terminal' });
    case 'failure':
      return Result.ko([new Error('scripted processing failure')]);
  }
}

/**
 * Wire a faked ProcessFileUseCase.execute to return the scripted outcome per
 * filePath (anything unscripted resolves as an ordinary successful ingest).
 */
export function scriptOutcomesByPath(
  execute: {
    mockImplementation(fn: (params: unknown) => Promise<Result<unknown>>): unknown;
  },
  script: Record<string, ScriptedOutcomeKind>,
  defaults: string[] = ['mem-ingested-1'],
): void {
  execute.mockImplementation(async (params: unknown) => {
    const { filePath } = params as { filePath: string };
    const kind = script[filePath] ?? 'ingest';
    return anOutcomeFor(kind, defaults);
  });
}

/** All-zero summary — the expected result of a zero-activity run (C8). */
export const aZeroRunSummary = (): BatchRunSummary => ({
  files: 0,
  gatedSkips: 0,
  terminalSkipSkips: 0,
  verifiedSkips: 0,
  reIngested: 0,
});

/** Info-log lines carrying a per-run summary (format + presence assertions). */
export const summaryLinesFrom = (infoMock: { mock: { calls: unknown[][] } }): string[] =>
  infoMock.mock.calls.map(call => String(call[0])).filter(line => line.includes('finished: files='));

/**
 * Info-log lines carrying a mid-run progress heartbeat (Ad-Hoc Task F).
 * Matches both prefixes ('resume progress:', 'force-reprocess progress:');
 * no other line this service emits contains the leading-space token.
 */
export const heartbeatLinesFrom = (infoMock: { mock: { calls: unknown[][] } }): string[] =>
  infoMock.mock.calls.map(call => String(call[0])).filter(line => line.includes(' progress: '));

/**
 * Build a FileTracker aggregate row for the queue-subtraction seam
 * (T10 / DEC-A7: the resume queue = enumerated files minus any file with a
 * row). Mirrors `recover.service.test.ts`'s local `aTracker` builder: domain
 * aggregates through `FileTracker.of`, returned concrete (props validated).
 * `skipReason` marks a terminal-skip row (a row IS known — queued never);
 * `fileHash: undefined` leaves the row without a stored hash; the queue path
 * never reads hashes (row presence alone decides), which tests pin directly.
 */
export function aFileTrackerRow(
  filePath: string,
  overrides: { skipReason?: FileTrackerSkipReason; fileHash?: string } = {},
): FileTracker {
  return FileTracker.of({
    filePath,
    ...(overrides.skipReason !== undefined ? { skipReason: overrides.skipReason } : {}),
    ...(overrides.fileHash !== undefined ? { fileHash: overrides.fileHash } : {}),
  }).getValue();
}

/**
 * Wire the faked `FileTrackerRepository.findTrackedBySourceId` to return rows
 * for the given file paths (T10 new-files-only queue). Optional `skipOf`
 * marks one path as a terminal-skip row; optional `hashOf` gives one path a
 * stored hash differing from anything the queue could compute.
 */
export function scriptKnownRows(
  findTracked: { mockResolvedValue(value: FileTracker[]): unknown },
  knownPaths: string[],
  opts: { skipOf?: string; hashOf?: string } = {},
): void {
  findTracked.mockResolvedValue(
    knownPaths.map(p =>
      aFileTrackerRow(p, {
        ...(opts.skipOf === p ? { skipReason: 'content-filtered' as const } : {}),
        ...(opts.hashOf === p ? { fileHash: 'stored-hash-differs-from-disk' } : {}),
      }),
    ),
  );
}
