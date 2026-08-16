/**
 * Domain event base interface.
 */

export interface DomainEvent {
  readonly type: string;
  readonly timestamp: Date;
}
