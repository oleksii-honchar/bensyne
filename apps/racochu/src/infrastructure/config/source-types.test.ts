import { SOURCE_TYPES, SOURCE_TYPE_UNKNOWN, sourceTypeSchema } from './source-types';

describe('D29 source-type axis (spec §6.6)', () => {
  describe('SOURCE_TYPES — 1:1 gate (spec §14.11)', () => {
    it('is the exact producer set [obsidian, agent-sessions, vault] (cross-app lock with bensyne SourceType)', () => {
      expect(Object.values(SOURCE_TYPES)).toEqual(['obsidian', 'agent-sessions', 'vault']);
    });
  });

  describe('sourceTypeSchema — the 4-value wire axis (obsidian | agent-sessions | vault | unknown)', () => {
    it.each(['obsidian', 'agent-sessions', 'vault', 'unknown'])(
      'accepts wire value %s (exactly what bensyne SourceType accepts)',
      value => {
        expect(sourceTypeSchema.safeParse(value).success).toBe(true);
      },
    );

    it.each([
      'file_system',
      'agent_session',
      'git',
      'database',
      'external',
      'remote',
      'content-aware',
      '',
      'whatever',
    ])('rejects legacy/invalid value %s (D29: not on the axis)', value => {
      expect(sourceTypeSchema.safeParse(value).success).toBe(false);
    });

    it('exposes the unknown degrade marker (wire-side fallback only, not a producer)', () => {
      expect(SOURCE_TYPE_UNKNOWN).toBe('unknown');
      expect(sourceTypeSchema.safeParse(SOURCE_TYPE_UNKNOWN).success).toBe(true);
    });
  });
});
