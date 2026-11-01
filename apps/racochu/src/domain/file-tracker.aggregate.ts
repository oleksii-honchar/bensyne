import { ValuesType } from '@/utils/values-type';
import { z } from 'zod';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';
import { FileAddedEvent, FileChangedEvent, FileDeletedEvent } from './events/file-events';

/**
 * File tracker status — tracks the current state of a tracked file.
 */
export const FILE_TRACKER_STATUS = {
  ADDED: 'added' as const,
  CHANGED: 'changed' as const,
  DELETED: 'deleted' as const,
} as const;

export type FileTrackerStatus = ValuesType<typeof FILE_TRACKER_STATUS>;

/**
 * Terminal skip reasons — set on a FileTracker row when a file can never be
 * ingested with its current content. Mirrors the nullable `skipReason` column.
 */
export const FILE_TRACKER_SKIP_REASON = {
  CONTENT_FILTERED: 'content-filtered' as const,
  EMPTY_CONTENT: 'empty-content' as const,
  ZERO_CHUNKS: 'zero-chunks' as const,
} as const;

export type FileTrackerSkipReason = ValuesType<typeof FILE_TRACKER_SKIP_REASON>;

const fileTrackerSchema = z.object({
  filePath: z.string().min(1),
  status: z.enum(Object.values(FILE_TRACKER_STATUS)).nullish(),
  fileHash: z.string().optional(),
  hardwareId: z.string().optional(),
  skipReason: z.enum(Object.values(FILE_TRACKER_SKIP_REASON)).nullish(),
});

export type FileTrackerProps = z.infer<typeof fileTrackerSchema>;

/**
 * File tracker aggregate.
 *
 * Invariant: "A FileTracker row means: racochu has seen this exact content hash
 * and reached a final decision about it — ingested (memories tracked, skipReason
 * null) or terminally skipped (skipReason set, zero memories)."
 *
 * No state machine is added for skip rows: they are cleared/refreshed by a hash
 * mismatch during normal processing, not by a status transition.
 */
export class FileTracker {
  private constructor(private readonly props: FileTrackerProps) {}

  /**
   * Create a file tracker from props, validating via zod schema. Returns Result.
   */
  static of(props: FileTrackerProps): Result<FileTracker> {
    const parsed = fileTrackerSchema.safeParse(props);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails('Invalid file tracker data: ' + parsed.error.message, 'InvalidFileTracker'),
      ]);
    }
    return Result.ok(new FileTracker(parsed.data));
  }

  /**
   * Transition to ADDED status and emit FileAddedEvent.
   */
  add(): Result<FileTracker> {
    const eventResult = FileAddedEvent.of(this.props.filePath);
    if (eventResult.isKo()) {
      return Result.ko(eventResult.getErrors());
    }
    const event = eventResult.getValue();
    const added = new FileTracker({ ...this.props, status: FILE_TRACKER_STATUS.ADDED });
    return Result.ok(added, [event]);
  }

  /**
   * Transition to CHANGED status and emit FileChangedEvent.
   */
  change(): Result<FileTracker> {
    const eventResult = FileChangedEvent.of(this.props.filePath);
    if (eventResult.isKo()) {
      return Result.ko(eventResult.getErrors());
    }
    const event = eventResult.getValue();
    const changed = new FileTracker({ ...this.props, status: FILE_TRACKER_STATUS.CHANGED });
    return Result.ok(changed, [event]);
  }

  /**
   * Transition to DELETED status and emit FileDeletedEvent.
   */
  delete(): Result<FileTracker> {
    const eventResult = FileDeletedEvent.of(this.props.filePath);
    if (eventResult.isKo()) {
      return Result.ko(eventResult.getErrors());
    }
    const event = eventResult.getValue();
    const deleted = new FileTracker({ ...this.props, status: FILE_TRACKER_STATUS.DELETED });
    return Result.ok(deleted, [event]);
  }

  get filePath(): string {
    return this.props.filePath;
  }

  get status(): FileTrackerStatus | null | undefined {
    return this.props.status ?? null;
  }

  get fileHash(): string | null {
    return this.props.fileHash ?? null;
  }

  get hardwareId(): string | null {
    return this.props.hardwareId ?? null;
  }

  get skipReason(): FileTrackerSkipReason | null {
    return this.props.skipReason ?? null;
  }

  toJson(): FileTrackerProps {
    return {
      filePath: this.props.filePath,
      status: this.props.status,
      fileHash: this.props.fileHash,
      hardwareId: this.props.hardwareId,
    };
  }
}
