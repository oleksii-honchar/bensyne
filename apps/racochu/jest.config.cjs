module.exports = {
  preset: 'ts-jest',
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@prisma/client$': '<rootDir>/src/generated/prisma/client.js',
  },
  moduleFileExtensions: ['js', 'json', 'ts'],
  rootDir: '.',
  testRegex: 'src/((?!e2e/)).*\\.test\\.ts$',
  collectCoverageFrom: ['src/**/*.ts', '!src/e2e/**/*'],
  coverageDirectory: 'coverage',
  testEnvironment: 'node',
  transform: {
    '^.+\\.(ts|tsx|js|jsx)$': ['ts-jest', {
      diagnostics: {
        ignoreCodes: [2322, 2353], // Dirent<NonSharedBuffer> mock type mismatch in force-reprocess tests
      },
    }],
  },
  transformIgnorePatterns: [
    'node_modules/(?!(chokidar|anymatch|readdirp|glob-parent|is-binary-path|fsevents|nestjs-pino|pino-http|pino|pino-pretty|@mastra|@sindresorhus|escape-string-regexp|tokenx|tiktoken|@faker-js|@ai-sdk)/)',
  ],
  coverageThreshold: {
    global: {
      lines: 80,
      branches: 70,
      functions: 80,
      statements: 80,
    },
  },
};
