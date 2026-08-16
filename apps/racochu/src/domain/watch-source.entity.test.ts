import { SOURCE_STRATEGIES } from '../infrastructure/config/source-strategies';
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
      expect(json.strategy).toBe(watchSource.strategy);
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
      expect(recreated.strategy).toBe(watchSource.strategy);
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
      const expectedStrategy = SOURCE_STRATEGIES.AGENT_SESSIONS;

      // Act
      const watchSource = aWatchSource({
        id: expectedId,
        path: expectedPath,
        include: expectedInclude,
        exclude: expectedExclude,
        debounceMs: expectedDebounceMs,
        ignorePatterns: expectedIgnorePatterns,
        strategy: expectedStrategy,
      });

      // Assert
      expect(watchSource.id).toBe(expectedId);
      expect(watchSource.path).toBe(expectedPath);
      expect(watchSource.include).toEqual(expectedInclude);
      expect(watchSource.exclude).toEqual(expectedExclude);
      expect(watchSource.debounceMs).toBe(expectedDebounceMs);
      expect(watchSource.ignorePatterns).toEqual(expectedIgnorePatterns);
      expect(watchSource.strategy).toBe(expectedStrategy);
    });
  });

  describe('strategy field', () => {
    it('defaults to content-aware when not provided', () => {
      // Arrange
      const watchSource = aWatchSource();

      // Assert
      expect(watchSource.strategy).toBe(SOURCE_STRATEGIES.CONTENT_AWARE);
    });

    it('accepts explicit strategy value', () => {
      // Arrange
      const watchSource = aWatchSource({ strategy: SOURCE_STRATEGIES.AGENT_SESSIONS });

      // Assert
      expect(watchSource.strategy).toBe(SOURCE_STRATEGIES.AGENT_SESSIONS);
    });

    it('rejects empty strategy', () => {
      // Arrange
      const watchSource = aWatchSource();
      const invalidProps = { ...watchSource.toJson(), strategy: '' as any };

      // Act
      const result = WatchSource.of(invalidProps);

      // Assert
      expect(result.isKo()).toBe(true);
    });

    it('toJson includes strategy', () => {
      // Arrange
      const watchSource = aWatchSource({ strategy: SOURCE_STRATEGIES.OBSIDIAN });

      // Act
      const json = watchSource.toJson();

      // Assert
      expect(json.strategy).toBe(SOURCE_STRATEGIES.OBSIDIAN);
    });

    it('toJson round-trip preserves strategy', () => {
      // Arrange
      const watchSource = aWatchSource({ strategy: SOURCE_STRATEGIES.AGENT_SESSIONS });

      // Act
      const json = watchSource.toJson();
      const result = WatchSource.of(json);

      // Assert
      expect(result.isOk()).toBe(true);
      expect(result.getValue().strategy).toBe(SOURCE_STRATEGIES.AGENT_SESSIONS);
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
