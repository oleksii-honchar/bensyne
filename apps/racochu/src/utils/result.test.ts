import { ErrorWithDetails } from './error-with-details';
import { Result } from './result';

describe('Result', () => {
  describe('static methods', () => {
    it('should create an Ok result with a value and no errors', () => {
      const value = 'test';
      const result = Result.ok(value);
      expect(result.isOk()).toBe(true);
      expect(result.isKo()).toBe(false);
      expect(result.getValue()).toBe(value);
      expect(result.getErrors()).toEqual([]);
    });

    it('should create a Ko result with ErrorWithDetails errors and no value', () => {
      const errors = [new ErrorWithDetails('error1', 'Error1'), new ErrorWithDetails('error2', 'Error2')];
      const result = Result.ko(errors);
      expect(result.isOk()).toBe(false);
      expect(result.isKo()).toBe(true);
      expect(result.getErrors()).toEqual(errors);
      expect(() => result.getValue()).toThrow();
    });

    it('should create a single result with all the values of multiple results when using sequence', () => {
      const results = [Result.ok(1), Result.ok(2), Result.ok(3)];
      const result = Result.sequence(results);
      expect(result.isOk()).toBe(true);
      expect(result.getValue()).toEqual([1, 2, 3]);
    });

    it('should create a single result with the first error of multiple results when using sequence', () => {
      const errors = [new ErrorWithDetails('error', 'SeqError')];
      const results = [Result.ok(1), Result.ko(errors), Result.ok(3)];
      const result = Result.sequence(results);
      expect(result.isKo()).toBe(true);
      expect(result.getErrors()).toEqual(errors);
    });
  });

  describe('instance methods', () => {
    it('isOk should return true for an Ok result', () => {
      const result = Result.ok('test');
      expect(result.isOk()).toBe(true);
      expect(result.isKo()).toBe(false);
    });

    it('isKo should return true for a Ko result', () => {
      const errors = [new ErrorWithDetails('error', 'TestError')];
      const result = Result.ko(errors);
      expect(result.isKo()).toBe(true);
      expect(result.isOk()).toBe(false);
    });

    it('getErrors should return the correct errors', () => {
      const errors = [new ErrorWithDetails('error1', 'Error1'), new ErrorWithDetails('error2', 'Error2')];
      const result = Result.ko(errors);
      expect(result.getErrors()).toEqual(errors);
    });

    it('getValue should return the correct value', () => {
      const value = 'test';
      const result = Result.ok(value);
      expect(result.getValue()).toBe(value);
    });

    it('should map the value of an Ok result', () => {
      const result = Result.ok(1);
      const mappedResult = result.map(value => value * 2);
      expect(mappedResult.isOk()).toBe(true);
      expect(mappedResult.getValue()).toBe(2);
    });

    it('should return a Ko result if we try to map a Ko result', () => {
      const errors = [new ErrorWithDetails('error', 'MapError')];
      const result: Result<number> = Result.ko(errors);
      const mappedResult = result.map(value => value + 1);
      expect(mappedResult.isKo()).toBe(true);
      expect(mappedResult.getErrors()).toEqual(errors);
    });

    it('should chain the value of an Ok result', () => {
      const result = Result.ok(1);
      const mappedResult = result.chain(value => Result.ok(value * 2));
      expect(mappedResult.isOk()).toBe(true);
      expect(mappedResult.getValue()).toBe(2);
    });

    it('should return a Ko result if the chain function returns a Ko result or we try to chain a Ko result', () => {
      const errors = [new ErrorWithDetails('error', 'ChainError')];
      const result: Result<number> = Result.ko(errors);
      const mappedResult = result.chain(value => Result.ok(value + 1));
      expect(mappedResult.isKo()).toBe(true);
      expect(mappedResult.getErrors()).toEqual(errors);

      const errors2 = [new ErrorWithDetails('error2', 'ChainError2')];
      const result2: Result<number> = Result.ok(1);
      const mappedResult2 = result2.chain(() => Result.ko(errors2));
      expect(mappedResult2.isKo()).toBe(true);
      expect(mappedResult2.getErrors()).toEqual(errors2);
    });
  });
});
