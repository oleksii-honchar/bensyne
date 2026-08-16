import { z } from 'zod';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';

const fileMemoryTrackerSchema = z.object({
  id: z.bigint(),
  filePath: z.string().min(1),
  memoryIds: z.array(z.string().min(1)),
  sourceId: z.string().min(1),
  memoryBank: z.string().min(1),
});

export type FileMemoryTrackerProps = z.infer<typeof fileMemoryTrackerSchema>;

export class FileMemoryTracker {
  private constructor(private readonly props: FileMemoryTrackerProps) {}

  static of(props: FileMemoryTrackerProps): Result<FileMemoryTracker> {
    const parsed = fileMemoryTrackerSchema.safeParse(props);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails(
          'Invalid FileMemoryTracker data: ' + parsed.error.message,
          'InvalidFileMemoryTracker',
        ),
      ]);
    }
    return Result.ok(new FileMemoryTracker(parsed.data), []);
  }

  remember(memoryId: string): Result<FileMemoryTracker> {
    if (!memoryId || memoryId.trim().length === 0) {
      return Result.ko([new ErrorWithDetails('memoryId cannot be empty', 'EmptyMemoryId')]);
    }

    if (this.props.memoryIds.includes(memoryId)) {
      return Result.ok(this, []);
    }

    return FileMemoryTracker.of({
      ...this.props,
      memoryIds: [...this.props.memoryIds, memoryId],
    });
  }

  forget(memoryId: string): Result<FileMemoryTracker> {
    const filtered = this.props.memoryIds.filter(id => id !== memoryId);

    if (filtered.length === this.props.memoryIds.length) {
      return Result.ok(this, []);
    }

    return FileMemoryTracker.of({
      ...this.props,
      memoryIds: filtered,
    });
  }

  /**
   * Forget multiple memory IDs at once.
   * Returns the same tracker if none of the IDs were present.
   */
  forgetMany(memoryIds: string[]): Result<FileMemoryTracker> {
    const filtered = this.props.memoryIds.filter(id => !memoryIds.includes(id));

    if (filtered.length === this.props.memoryIds.length) {
      return Result.ok(this, []);
    }

    return FileMemoryTracker.of({
      ...this.props,
      memoryIds: filtered,
    });
  }

  get id(): bigint {
    return this.props.id;
  }

  get filePath(): string {
    return this.props.filePath;
  }

  get memoryIds(): string[] {
    return this.props.memoryIds;
  }

  get sourceId(): string {
    return this.props.sourceId;
  }

  get memoryBank(): string {
    return this.props.memoryBank;
  }

  toJson(): FileMemoryTrackerProps {
    return {
      id: this.props.id,
      filePath: this.props.filePath,
      memoryIds: [...this.props.memoryIds],
      sourceId: this.props.sourceId,
      memoryBank: this.props.memoryBank,
    };
  }

  empty(): Result<FileMemoryTracker> {
    return Result.ok(new FileMemoryTracker({} as FileMemoryTrackerProps), []);
  }
}
