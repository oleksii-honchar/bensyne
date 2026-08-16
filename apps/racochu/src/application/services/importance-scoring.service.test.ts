import { Test, TestingModule } from '@nestjs/testing';
import { FILE_ROLES } from '../../domain/content-chunk.entity';
import { aContentChunk } from '../../domain/content-chunk.entity.test-utils';
import { EnhancementConfig } from '../../infrastructure/config/config-schemas';
import { DEFAULT_CONFIG } from '../../infrastructure/config/configuration.service';
import { ImportanceScoringService } from './importance-scoring.service';

describe('ImportanceScoringService', () => {
  let service: ImportanceScoringService;

  const defaultConfig: EnhancementConfig = DEFAULT_CONFIG.enhancement;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [ImportanceScoringService],
    }).compile();

    service = module.get<ImportanceScoringService>(ImportanceScoringService);
  });

  describe('score', () => {
    describe('disabled scoring', () => {
      it('should return defaultScore when importance scoring is disabled', () => {
        const chunk = aContentChunk();
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: { ...defaultConfig.importance, enabled: false, defaultScore: 0.3 },
        };

        const score = service.score(chunk, config);

        expect(score).toBe(0.3);
      });

      it('should return 0.5 as defaultScore when not specified and scoring disabled', () => {
        const chunk = aContentChunk();
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: { enabled: false, defaultScore: 0.5, factors: [] },
        };

        const score = service.score(chunk, config);

        expect(score).toBe(0.5);
      });
    });

    describe('fileRole factor', () => {
      it('should produce highest score for DOCS fileRole', () => {
        const docsChunk = aContentChunk({ fileRole: FILE_ROLES.DOCS, text: 'x', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'fileRole', weight: 0.4 }],
          },
        };

        const score = service.score(docsChunk, config);

        // Base 0.5 + (0.8 * 0.4) = 0.82
        expect(score).toBeCloseTo(0.82);
      });

      it('should produce lower score for CODE fileRole than DOCS', () => {
        const codeChunk = aContentChunk({ fileRole: FILE_ROLES.CODE, text: 'x', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'fileRole', weight: 0.4 }],
          },
        };

        const score = service.score(codeChunk, config);

        // Base 0.5 + (0.7 * 0.4) = 0.78
        expect(score).toBeCloseTo(0.78);
      });

      it('should produce lower score for CONFIG fileRole than CODE', () => {
        const configChunk = aContentChunk({ fileRole: FILE_ROLES.CONFIG, text: 'x', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'fileRole', weight: 0.4 }],
          },
        };

        const score = service.score(configChunk, config);

        // Base 0.5 + (0.6 * 0.4) = 0.74
        expect(score).toBeCloseTo(0.74);
      });

      it('should apply fileRole weight multiplier', () => {
        const chunk = aContentChunk({ fileRole: FILE_ROLES.DOCS, text: 'x', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'fileRole', weight: 0.4 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + (0.8 * 0.4) = 0.82
        expect(score).toBeCloseTo(0.82);
      });
    });

    describe('length factor', () => {
      it('should give no bonus for very short content', () => {
        const chunk = aContentChunk({ text: 'hi', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'length', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + negligible length bonus
        expect(score).toBeLessThan(0.55);
      });

      it('should give higher bonus for longer content', () => {
        const shortChunk = aContentChunk({ text: 'a'.repeat(50), sectionHeader: '' });
        const longChunk = aContentChunk({ text: 'a'.repeat(300), sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'length', weight: 1.0 }],
          },
        };

        const shortScore = service.score(shortChunk, config);
        const longScore = service.score(longChunk, config);

        expect(longScore).toBeGreaterThan(shortScore);
      });

      it('should cap length bonus at longer content lengths', () => {
        const mediumChunk = aContentChunk({ text: 'a'.repeat(1000), sectionHeader: '' });
        const hugeChunk = aContentChunk({ text: 'a'.repeat(5000), sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'length', weight: 1.0 }],
          },
        };

        const mediumScore = service.score(mediumChunk, config);
        const hugeScore = service.score(hugeChunk, config);

        // Both should be at or near the cap
        expect(hugeScore - mediumScore).toBeLessThan(0.01);
      });

      it('should apply length weight multiplier', () => {
        const chunk = aContentChunk({ text: 'a'.repeat(500), sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'length', weight: 0.2 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + (lengthBonus * 0.2) — bonus capped around 0.1 max
        expect(score).toBeGreaterThan(0.5);
        expect(score).toBeLessThan(0.53);
      });
    });

    describe('keywords factor', () => {
      it('should give no bonus when no keywords present', () => {
        const chunk = aContentChunk({
          text: 'This is normal content without any special markers.',
          sectionHeader: '',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        // No keywords found, so score should be close to base
        expect(score).toBeLessThan(0.55);
      });

      it('should give +0.1 bonus for TODO keyword', () => {
        const chunk = aContentChunk({ text: 'This has a TODO item to fix.', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeGreaterThan(0.5);
      });

      it('should give +0.1 bonus for FIXME keyword', () => {
        const chunk = aContentChunk({ text: 'This has a FIXME issue.', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeGreaterThan(0.5);
      });

      it('should give +0.1 bonus for IMPORTANT keyword', () => {
        const chunk = aContentChunk({ text: 'This is IMPORTANT information.', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeGreaterThan(0.5);
      });

      it('should give +0.1 bonus for breaking keyword', () => {
        const chunk = aContentChunk({ text: 'This is a breaking change.', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeGreaterThan(0.5);
      });

      it('should give +0.1 bonus for CRITICAL keyword', () => {
        const chunk = aContentChunk({ text: 'This is CRITICAL.', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeGreaterThan(0.5);
      });

      it('should accumulate bonuses for multiple keywords up to max +0.3', () => {
        const chunk = aContentChunk({
          text: 'TODO: fix this FIXME issue. IMPORTANT: this is breaking and CRITICAL.',
          sectionHeader: '',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + capped keyword bonus (max 0.3) = 0.8
        expect(score).toBeCloseTo(0.8);
      });

      it('should cap keyword bonus at +0.3 even with many keywords', () => {
        const chunk = aContentChunk({
          text: 'TODO FIXME IMPORTANT breaking CRITICAL TODO FIXME IMPORTANT breaking CRITICAL',
          sectionHeader: '',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + capped keyword bonus (max 0.3) = 0.8
        expect(score).toBeCloseTo(0.8);
      });

      it('should apply keywords weight multiplier', () => {
        const chunk = aContentChunk({ text: 'TODO FIXME IMPORTANT', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 0.3 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + (0.3 keywordBonus * 0.3 weight) = 0.5 + 0.09 = 0.59
        expect(score).toBeCloseTo(0.59);
      });
    });

    describe('header factor', () => {
      it('should give no bonus when sectionHeader is empty', () => {
        const chunk = aContentChunk({ text: 'Content', sectionHeader: '' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'header', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeCloseTo(0.5);
      });

      it('should give +0.05 bonus for level 2 header (##)', () => {
        const chunk = aContentChunk({ text: 'Content', sectionHeader: '## Section Title' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'header', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeCloseTo(0.55);
      });

      it('should give +0.10 bonus for level 3 header (###)', () => {
        const chunk = aContentChunk({ text: 'Content', sectionHeader: '### Subsection' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'header', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeCloseTo(0.6);
      });

      it('should give +0.15 bonus for level 4 header (####)', () => {
        const chunk = aContentChunk({ text: 'Content', sectionHeader: '#### Detail' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'header', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeCloseTo(0.65);
      });

      it('should give no bonus for plain text header without ## prefix', () => {
        const chunk = aContentChunk({ text: 'Content', sectionHeader: 'Plain Title' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'header', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeCloseTo(0.5);
      });

      it('should apply header weight multiplier', () => {
        const chunk = aContentChunk({ text: 'Content', sectionHeader: '## Section' });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'header', weight: 0.1 }],
          },
        };

        const score = service.score(chunk, config);

        // Base 0.5 + (0.05 headerBonus * 0.1 weight) = 0.5 + 0.005 = 0.505
        expect(score).toBeCloseTo(0.505);
      });
    });

    describe('combined scoring', () => {
      it('should combine all factors with their weights', () => {
        const chunk = aContentChunk({
          fileRole: FILE_ROLES.DOCS,
          text: 'a'.repeat(500) + ' TODO FIXME',
          sectionHeader: '## Important Section',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [
              { name: 'fileRole', weight: 0.4 },
              { name: 'length', weight: 0.2 },
              { name: 'keywords', weight: 0.3 },
              { name: 'header', weight: 0.1 },
            ],
          },
        };

        const score = service.score(chunk, config);

        // Should be higher than base due to all positive factors
        expect(score).toBeGreaterThan(0.5);
        expect(score).toBeLessThanOrEqual(1.0);
      });
    });

    describe('score clamping', () => {
      it('should clamp score to maximum of 1.0', () => {
        const chunk = aContentChunk({
          fileRole: FILE_ROLES.DOCS,
          text: 'a'.repeat(10000) + ' TODO FIXME IMPORTANT breaking CRITICAL',
          sectionHeader: '#### Deep Section',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [
              { name: 'fileRole', weight: 10.0 },
              { name: 'length', weight: 10.0 },
              { name: 'keywords', weight: 10.0 },
              { name: 'header', weight: 10.0 },
            ],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBe(1.0);
      });

      it('should clamp score to minimum of 0.0', () => {
        const chunk = aContentChunk({
          fileRole: FILE_ROLES.CONFIG,
          text: '',
          sectionHeader: '',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [
              { name: 'fileRole', weight: -10.0 },
              { name: 'length', weight: -10.0 },
              { name: 'keywords', weight: -10.0 },
              { name: 'header', weight: -10.0 },
            ],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBe(0.0);
      });
    });

    describe('edge cases', () => {
      it('should return a number (not Result)', () => {
        const chunk = aContentChunk();
        const score = service.score(chunk, defaultConfig);

        expect(typeof score).toBe('number');
      });

      it('should never throw — always produces a score', () => {
        const chunk = aContentChunk({
          text: '',
          sectionHeader: '',
          fileRole: FILE_ROLES.DOCS,
        });

        expect(() => service.score(chunk, defaultConfig)).not.toThrow();
      });

      it('should handle empty factors array by returning defaultScore', () => {
        const chunk = aContentChunk();
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: { enabled: true, defaultScore: 0.5, factors: [] },
        };

        const score = service.score(chunk, config);

        expect(score).toBe(0.5);
      });

      it('should ignore unknown factor names gracefully', () => {
        const chunk = aContentChunk();
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'unknownFactor', weight: 1.0 }],
          },
        };

        expect(() => service.score(chunk, config)).not.toThrow();
        expect(service.score(chunk, config)).toBe(0.5);
      });

      it('should handle case-insensitive keyword matching', () => {
        const chunk = aContentChunk({
          text: 'this has a todo item and a breaking change',
          sectionHeader: '',
        });
        const config: EnhancementConfig = {
          ...defaultConfig,
          importance: {
            enabled: true,
            defaultScore: 0.5,
            factors: [{ name: 'keywords', weight: 1.0 }],
          },
        };

        const score = service.score(chunk, config);

        expect(score).toBeGreaterThan(0.5);
      });
    });
  });
});
