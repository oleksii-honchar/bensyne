import { FILE_COMMANDS, FileCommandType, ProcessFileCommand } from './process-file-command';

describe('ProcessFileCommand', () => {
  it('of(path, sourceId) returns ok with correct type', () => {
    const result = ProcessFileCommand.of('/some/path/file.md', 'source-1');

    expect(result.isOk()).toBe(true);
    const cmd = result.getValue();
    expect(cmd.type).toBe(FILE_COMMANDS.PROCESS);
    expect(cmd.path).toBe('/some/path/file.md');
    expect(cmd.sourceId).toBe('source-1');
    expect(cmd.timestamp).toBeInstanceOf(Date);
  });

  it('of("", sourceId) returns ko', () => {
    const result = ProcessFileCommand.of('', 'source-1');

    expect(result.isKo()).toBe(true);
  });

  it('of(path, "") returns ko', () => {
    const result = ProcessFileCommand.of('/some/path/file.md', '');

    expect(result.isKo()).toBe(true);
  });

  it('of(undefined, sourceId) returns ko', () => {
    const result = ProcessFileCommand.of(undefined as unknown as string, 'source-1');

    expect(result.isKo()).toBe(true);
  });
});

describe('FILE_COMMANDS', () => {
  it('has correct type constant', () => {
    expect(FILE_COMMANDS.PROCESS).toBe('process.file');
  });

  it('FileCommandType is union of all values', () => {
    const process: FileCommandType = FILE_COMMANDS.PROCESS;

    expect(process).toBe('process.file');
  });
});
