import { z } from 'zod';
import { SOURCE_STRATEGIES } from '../infrastructure/config/source-strategies';
import { ErrorWithDetails } from '../utils/error-with-details';
import { Result } from '../utils/result';

export const watchSourceEntitySchema = z.object({
  id: z.bigint().positive(),
  path: z.string(),
  include: z.array(z.string()),
  exclude: z.array(z.string()),
  debounceMs: z.number().positive(),
  ignorePatterns: z.array(z.string()),
  strategy: z.enum(Object.values(SOURCE_STRATEGIES)).default(SOURCE_STRATEGIES.CONTENT_AWARE),
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
      strategy: this.props.strategy,
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
  get strategy(): string {
    return this.props.strategy;
  }
}
