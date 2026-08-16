/**
 * Custom error class with optional code and metadata.
 * Pattern copied from voqaria typescript-common.
 */

export type StringIndex = Record<string, string>;

export class ErrorWithDetails extends Error {
  constructor(
    public override readonly message: string,
    public readonly code?: string,
    public readonly data?: StringIndex,
  ) {
    super(message);
  }

  static of(error: Error): ErrorWithDetails {
    return new ErrorWithDetails(error.message, 'ErrorWithDetails', { error: error.message });
  }
}
