import { SOURCE_TYPES } from '../infrastructure/config/source-types';
import { WatchSource, WatchSourceProps } from './watch-source.entity';
import { aWatchSource } from './watch-source.entity.test-utils';

describe('WatchSource', () => {
  describe('of()', () => {
    it('with valid props returns ok', () => {
      // Arrange
      const watchSource = aWatchSource();
      const validProps = watchSource.toJson();

      // Act
      const result = WatchSource.of(validProps);

      // Assert
      expect(result.isOk()).toBe(true);
      const resultWs = result.getValue();
      expect(resultWs).toBeInstanceOf(WatchSource);
      expect(resultWs.id).toBe(watchSource.id);
      expect(typeof resultWs.id).toBe('bigint');
    });

    it('with invalid props (negative debounceMs) returns ko', () => {
      // Arrange
      const watchSource = aWatchSource();
      const invalidProps = { ...watchSource.toJson(), debounceMs: -100 };

      // Act
      const result = WatchSource.of(invalidProps);

      // Assert
      expect(result.isKo()).toBe(true);
      expect(result.getErrors()[0].message).toContain('Invalid watch source data');
    });

    it('with invalid id (string instead of bigint) returns ko', () => {
      // Arrange
      const watchSource = aWatchSource();
      const invalidProps = { ...watchSource.toJson(), id: 'test-source-1' as never };

      // Act
      const result = WatchSource.of(invalidProps);

      // Assert
      expect(result.isKo()).toBe(true);
    });

    it('with missing required field returns ko', () => {
      // Arrange
      const watchSource = aWatchSource();
      const invalidProps = { ...watchSource.toJson() } as unknown as WatchSourceProps;
      delete (invalidProps as Partial<WatchSourceProps>).debounceMs;

      // Act
      const result = WatchSource.of(invalidProps);

      // Assert
      expect(result.isKo()).toBe(true);
    });
  });

  describe('toJson()', () => {
    it('returns all props with correct values', () => {
      // Arrange
      const watchSource = aWatchSource();

      // Act
      const json = watchSource.toJson();

      // Assert
      expect(json.id).toBe(watchSource.id);
      expect(json.path).toBe(watchSource.path);
      expect(json.include).toEqual(watchSource.include);
      expect(json.exclude).toEqual(watchSource.exclude);
      expect(json.debounceMs).toBe(watchSource.debounceMs);
      expect(json.ignorePatterns).toEqual(watchSource.ignorePatterns);
      expect(json.sourceType).toBe(watchSource.sourceType);
    });

    it('returns independent copies of arrays', () => {
      // Arrange
      const watchSource = aWatchSource();

      // Act
      const json = watchSource.toJson();

      // Assert
      expect(json.include).not.toBe(watchSource.include);
      expect(json.exclude).not.toBe(watchSource.exclude);
      expect(json.ignorePatterns).not.toBe(watchSource.ignorePatterns);
    });

    it('returned props can recreate the entity', () => {
      // Arrange
      const watchSource = aWatchSource();

      // Act
      const json = watchSource.toJson();
      const result = WatchSource.of(json);

      // Assert
      expect(result.isOk()).toBe(true);
      const recreated = result.getValue();
      expect(recreated.id).toBe(watchSource.id);
      expect(recreated.path).toBe(watchSource.path);
      expect(recreated.include).toEqual(watchSource.include);
      expect(recreated.exclude).toEqual(watchSource.exclude);
      expect(recreated.debounceMs).toBe(watchSource.debounceMs);
      expect(recreated.ignorePatterns).toEqual(watchSource.ignorePatterns);
      expect(recreated.sourceType).toBe(watchSource.sourceType);
    });
  });

  describe('getters', () => {
    it('all getters return correct values', () => {
      // Arrange
      const expectedId = 9876543210987654321n;
      const expectedPath = '/tmp/getters';
      const expectedInclude = ['*.md', '*.txt'];
      const expectedExclude = ['**/archive/**'];
      const expectedDebounceMs = 5000;
      const expectedIgnorePatterns = ['**/.DS_Store', '**/Thumbs.db'];
      const expectedSourceType = SOURCE_TYPES.AGENT_SESSIONS;

      // Act
      const watchSource = aWatchSource({
        id: expectedId,
        path: expectedPath,
        include: expectedInclude,
        exclude: expectedExclude,
        debounceMs: expectedDebounceMs,
        ignorePatterns: expectedIgnorePatterns,
        sourceType: expectedSourceType,
      });

      // Assert
      expect(watchSource.id).toBe(expectedId);
      expect(watchSource.path).toBe(expectedPath);
      expect(watchSource.include).toEqual(expectedInclude);
      expect(watchSource.exclude).toEqual(expectedExclude);
      expect(watchSource.debounceMs).toBe(expectedDebounceMs);
      expect(watchSource.ignorePatterns).toEqual(expectedIgnorePatterns);
      expect(watchSource.sourceType).toBe(expectedSourceType);
    });
  });

  describe('sourceType field (D29: the field IS the source type)', () => {
    it('defaults to vault when not provided (content-aware successor)', () => {
      // Arrange
      const watchSource = aWatchSource();

      // Assert
      expect(watchSource.sourceType).toBe(SOURCE_TYPES.VAULT);
    });

    it.each([SOURCE_TYPES.OBSIDIAN, SOURCE_TYPES.AGENT_SESSIONS, SOURCE_TYPES.VAULT])(
      'accepts explicit D29 source type %s',
      sourceType => {
        const watchSource = aWatchSource({ sourceType });

        expect(watchSource.sourceType).toBe(sourceType);
      },
    );

    it('rejects empty sourceType', () => {
      // Arrange
      const watchSource = aWatchSource();
      const invalidProps = { ...watchSource.toJson(), sourceType: '' as never };

      // Act
      const result = WatchSource.of(invalidProps);

      // Assert
      expect(result.isKo()).toBe(true);
    });

    it('rejects legacy non-D29 source type values (content-aware, file_system)', () => {
      const watchSource = aWatchSource();

      expect(WatchSource.of({ ...watchSource.toJson(), sourceType: 'content-aware' as never }).isKo()).toBe(true);
      expect(WatchSource.of({ ...watchSource.toJson(), sourceType: 'file_system' as never }).isKo()).toBe(true);
    });

    it('toJson includes sourceType', () => {
      // Arrange
      const watchSource = aWatchSource({ sourceType: SOURCE_TYPES.OBSIDIAN });

      // Act
      const json = watchSource.toJson();

      // Assert
      expect(json.sourceType).toBe(SOURCE_TYPES.OBSIDIAN);
    });

    it('toJson round-trip preserves sourceType', () => {
      // Arrange
      const watchSource = aWatchSource({ sourceType: SOURCE_TYPES.AGENT_SESSIONS });

      // Act
      const json = watchSource.toJson();
      const result = WatchSource.of(json);

      // Assert
      expect(result.isOk()).toBe(true);
      expect(result.getValue().sourceType).toBe(SOURCE_TYPES.AGENT_SESSIONS);
    });
  });

  describe('immutability', () => {
    it('entity is immutable', () => {
      // Arrange
      const watchSource = aWatchSource();

      // Act + Assert
      expect(() => {
        (watchSource as { id: bigint }).id = 9999999999999999999n;
      }).toThrow();

      expect(watchSource.id).toBe(watchSource.id);
    });
  });
});
