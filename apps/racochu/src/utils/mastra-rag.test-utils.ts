/**
 * Shared mock for @mastra/rag used across test files.
 *
 * Import this file at the top of any test file that needs the @mastra/rag mock:
 *
 *   import '@/utils/mastra-rag.test-utils';
 *
 * The jest.mock call is hoisted automatically by Jest, so the import order
 * does not matter as long as this file is imported before any module that
 * depends on @mastra/rag.
 */
jest.mock('@mastra/rag', () => ({
  MDocument: class MockMDocument {
    static fromMarkdown = jest.fn();
    static fromJSON = jest.fn();
    static fromText = jest.fn();
    static fromHTML = jest.fn();
    extractMetadata = jest.fn();
    chunkMarkdown = jest.fn();
    chunkRecursive = jest.fn();
    chunkJSON = jest.fn();
    chunkSentence = jest.fn();
    getDocs = jest.fn();
    _chunks: { text: string; metadata?: Record<string, unknown> }[] = [];
    _metadata: Record<string, string> = {};
    _textContent = '';
    constructor(content: string, metadata?: Record<string, unknown>) {
      this._textContent = content;
      this._metadata = (metadata as Record<string, string>) ?? {};
    }
  },
}));
