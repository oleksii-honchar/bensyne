import { EnrichmentConfigForLlm, LlmClientFactory } from './llm-client-factory';

const mockChat = jest.fn((modelName: string) => ({ model: modelName, provider: 'mock-openai' }));
const mockOpenAI = { chat: mockChat };

jest.mock('@ai-sdk/openai', () => ({
  createOpenAI: jest.fn(() => mockOpenAI),
}));

import { createOpenAI } from '@ai-sdk/openai';

const mockCreateOpenAI = createOpenAI as jest.Mock;

describe('LlmClientFactory', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('createCustomLlm', () => {
    const validConfig: EnrichmentConfigForLlm = {
      enabled: true,
      llmUrl: 'https://lite-llm.lan/v1',
      llmModel: 'puma-qwopus3.5-9b',
      apiKey: 'sk-test-key',
    };

    it('should return null when config.enabled is false', () => {
      const config: EnrichmentConfigForLlm = { ...validConfig, enabled: false };

      const result = LlmClientFactory.createCustomLlm(config);

      expect(result).toBeNull();
    });

    it('should return null when config.llmUrl is empty', () => {
      const config: EnrichmentConfigForLlm = { ...validConfig, llmUrl: '' };

      const result = LlmClientFactory.createCustomLlm(config);

      expect(result).toBeNull();
    });

    it('should return null when config.apiKey is empty', () => {
      const config: EnrichmentConfigForLlm = { ...validConfig, apiKey: '' };

      const result = LlmClientFactory.createCustomLlm(config);

      expect(result).toBeNull();
    });

    it('should return null when config.apiKey is missing', () => {
      const config: EnrichmentConfigForLlm = {
        ...validConfig,
        apiKey: '',
      };

      const result = LlmClientFactory.createCustomLlm(config);

      expect(result).toBeNull();
    });

    it('should return a Chat Completions model when config is valid', () => {
      const result = LlmClientFactory.createCustomLlm(validConfig);

      expect(result).not.toBeNull();
      expect(mockChat).toHaveBeenCalledWith('puma-qwopus3.5-9b');
    });

    it('should call createOpenAI with correct apiKey and baseURL', () => {
      LlmClientFactory.createCustomLlm(validConfig);

      expect(mockCreateOpenAI).toHaveBeenCalledWith({
        apiKey: 'sk-test-key',
        baseURL: 'https://lite-llm.lan/v1',
      });
    });

    it('should call .chat(modelName) to create the Chat Completions model', () => {
      LlmClientFactory.createCustomLlm(validConfig);

      expect(mockChat).toHaveBeenCalledWith('puma-qwopus3.5-9b');
    });

    // Simulates @ai-sdk/openai-v6 (3.x) which uses chatModel instead of chat
    it('should fall back to chatModel when chat is not available (v6 provider)', () => {
      const mockChatModel = jest.fn((modelName: string) => ({
        model: modelName,
        provider: 'mock-openai-v6',
      }));
      const mockOpenAIV6 = { chatModel: mockChatModel };

      mockCreateOpenAI.mockReturnValueOnce(mockOpenAIV6);

      const result = LlmClientFactory.createCustomLlm(validConfig);

      expect(result).not.toBeNull();
      expect(mockChatModel).toHaveBeenCalledWith('puma-qwopus3.5-9b');
    });

    // Simulates a minimal provider that is just callable
    it('should fall back to calling provider directly when neither chat nor chatModel exists', () => {
      const mockCallableProvider = jest.fn((modelName: string) => ({
        model: modelName,
        provider: 'mock-callable',
      }));

      mockCreateOpenAI.mockReturnValueOnce(mockCallableProvider);

      const result = LlmClientFactory.createCustomLlm(validConfig);

      expect(result).not.toBeNull();
      expect(mockCallableProvider).toHaveBeenCalledWith('puma-qwopus3.5-9b');
    });
  });
});
