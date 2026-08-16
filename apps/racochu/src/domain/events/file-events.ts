import { ValuesType } from '@/utils/values-type';
import { DomainEvent } from '../../utils/domain-event';
import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';

export const FILE_EVENTS = {
  ADDED: 'file.added' as const,
  CHANGED: 'file.changed' as const,
  DELETED: 'file.deleted' as const,
} as const;

export type FileEventType = ValuesType<typeof FILE_EVENTS>;

export const FILE_OPERATIONS = {
  ADD: 'add' as const,
  CHANGE: 'change' as const,
  DELETE: 'delete' as const,
} as const;

export type FileOperation = ValuesType<typeof FILE_OPERATIONS>;

export const CHOKIDAR_EVENTS = {
  ADD: 'add' as const,
  CHANGE: 'change' as const,
  UNLINK: 'unlink' as const,
} as const;

export class FileAddedEvent implements DomainEvent {
  readonly type: string;
  readonly timestamp: Date;
  readonly path: string;

  private constructor(path: string) {
    this.type = FILE_EVENTS.ADDED;
    this.path = path;
    this.timestamp = new Date();
  }

  static of(path: string): Result<FileAddedEvent> {
    if (!path || typeof path !== 'string') {
      return Result.ko([new ErrorWithDetails('File path must be a non-empty string', 'InvalidFilePath')]);
    }
    return Result.ok(new FileAddedEvent(path));
  }
}

export class FileChangedEvent implements DomainEvent {
  readonly type: string;
  readonly timestamp: Date;
  readonly path: string;

  private constructor(path: string) {
    this.type = FILE_EVENTS.CHANGED;
    this.path = path;
    this.timestamp = new Date();
  }

  static of(path: string): Result<FileChangedEvent> {
    if (!path || typeof path !== 'string') {
      return Result.ko([new ErrorWithDetails('File path must be a non-empty string', 'InvalidFilePath')]);
    }
    return Result.ok(new FileChangedEvent(path));
  }
}

export class FileDeletedEvent implements DomainEvent {
  readonly type: string;
  readonly timestamp: Date;
  readonly path: string;

  private constructor(path: string) {
    this.type = FILE_EVENTS.DELETED;
    this.path = path;
    this.timestamp = new Date();
  }

  static of(path: string): Result<FileDeletedEvent> {
    if (!path || typeof path !== 'string') {
      return Result.ko([new ErrorWithDetails('File path must be a non-empty string', 'InvalidFilePath')]);
    }
    return Result.ok(new FileDeletedEvent(path));
  }
}
