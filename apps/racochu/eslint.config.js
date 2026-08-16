const globals = require('globals');
const eslint = require('@eslint/js');
const tseslint = require('typescript-eslint');
const eslintPrettier = require('eslint-plugin-prettier');

const eslintConfigBase = require('./eslint.config.base');

module.exports = tseslint.config(
  ...eslintConfigBase,
  {
    ignores: ['src/generated/**'],
  },
  {
    files: ['src/**/*.ts'],
    plugins: {
      'typescript-eslint': tseslint.plugin,
      prettier: eslintPrettier,
    },
    languageOptions: {
      ecmaVersion: 'latest',
      parser: tseslint.parser,
      parserOptions: {
        project: true,
        tsconfigRootDir: __dirname,
      },
      sourceType: 'module',
      globals: {
        ...globals.node,
        ...globals.jest,
      },
    },
    rules: {
      'prettier/prettier': 'error',
      // Prefer Prettier's `{}` for empty blocks over ESLint's `{ }`
      'brace-style': 'off',
      // Disable base rule — it doesn't understand TS parameter properties (e.g. `private readonly x: X` in constructors)
      'no-unused-vars': 'off',
      // Use TS-aware rule that correctly handles parameter properties; allow _-prefixed (intentionally unused)
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
);
