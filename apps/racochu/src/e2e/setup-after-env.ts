// E2E setup that runs AFTER the test framework is installed (setupFilesAfterEnv).
//
// Purpose: disable the manual mock for @ai-sdk/openai (src/__mocks__/...).
// That mock exists so the UNIT suite can load without ESM resolution issues,
// but it silently breaks the e2e enrichment path — the real provider is
// replaced by jest.fn().mockReturnValue({}) so LlmClientFactory produces an
// empty model and Mastra throws AGENT_GET_MODEL_MISSING_MODEL_INSTANCE.
// E2E must use the real @ai-sdk/openai (transformed via transformIgnorePatterns,
// incl. its ESM-only dep @workflow/serde).
jest.unmock('@ai-sdk/openai');
