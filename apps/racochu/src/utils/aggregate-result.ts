import { DomainEvent } from './domain-event';
import { ErrorWithDetails } from './error-with-details';

/**
 * AggregateResult is a Result specialization for aggregate root operations.
 * Wraps an aggregate entity with domain events produced during the operation.
 *
 * Pattern: aggregate operations (remember, forget, etc.) return AggregateResult<T>
 * where T is the aggregate root type, carrying both the updated aggregate and events.
 */
export class AggregateResult<T> {
  private constructor(
    private readonly value: T | null,
    private readonly errors: ErrorWithDetails[],
    private readonly events: DomainEvent[],
  ) {}

  static ok<T>(value: T, events: DomainEvent[]): AggregateResult<T> {
    return new AggregateResult(value, [], events);
  }

  static ko<T>(errors: ErrorWithDetails[], events: DomainEvent[] = []): AggregateResult<T> {
    return new AggregateResult<T>(null, errors, events);
  }

  isOk(): this is AggregateResult<NonNullable<T>> {
    return this.errors.length === 0;
  }

  isKo(): boolean {
    return this.errors.length > 0;
  }

  getValue(): T {
    if (this.isKo()) {
      throw new Error('Cannot get value from a Ko AggregateResult');
    }
    return this.value as T;
  }

  getErrors(): ErrorWithDetails[] {
    return this.errors;
  }

  getEvents(): DomainEvent[] {
    return this.events;
  }
}
