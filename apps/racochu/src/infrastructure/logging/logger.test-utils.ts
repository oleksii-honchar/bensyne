import { BasePinoLogger } from './base-pino-logger';

export function aLogger(overrides: Partial<jest.Mocked<BasePinoLogger>> = {}): jest.Mocked<BasePinoLogger> {
  const mock = {
    setContext: jest.fn(),
    log: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
    warn: jest.fn(),
    debug: jest.fn(),
    child: jest.fn().mockReturnThis(),
    ...overrides,
  } as unknown as jest.Mocked<BasePinoLogger>;

  return mock;
}
