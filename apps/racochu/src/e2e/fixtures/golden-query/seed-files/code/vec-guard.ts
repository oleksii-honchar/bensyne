/**
 * Vector dimension mismatch guard for Mnemosyne vec0 tables.
 *
 * When the embedding model is switched (e.g. 384 → 2560), the vec0
 * table schema expects the new dimension. This guard detects the
 * mismatch and falls back to keyword search via the beam parameter.
 */

import { Logger } from '@nestjs/common';

const logger = new Logger('VecGuard');

export class VecDimensionGuard {
  private readonly expectedDim: number;

  constructor(expectedDim: number) {
    this.expectedDim = expectedDim;
  }

  /**
   * Checks if the current vec0 table dimension matches the expected
   * embedding dimension. Returns true if there is a dimension mismatch.
   */
  checkDimension(currentDim: number): boolean {
    if (currentDim !== this.expectedDim) {
      logger.warn(
        `Dimension mismatch detected: expected ${this.expectedDim}, got ${currentDim}. Falling back to keyword search.`,
      );
      return true;
    }
    return false;
  }

  /**
   * When a dimension mismatch is detected, the recall query should
   * use beam search (keyword fallback) instead of vector search.
   * Sets beam to a positive value to trigger keyword search.
   */
  buildFallbackParams(): { beam: number } {
    return { beam: 10 };
  }
}
