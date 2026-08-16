import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { ValuesType } from '../../utils/values-type';

export interface DomainCommand {
  readonly type: string;
  readonly timestamp: Date;
}

export const FILE_COMMANDS = {
  PROCESS: 'process.file' as const,
} as const;

export type FileCommandType = ValuesType<typeof FILE_COMMANDS>;

export class ProcessFileCommand implements DomainCommand {
  readonly type: string;
  readonly timestamp: Date;
  readonly path: string;
  readonly sourceId: string;

  private constructor(path: string, sourceId: string) {
    this.type = FILE_COMMANDS.PROCESS;
    this.path = path;
    this.sourceId = sourceId;
    this.timestamp = new Date();
  }

  static of(path: string, sourceId: string): Result<ProcessFileCommand> {
    if (!path || !sourceId) {
      return Result.ko([new ErrorWithDetails('Path and sourceId are required', 'InvalidProcessFileCommand')]);
    }
    return Result.ok(new ProcessFileCommand(path, sourceId));
  }
}
