import { z } from 'zod';
import { SOURCE_TYPES } from '../infrastructure/config/source-types';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';

export const watchSourceEntitySchema = z.object({
  id: z.bigint().positive(),
  path: z.string(),
  include: z.array(z.string()),
  exclude: z.array(z.string()),
  debounceMs: z.number().positive(),
  ignorePatterns: z.array(z.string()),
  // D29: the field IS the source type (default vault, the content-aware successor).
  sourceType: z.enum(Object.values(SOURCE_TYPES) as [string, ...string[]]).default(SOURCE_TYPES.VAULT),
});

export type WatchSourceProps = z.infer<typeof watchSourceEntitySchema>;

export class WatchSource {
  private constructor(private readonly props: WatchSourceProps) {}

  static of(props: WatchSourceProps): Result<WatchSource> {
    const parsed = watchSourceEntitySchema.safeParse(props);
    if (!parsed.success) {
      return Result.ko([
        new ErrorWithDetails('Invalid watch source data: ' + parsed.error.message, 'InvalidWatchSource'),
      ]);
    }
    return Result.ok(new WatchSource(parsed.data), []);
  }

  toJson(): WatchSourceProps {
    return {
      id: this.props.id,
      path: this.props.path,
      include: [...this.props.include],
      exclude: [...this.props.exclude],
      debounceMs: this.props.debounceMs,
      ignorePatterns: [...this.props.ignorePatterns],
      sourceType: this.props.sourceType,
    };
  }

  get id(): bigint {
    return this.props.id;
  }
  get path(): string {
    return this.props.path;
  }
  get include(): string[] {
    return this.props.include;
  }
  get exclude(): string[] {
    return this.props.exclude;
  }
  get debounceMs(): number {
    return this.props.debounceMs;
  }
  get ignorePatterns(): string[] {
    return this.props.ignorePatterns;
  }
  get sourceType(): string {
    return this.props.sourceType;
  }
}
