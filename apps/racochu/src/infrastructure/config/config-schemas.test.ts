import {
  chunkingConfigSchema,
  configurationSchema,
  enhancementConfigSchema,
  enrichmentConfigSchema,
  mcpConfigSchema,
  telemetryConfigSchema,
  watchSourceConfigSchema,
} from './config-schemas';
import { SOURCE_TYPES } from './source-types';

describe('config-schemas', () => {
  describe('watchSourceConfigSchema', () => {
    it('parses valid watch source config', () => {
      const input = {
        id: 'test-source',
        path: '/some/path',
        exclude: ['**/.git/**'],
        debounceMs: 5000,
      };

      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.id).toBe('test-source');
        expect(result.data.path).toBe('/some/path');
      }
    });

    it('applies defaults for optional fields', () => {
      const input = {
        id: 'minimal',
        path: '/path',
      };

      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.exclude).toEqual([
          '.git/**',
          '**/.git/**',
          'node_modules/**',
          '**/node_modules/**',
        ]);
        expect(result.data.debounceMs).toBe(3000);
      }
    });

    it('rejects missing id', () => {
      const input = { path: '/path' };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('rejects missing path', () => {
      const input = { id: 'test' };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('rejects negative debounceMs', () => {
      const input = { id: 'test', path: '/path', debounceMs: -100 };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('accepts memoryBank field', () => {
      const input = {
        id: 'test-source',
        path: '/path',
        memoryBank: 'my-namespace',
      };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.memoryBank).toBe('my-namespace');
      }
    });

    it('defaults memoryBank to source id when not provided', () => {
      const input = { id: 'my-source', path: '/path' };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.memoryBank).toBe('my-source');
      }
    });

    it('accepts description field and preserves it as-is', () => {
      const input = {
        id: 'test-source',
        path: '/path',
        description: 'My personal Obsidian vault with notes and research',
      };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.description).toBe('My personal Obsidian vault with notes and research');
      }
    });

    it('allows config without description (description is optional)', () => {
      const input = { id: 'test-source', path: '/path' };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.description).toBeUndefined();
      }
    });

    it('accepts valid sourceType values', () => {
      const input = { id: 'test-source', path: '/path', sourceType: SOURCE_TYPES.AGENT_SESSIONS };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.sourceType).toBe(SOURCE_TYPES.AGENT_SESSIONS);
      }

      const result2 = watchSourceConfigSchema.safeParse({
        id: 'test-source',
        path: '/path',
        sourceType: SOURCE_TYPES.OBSIDIAN,
      });
      expect(result2.success).toBe(true);
      if (result2.success) {
        expect(result2.data.sourceType).toBe(SOURCE_TYPES.OBSIDIAN);
      }

      const result3 = watchSourceConfigSchema.safeParse({
        id: 'test-source',
        path: '/path',
        sourceType: SOURCE_TYPES.VAULT,
      });
      expect(result3.success).toBe(true);
      if (result3.success) {
        expect(result3.data.sourceType).toBe(SOURCE_TYPES.VAULT);
      }
    });

    it('rejects invalid sourceType value', () => {
      const input = { id: 'test-source', path: '/path', sourceType: 'invalid-source-type' };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('defaults sourceType to vault when omitted', () => {
      const input = { id: 'test-source', path: '/path' };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.sourceType).toBe('vault');
      }
    });

    it('backward compatible: config without sourceType field parses successfully', () => {
      const input = {
        id: 'legacy-source',
        path: '/legacy/path',
        memoryBank: 'legacy-bank',
        description: 'A legacy source',
      };
      const result = watchSourceConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.sourceType).toBe('vault');
        expect(result.data.memoryBank).toBe('legacy-bank');
      }
    });
  });

  describe('enhancementConfigSchema', () => {
    it('parses valid enhancement config with all fields', () => {
      const input = {
        maxCharacters: {
          prose: 200,
          code: 400,
          configuration: 300,
          documentation: 300,
        },
        importance: {
          enabled: true,
          defaultScore: 0.5,
          factors: [
            { name: 'fileRole', weight: 0.4 },
            { name: 'keywords', weight: 0.3 },
          ],
        },
        tags: {
          enabled: true,
          maxTags: 10,
        },
        source: {
          includePath: true,
          includeSection: true,
          includeMetadata: false,
        },
      };

      const result = enhancementConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.maxCharacters.prose).toBe(200);
        expect(result.data.maxCharacters.code).toBe(400);
        expect(result.data.importance.enabled).toBe(true);
        expect(result.data.tags.enabled).toBe(true);
        expect(result.data.source.includePath).toBe(true);
      }
    });

    it('applies defaults for empty object', () => {
      const result = enhancementConfigSchema.safeParse({});
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.maxCharacters.prose).toBe(200);
        expect(result.data.maxCharacters.code).toBe(400);
        expect(result.data.maxCharacters.configuration).toBe(300);
        expect(result.data.maxCharacters.documentation).toBe(300);
        expect(result.data.importance.enabled).toBe(true);
        expect(result.data.importance.defaultScore).toBe(0.5);
        expect(result.data.importance.factors).toBeDefined();
        expect(result.data.tags.enabled).toBe(true);
        expect(result.data.tags.maxTags).toBe(10);
        expect(result.data.source.includePath).toBe(true);
        expect(result.data.source.includeSection).toBe(true);
        expect(result.data.source.includeMetadata).toBe(false);
      }
    });

    it('validates maxCharacters values are positive numbers', () => {
      const result = enhancementConfigSchema.safeParse({
        maxCharacters: { prose: -10, code: 400, configuration: 300, documentation: 300 },
      });
      expect(result.success).toBe(false);
    });

    it('validates importance.defaultScore is between 0 and 1', () => {
      const result = enhancementConfigSchema.safeParse({
        importance: { enabled: true, defaultScore: 1.5 },
      });
      expect(result.success).toBe(false);
    });

    it('validates importance.factors have required fields', () => {
      const result = enhancementConfigSchema.safeParse({
        importance: { enabled: true, defaultScore: 0.5, factors: [{ name: 'test' }] },
      });
      expect(result.success).toBe(true); // weight is optional, defaults to 1.0
    });

    it('validates tags.maxTags is positive', () => {
      const result = enhancementConfigSchema.safeParse({
        tags: { enabled: true, maxTags: 0 },
      });
      expect(result.success).toBe(false);
    });
  });

  describe('chunkingConfigSchema', () => {
    it('parses valid chunking config', () => {
      const input = {
        maxSizes: {
          agentSessions: 400,
          obsidianNotes: 500,
          codeFiles: 400,
          configuration: 'per-key',
          plainText: 450,
        },
        overlap: 50,
        hardCap: 600,
      };

      const result = chunkingConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('applies defaults for empty object', () => {
      const result = chunkingConfigSchema.safeParse({});
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.maxSizes?.agentSessions).toBe(400);
        expect(result.data.overlap).toBe(50);
        expect(result.data.hardCap).toBe(600);
      }
    });

    it('accepts configuration as number', () => {
      const input = {
        maxSizes: { configuration: 500 },
      };

      const result = chunkingConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
    });
  });

  describe('enrichmentConfigSchema', () => {
    it('parses valid enrichment config', () => {
      const input = {
        enabled: true,
        llmUrl: 'http://localhost:8000/v1',
        llmModel: 'qwen3.5-27b',
        apiKey: 'test-key',
        maxConcurrency: 3,
        timeoutMs: 15000,
        docMaxTokens: 16000,
      };

      const result = enrichmentConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('applies defaults for empty object', () => {
      const result = enrichmentConfigSchema.safeParse({});
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.enabled).toBe(false);
        expect(result.data.maxConcurrency).toBe(1);
        expect(result.data.timeoutMs).toBe(15000);
        expect(result.data.docMaxTokens).toBe(16000);
      }
    });

    it('rejects invalid URL', () => {
      const input = { llmUrl: 'not-a-url' };
      const result = enrichmentConfigSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('mcpConfigSchema', () => {
    it('parses valid MCP config', () => {
      const input = {
        url: 'https://lite-llm.lan/mcp/mnemosyne',
        apiKey: 'test-key',
        timeoutMs: 30000,
        maxRetries: 3,
        retryDelayMs: 1000,
      };

      const result = mcpConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('applies defaults for empty object', () => {
      const result = mcpConfigSchema.safeParse({});
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.url).toBe('https://lite-llm.lan/mcp/mnemosyne');
        expect(result.data.timeoutMs).toBe(30000);
        expect(result.data.maxRetries).toBe(3);
        expect(result.data.retryDelayMs).toBe(1000);
      }
    });

    it('rejects invalid URL', () => {
      const input = { url: 'not-a-url' };
      const result = mcpConfigSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('telemetryConfigSchema', () => {
    it('parses valid telemetry config', () => {
      const input = {
        enabled: true,
        endpoint: 'clickstack-otel-collector:4317',
        service: 'racochu',
        metrics: {
          chunking: true,
          ingestion: true,
          errors: true,
        },
      };

      const result = telemetryConfigSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('applies defaults for empty object', () => {
      const result = telemetryConfigSchema.safeParse({});
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.enabled).toBe(true);
        expect(result.data.endpoint).toBe('clickstack-otel-collector:4317');
        expect(result.data.service).toBe('racochu');
        expect(result.data.metrics?.chunking).toBe(true);
      }
    });
  });

  describe('configurationSchema', () => {
    it('parses full valid configuration', () => {
      const input = {
        watchSources: [
          {
            id: 'obsidian-vault',
            path: '~/vault',
            include: ['*.md', '*.txt'],
            exclude: ['**/.git/**', '**/node_modules/**'],
            debounceMs: 3000,
            ignorePatterns: ['**/.DS_Store'],
          },
          {
            id: 'agent-sessions',
            path: '~/.agent-sessions',
            include: ['*.md'],
            exclude: ['**/archive/**'],
            debounceMs: 5000,
          },
          {
            id: 'codebase',
            path: '~/www/project',
            include: ['*.ts', '*.js', '*.py'],
            exclude: ['**/node_modules/**', '**/dist/**'],
            debounceMs: 2000,
          },
        ],
        chunking: {
          maxSizes: {
            agentSessions: 400,
            obsidianNotes: 500,
            codeFiles: 400,
            configuration: 'per-key',
            plainText: 450,
          },
          overlap: 50,
          hardCap: 600,
        },
        enrichment: { enabled: false },
        mcp: {
          url: 'https://lite-llm.lan/mcp/mnemosyne',
          timeoutMs: 30000,
          maxRetries: 3,
          retryDelayMs: 1000,
        },
        telemetry: {
          enabled: true,
          endpoint: 'clickstack-otel-collector:4317',
          service: 'racochu',
          metrics: {
            chunking: true,
            ingestion: true,
            errors: true,
          },
        },
      };

      const result = configurationSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.watchSources).toHaveLength(3);
        expect(result.data.watchSources[0].sourceType).toBe('vault');
        expect(result.data.mcp.url).toBe('https://lite-llm.lan/mcp/mnemosyne');
      }
    });

    it('applies defaults for empty object', () => {
      const result = configurationSchema.safeParse({});
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.watchSources).toEqual([]);
        expect(result.data.enrichment.enabled).toBe(false);
        expect(result.data.enhancement.maxCharacters.prose).toBe(200);
        expect(result.data.enhancement.importance.enabled).toBe(true);
        expect(result.data.enhancement.tags.enabled).toBe(true);
        expect(result.data.mcp.url).toBe('https://lite-llm.lan/mcp/mnemosyne');
        expect(result.data.telemetry.enabled).toBe(true);
      }
    });

    it('parses enhancement config in root schema', () => {
      const input = {
        enhancement: {
          maxCharacters: { prose: 250, code: 500, configuration: 350, documentation: 350 },
          importance: { enabled: false, defaultScore: 0.3 },
          tags: { enabled: true, maxTags: 5 },
          source: { includePath: true, includeSection: false, includeMetadata: true },
        },
      };
      const result = configurationSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.enhancement.maxCharacters.prose).toBe(250);
        expect(result.data.enhancement.importance.enabled).toBe(false);
        expect(result.data.enhancement.tags.maxTags).toBe(5);
        expect(result.data.enhancement.source.includeMetadata).toBe(true);
      }
    });

    it('rejects config with invalid watch source', () => {
      const input = {
        watchSources: [{ id: 'bad', path: 123 }], // path must be string
      };

      const result = configurationSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });
});
