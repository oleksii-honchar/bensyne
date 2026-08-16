import {
  FILE_EVENTS,
  FileAddedEvent,
  FileChangedEvent,
  FileDeletedEvent,
  FileEventType,
} from './file-events';

describe('FileAddedEvent', () => {
  it('of(validPath) returns ok with correct type', () => {
    const result = FileAddedEvent.of('/some/path/file.md');

    expect(result.isOk()).toBe(true);
    const event = result.getValue();
    expect(event.type).toBe(FILE_EVENTS.ADDED);
    expect(event.path).toBe('/some/path/file.md');
    expect(event.timestamp).toBeInstanceOf(Date);
  });

  it('of("") returns ko', () => {
    const result = FileAddedEvent.of('');

    expect(result.isKo()).toBe(true);
  });

  it('of(null) returns ko', () => {
    const result = FileAddedEvent.of(null as unknown as string);

    expect(result.isKo()).toBe(true);
  });
});

describe('FileChangedEvent', () => {
  it('of(validPath) returns ok with correct type', () => {
    const result = FileChangedEvent.of('/some/path/file.md');

    expect(result.isOk()).toBe(true);
    const event = result.getValue();
    expect(event.type).toBe(FILE_EVENTS.CHANGED);
    expect(event.path).toBe('/some/path/file.md');
    expect(event.timestamp).toBeInstanceOf(Date);
  });

  it('of(null) returns ko', () => {
    const result = FileChangedEvent.of(null as unknown as string);

    expect(result.isKo()).toBe(true);
  });
});

describe('FileDeletedEvent', () => {
  it('of(validPath) returns ok with correct type', () => {
    const result = FileDeletedEvent.of('/some/path/file.md');

    expect(result.isOk()).toBe(true);
    const event = result.getValue();
    expect(event.type).toBe(FILE_EVENTS.DELETED);
    expect(event.path).toBe('/some/path/file.md');
    expect(event.timestamp).toBeInstanceOf(Date);
  });

  it('of("") returns ko', () => {
    const result = FileDeletedEvent.of('');

    expect(result.isKo()).toBe(true);
  });
});

describe('FILE_EVENTS', () => {
  it('has correct type constants', () => {
    expect(FILE_EVENTS.ADDED).toBe('file.added');
    expect(FILE_EVENTS.CHANGED).toBe('file.changed');
    expect(FILE_EVENTS.DELETED).toBe('file.deleted');
  });

  it('FileEventType is union of all values', () => {
    const added: FileEventType = FILE_EVENTS.ADDED;
    const changed: FileEventType = FILE_EVENTS.CHANGED;
    const deleted: FileEventType = FILE_EVENTS.DELETED;

    expect(added).toBe('file.added');
    expect(changed).toBe('file.changed');
    expect(deleted).toBe('file.deleted');
  });
});
