/**
 * Jest config for the dependency-free ESM scripts suite (apps/racochu/scripts).
 * Run via: NODE_OPTIONS=--experimental-vm-modules jest --config jest.scripts.config.cjs
 * (chained into `npm test`). Kept separate so the main unit suite (ts-jest/CJS)
 * is never affected by ESM-vm-mode.
 */
module.exports = {
  rootDir: '.',
  roots: ['<rootDir>/scripts'],
  testEnvironment: 'node',
  testMatch: ['<rootDir>/scripts/**/*.test.mjs'],
};
