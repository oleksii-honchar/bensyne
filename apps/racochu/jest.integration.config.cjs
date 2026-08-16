/**
 * B4 — MCP protocol integration test config (spec-monorepo Phase B4).
 *
 * Isolated from the unit suite (jest.config.cjs) and the Docker-based e2e
 * suite (jest.e2e.config.cjs): this config only matches src/integration/ and
 * starts the REAL bensyne-mcp server via its venv Python (no Docker, no
 * global setup). Run via `npm run test:integration` or `npx nx run racochu:integration`.
 */
module.exports = {
  preset: 'ts-jest',
  moduleFileExtensions: ['js', 'json', 'ts'],
  rootDir: '.',
  testRegex: 'src/integration/.*\\.test\\.ts$',
  collectCoverageFrom: [],
  coverageDirectory: 'coverage-integration',
  testEnvironment: 'node',
  transform: {
    '^.+\\.(ts|tsx|js|jsx)$': 'ts-jest',
  },
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
  },
  testTimeout: 120000,
  verbose: true,
  maxWorkers: 1,
};
