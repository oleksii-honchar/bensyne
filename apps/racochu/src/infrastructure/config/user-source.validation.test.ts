import { ErrorWithDetails } from '../../utils/error-with-details';
import { Result } from '../../utils/result';
import { UserConfig } from './config-schemas';
import { validateUserSources } from './user-source.validation';

const aUserConfig = (overrides: Partial<UserConfig> = {}): UserConfig => ({
  id: 'oleksii',
  bank: 'user_oleksii',
  ...overrides,
});

describe('validateUserSources — exactly-one user source per host (ADR-1)', () => {
  it('rejects 0 user sources with a clear "exactly one" error', () => {
    const result = validateUserSources([]);

    expect(result.isKo()).toBe(true);
    const formatted = result.getFormattedErrors();
    expect(formatted).toContain('exactly one user source');
    expect(formatted).toContain('user');
    expect((result.getErrors()[0] as ErrorWithDetails).code).toBe('NoUserSourceDeclared');
  });

  it('accepts exactly 1 user source and returns it', () => {
    const user = aUserConfig();

    const result = validateUserSources([user]);

    expect(result.isOk()).toBe(true);
    expect(result.getValue()).toBe(user);
  });

  it('rejects >1 user sources with a clear "exactly one" error', () => {
    const result = validateUserSources([
      aUserConfig({ id: 'oleksii', bank: 'user_oleksii' }),
      aUserConfig({ id: 'other', bank: 'user_other' }),
    ]);

    expect(result.isKo()).toBe(true);
    const formatted = result.getFormattedErrors();
    expect(formatted).toContain('exactly one user source');
    expect(formatted).toContain('2');
    expect((result.getErrors()[0] as ErrorWithDetails).code).toBe('MultipleUserSourcesDeclared');
  });

  it('is a pure function returning a Result (no throwing)', () => {
    expect(validateUserSources([])).toBeInstanceOf(Result);
    expect(() => validateUserSources([])).not.toThrow();
  });
});
