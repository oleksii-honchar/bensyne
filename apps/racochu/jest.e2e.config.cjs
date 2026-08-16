module.exports = {
  preset: 'ts-jest',
  moduleFileExtensions: ['js', 'json', 'ts'],
  rootDir: '.',
  testRegex: 'src/e2e/.*\\.test\\.ts$',
  collectCoverageFrom: ['src/**/*.ts'],
  coverageDirectory: 'coverage-e2e',
  testEnvironment: 'node',
  globalSetup: '<rootDir>/src/e2e/global-setup.ts',
  globalTeardown: '<rootDir>/src/e2e/global-teardown.ts',
  setupFiles: ['<rootDir>/src/e2e/setup.ts'],
  // Runs after the test framework is installed, before each test file loads.
  // Used to jest.unmock('@ai-sdk/openai') so the real ESM provider is used in
  // e2e (the manual mock in src/__mocks__ is a unit-test workaround only).
  setupFilesAfterEnv: ['<rootDir>/src/e2e/setup-after-env.ts'],
  transform: {
    '^.+\\.(ts|tsx|js|jsx)$': 'ts-jest',
  },
  // vm-modules mode (NODE_OPTIONS=--experimental-vm-modules) loads node_modules
  // ESM natively, so nothing in node_modules needs transforming. The previous
  // allowlist force-transformed ESM packages (chokidar, @workflow/serde,
  // @ai-sdk, ...) into CJS, which breaks under vm-modules (and the dynamic
  // import('p-map') in @mastra/core's downloadAssetsFromMessages fails without
  // vm-modules). Keep the default: transform src/ only.
  transformIgnorePatterns: ['/node_modules/'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^tokenx$': '<rootDir>/src/e2e/mocks/tokenx.js',
  },
  testTimeout: 120000,
  verbose: true,
  // E2E suites share one Mnemosyne Docker instance and one SQLite tracker DB.
  // Parallel workers race on bank registration and Prisma writes (SQLite
  // "Operation has timed out"). Run sequentially (runInBand is CLI-only;
  // maxWorkers: 1 is the config equivalent).
  maxWorkers: 1,
  // E2E tests use real network connections (Mnemosyne MCP client HTTP
  // keep-alive sockets) that the global agent may not release in time.
  forceExit: true,
};
