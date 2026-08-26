import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { UserConfig } from './config-schemas';

/**
 * Exactly-one user-source invariant (ADR-1, spec §2.1): Racochu serves exactly
 * one user per host. The `user` config section declares that user; a host must
 * declare exactly one user source — zero or multiple is a startup rejection.
 *
 * The check is modeled as an explicit count over the declared user sources so
 * the "exactly one" contract is testable on all three branches (0, 1, >1).
 */
export function validateUserSources(userSources: UserConfig[]): Result<UserConfig> {
  if (userSources.length === 0) {
    return Result.ko([
      new ErrorWithDetails(
        'Racochu requires exactly one user source per host, but none is declared. ' +
          'Add a `user` section to your racochu config, e.g.:\n' +
          '  user:\n' +
          '    id: <your-stable-user-id>\n' +
          '    bank: user_<id>   # optional, defaults to user_<id>',
        'NoUserSourceDeclared',
      ),
    ]);
  }

  if (userSources.length > 1) {
    return Result.ko([
      new ErrorWithDetails(
        `Racochu requires exactly one user source per host, but ${userSources.length} are declared ` +
          `(${userSources.map(s => `id="${s.id}"`).join(', ')}). Remove all but one.`,
        'MultipleUserSourcesDeclared',
      ),
    ]);
  }

  return Result.ok(userSources[0]);
}
