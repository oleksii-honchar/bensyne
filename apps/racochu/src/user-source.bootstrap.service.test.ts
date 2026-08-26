import { UserConfig } from './infrastructure/config/config-schemas';
import { BasePinoLogger } from './infrastructure/logging/base-pino-logger';
import { aLogger } from './infrastructure/logging/logger.test-utils';
import { UserSourceBootstrapService } from './user-source.bootstrap.service';
import { Result } from './utils/result';

// Mock chokidar (CJS interop under ESM VM modules — same pattern as configuration.service.test.ts)
jest.mock('chokidar', () => ({
  watch: jest.fn(() => ({
    on: jest.fn(),
    close: jest.fn().mockResolvedValue(undefined),
  })),
}));

const aUserConfig = (overrides: Partial<UserConfig> = {}): UserConfig => ({
  id: 'oleksii',
  bank: 'user_oleksii',
  ...overrides,
});

const okResult = Result.ok(undefined as unknown as void);

interface TestContext {
  service: UserSourceBootstrapService;
  getUserConfig: jest.Mock;
  initialize: jest.Mock;
  registerBank: jest.Mock;
  logger: BasePinoLogger;
}

const buildService = (userConfig: UserConfig | undefined): TestContext => {
  const getUserConfig = jest.fn().mockReturnValue(userConfig);
  const configService = { getUserConfig } as never;
  const initialize = jest.fn().mockResolvedValue(okResult);
  const registerBank = jest.fn().mockResolvedValue(okResult);
  const bensyneClient = { initialize, registerBank } as never;
  const logger = aLogger();
  const service = new UserSourceBootstrapService(configService, bensyneClient, logger);
  return { service, getUserConfig, initialize, registerBank, logger };
};

describe('UserSourceBootstrapService — exactly-one user source + user bank ensure at startup', () => {
  it('rejects startup when 0 user sources are declared (user section missing)', async () => {
    const { service } = buildService(undefined);

    await expect(service.onApplicationBootstrap()).rejects.toThrow(/exactly one user source/);
    expect(service['bensyneClient'].registerBank).not.toHaveBeenCalled();
  });

  it('rejects startup with a clear error when >1 user sources are declared', async () => {
    const { service } = buildService(aUserConfig());

    await expect(
      service.bootstrapUserSources([
        aUserConfig({ id: 'oleksii', bank: 'user_oleksii' }),
        aUserConfig({ id: 'other', bank: 'user_other' }),
      ]),
    ).rejects.toThrow(/exactly one user source/);
  });

  it('bootstraps with exactly one user source and ensures the resolved user bank', async () => {
    const { service, registerBank, initialize } = buildService(aUserConfig());

    await service.onApplicationBootstrap();

    expect(initialize).toHaveBeenCalled();
    expect(registerBank).toHaveBeenCalledTimes(1);
    expect(registerBank).toHaveBeenCalledWith('user_oleksii', expect.stringContaining('oleksii'));
  });

  it('respects the explicit user.bank override (no re-derivation)', async () => {
    const { service, registerBank } = buildService(aUserConfig({ bank: 'custom-user-bank' }));

    await service.onApplicationBootstrap();

    expect(registerBank).toHaveBeenCalledWith('custom-user-bank', expect.any(String));
  });

  it('initializes the MCP client before registering the user bank', async () => {
    const { service, initialize, registerBank } = buildService(aUserConfig());
    const callOrder: string[] = [];
    initialize.mockImplementation(async () => {
      callOrder.push('initialize');
      return okResult;
    });
    registerBank.mockImplementation(async () => {
      callOrder.push('registerBank');
      return okResult;
    });

    await service.onApplicationBootstrap();

    expect(callOrder.indexOf('initialize')).toBeLessThan(callOrder.indexOf('registerBank'));
  });

  it('logs a warning (does not crash) when user bank registration fails, matching watch-source pattern', async () => {
    const { service, registerBank } = buildService(aUserConfig());
    registerBank.mockResolvedValue(Result.ko([new Error('MCP unavailable') as never]));

    await expect(service.onApplicationBootstrap()).resolves.not.toThrow();
    expect(registerBank).toHaveBeenCalledTimes(1);
  });
});
