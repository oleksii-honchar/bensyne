import { DomainEvent as ResultEvent } from './domain-event';
import { ErrorWithDetails } from './error-with-details';

interface Ok<T> {
  value: T;
  errors: never[];
  events: ResultEvent[];
}

interface Ko {
  value: never;
  errors: ErrorWithDetails[];
  events: ResultEvent[];
}

type ResultOf<T> = Ok<T> | Ko;

const ok = <T>(value: T, events: ResultEvent[]): Ok<T> => ({
  value,
  errors: [],
  events,
});

const ko = (errors: ErrorWithDetails[], events: ResultEvent[]): Ko =>
  ({ value: undefined, errors, events }) as Ko;

export class Result<A> {
  private constructor(private readonly result: ResultOf<A>) {}

  static ok<T>(value: T, events: ResultEvent[] = []): Result<T> {
    return new Result(ok(value, events));
  }

  static ko(errors: ErrorWithDetails[], events: ResultEvent[] = []): Result<never> {
    return new Result(ko(errors, events));
  }

  isOk(): this is Ok<A> {
    return this.result.errors.length === 0;
  }

  isKo(): this is Ko {
    return this.result.errors.length > 0;
  }

  hasEvents(): boolean {
    return this.result.events.length > 0;
  }

  getEvents(): ResultEvent[] {
    return this.result.events || [];
  }

  getErrors(): ErrorWithDetails[] {
    return this.result.errors;
  }

  getFormattedErrors(): string {
    return this.result.errors
      .map((e: ErrorWithDetails) => {
        if (typeof e === 'string') return e;
        if (e instanceof Error) return e.message;
        return JSON.stringify(e);
      })
      .join(', ');
  }

  getValue(): A {
    if (this.isKo()) {
      const errorMessages = this.result.errors
        .map(e => {
          if (typeof e === 'string') {
            return e;
          }
          if (e instanceof Error) {
            return e.message;
          }
          return JSON.stringify(e);
        })
        .join(', ');
      throw new Error('Cannot get value from a Ko result: ' + errorMessages);
    }
    return this.result.value;
  }

  /**
   * Function to help mapping the value of the result.
   *
   * @example
   * ```ts
   * const result = Result.ok(1)
   * const result2 = result.map(value => value + 1)
   * console.log(result2.getValue()) // 2
   * ```
   *
   * @example
   * ```ts
   * const result = Result.ko(['error'])
   * const result2 = result.map(value => value + 1)
   * console.log(result2.getErrors()) // ['error']
   * ```
   *
   * @param fn the function to map the value with
   * @returns The function executed inside the result
   */
  map<B>(fn: (value: A) => B): Result<B> {
    if (this.isOk()) {
      return Result.ok(fn(this.result.value));
    }
    return Result.ko(this.result.errors);
  }

  /**
   * Function to help chaining results one after the other.
   *
   * @example
   * ```ts
   * const result = Result.ok(1)
   * const result2 = result.chain(value => Result.ok(value + 1))
   * console.log(result2.getValue()) // 2
   * ```
   *
   * @example
   * ```ts
   * const result = Result.ko(['error'])
   * const result2 = result.chain(value => Result.ok(value + 1))
   * console.log(result2.getErrors()) // ['error']
   * ```
   *
   * @param fn the function to chain the result with
   * @returns The result of the function
   */
  chain<B>(fn: (value: A) => Result<B>): Result<B> {
    if (this.isOk()) {
      return fn(this.result.value);
    }
    return Result.ko(this.result.errors);
  }

  /**
   * Function to help manipulating multiple results into one of arrays. Helpful for parsing multiple objects for instance.
   *
   * @example
   * ```ts
   * const results = [Result.ok(1), Result.ok(2), Result.ok(3)]
   * const result = Result.sequence(results)
   * console.log(result.getValue()) // [1, 2, 3]
   * ```
   *
   * @example
   * ```ts
   * const results = [Result.ok(1), Result.ko('error'), Result.ok(3)]
   * const result = Result.sequence(results)
   * console.log(result.getErrors()) // ['error']
   * ```
   *
   * @param results All results to sequence between them
   * @returns A single result with all the values or the first error
   */
  static sequence<A>(results: Result<A>[]): Result<A[]> {
    const fn = (loopResult: Result<A>[], values: A[]): Result<A[]> => {
      const [head, ...tail] = loopResult;

      if (!head) return Result.ok(values);

      if (head.isKo()) return Result.ko(head.getErrors());

      return fn(tail, [...values, head.getValue()]);
    };

    return fn(results, []);
  }
}
