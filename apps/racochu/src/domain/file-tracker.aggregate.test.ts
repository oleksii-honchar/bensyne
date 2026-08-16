import { FILE_EVENTS, FileAddedEvent, FileChangedEvent, FileDeletedEvent } from './events/file-events';
import { FILE_TRACKER_STATUS, FileTracker, FileTrackerProps } from './file-tracker.aggregate';
import { aFileTracker } from './file-tracker.aggregate.test-utils';

describe('FileTracker', () => {
  describe('instance add', () => {
    it('transitions to ADDED status and emits FileAddedEvent in AggregateResult', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();
      expect(added.filePath).toBe('/test/file.txt');
      expect(added.status).toBe(FILE_TRACKER_STATUS.ADDED);
      const events = addResult.getEvents();
      expect(events).toHaveLength(1);
      expect(events[0]).toBeInstanceOf(FileAddedEvent);
      expect((events[0] as FileAddedEvent).type).toBe(FILE_EVENTS.ADDED);
      expect((events[0] as FileAddedEvent).path).toBe('/test/file.txt');
    });
  });

  describe('instance change', () => {
    it('transitions to CHANGED status and emits FileChangedEvent in AggregateResult', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();

      const changeResult = added.change();
      expect(changeResult.isOk()).toBe(true);
      const changed = changeResult.getValue();
      expect(changed.filePath).toBe('/test/file.txt');
      expect(changed.status).toBe(FILE_TRACKER_STATUS.CHANGED);
      const events = changeResult.getEvents();
      expect(events).toHaveLength(1);
      expect(events[0]).toBeInstanceOf(FileChangedEvent);
      expect((events[0] as FileChangedEvent).type).toBe(FILE_EVENTS.CHANGED);
    });

    it('original aggregate remains unchanged after change', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();
      expect(added.status).toBe(FILE_TRACKER_STATUS.ADDED);

      const changeResult = added.change();
      expect(changeResult.isOk()).toBe(true);
      // Original aggregate is immutable
      expect(added.status).toBe(FILE_TRACKER_STATUS.ADDED);
    });
  });

  describe('instance delete', () => {
    it('transitions to DELETED status and emits FileDeletedEvent in AggregateResult', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();

      const deleteResult = added.delete();
      expect(deleteResult.isOk()).toBe(true);
      const deleted = deleteResult.getValue();
      expect(deleted.filePath).toBe('/test/file.txt');
      expect(deleted.status).toBe(FILE_TRACKER_STATUS.DELETED);
      const events = deleteResult.getEvents();
      expect(events).toHaveLength(1);
      expect(events[0]).toBeInstanceOf(FileDeletedEvent);
      expect((events[0] as FileDeletedEvent).type).toBe(FILE_EVENTS.DELETED);
    });

    it('original aggregate remains unchanged after delete', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();
      expect(added.status).toBe(FILE_TRACKER_STATUS.ADDED);

      const deleteResult = added.delete();
      expect(deleteResult.isOk()).toBe(true);
      // Original aggregate is immutable
      expect(added.status).toBe(FILE_TRACKER_STATUS.ADDED);
    });
  });

  describe('static of', () => {
    it('creates FileTracker with just filePath — status is null until add()', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      expect(fileTracker.filePath).toBe('/test/file.txt');
      expect(fileTracker.status).toBeNull();
    });

    it('returns ko for empty filePath', () => {
      const props: FileTrackerProps = { filePath: '' };
      const result = FileTracker.of(props);
      expect(result.isKo()).toBe(true);
    });

    it('returns ko for missing filePath', () => {
      const props = {} as FileTrackerProps;
      const result = FileTracker.of(props);
      expect(result.isKo()).toBe(true);
    });
  });

  describe('toJson', () => {
    it('serializes filePath and status without events', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();

      const json = added.toJson();
      expect(json).toEqual({
        filePath: '/test/file.txt',
        status: FILE_TRACKER_STATUS.ADDED,
      });
    });
  });

  describe('status enum', () => {
    it('has ADDED, CHANGED, and DELETED values', () => {
      expect(FILE_TRACKER_STATUS.ADDED).toBe('added');
      expect(FILE_TRACKER_STATUS.CHANGED).toBe('changed');
      expect(FILE_TRACKER_STATUS.DELETED).toBe('deleted');
    });
  });

  describe('fileHash and hardwareId', () => {
    it('accepts fileHash and hardwareId in of()', () => {
      const props = aFileTracker({ fileHash: 'abc123', hardwareId: 'hw-456' });
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();
      expect(fileTracker.fileHash).toBe('abc123');
      expect(fileTracker.hardwareId).toBe('hw-456');
    });

    it('returns null for fileHash and hardwareId when not provided', () => {
      const props = aFileTracker();
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();
      expect(fileTracker.fileHash).toBeNull();
      expect(fileTracker.hardwareId).toBeNull();
    });

    it('returns null for fileHash and hardwareId when undefined', () => {
      const props = aFileTracker({ fileHash: undefined, hardwareId: undefined });
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();
      expect(fileTracker.fileHash).toBeNull();
      expect(fileTracker.hardwareId).toBeNull();
    });

    it('includes fileHash and hardwareId in toJson()', () => {
      const props = aFileTracker({ fileHash: 'abc123', hardwareId: 'hw-456' });
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();
      const json = fileTracker.toJson();
      expect(json.fileHash).toBe('abc123');
      expect(json.hardwareId).toBe('hw-456');
    });

    it('preserves fileHash and hardwareId through add/change/delete', () => {
      const props = aFileTracker({ fileHash: 'abc123', hardwareId: 'hw-456' });
      const result = FileTracker.of(props);
      expect(result.isOk()).toBe(true);
      const fileTracker = result.getValue();

      const addResult = fileTracker.add();
      expect(addResult.isOk()).toBe(true);
      const added = addResult.getValue();
      expect(added.fileHash).toBe('abc123');
      expect(added.hardwareId).toBe('hw-456');

      const changeResult = added.change();
      expect(changeResult.isOk()).toBe(true);
      const changed = changeResult.getValue();
      expect(changed.fileHash).toBe('abc123');
      expect(changed.hardwareId).toBe('hw-456');

      const deleteResult = changed.delete();
      expect(deleteResult.isOk()).toBe(true);
      const deleted = deleteResult.getValue();
      expect(deleted.fileHash).toBe('abc123');
      expect(deleted.hardwareId).toBe('hw-456');
    });
  });
});
