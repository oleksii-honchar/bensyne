/**
 * Mock for @ai-sdk/openai — provides CommonJS-compatible createOpenAI
 * to avoid ESM resolution issues in Jest.
 */
module.exports.createOpenAI = jest.fn().mockReturnValue(
  jest.fn().mockReturnValue({}),
);
