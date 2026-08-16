import { Injectable } from '@nestjs/common';
import { ContentChunk, FILE_ROLES, FileRole } from '../../domain/content-chunk.entity';
import { EnhancementConfig } from '../../infrastructure/config/config-schemas';

/**
 * Rule-based importance scoring service for chunks.
 * Returns a score in [0, 1] based on configurable factors.
 * Never throws — always produces a score.
 */
@Injectable()
export class ImportanceScoringService {
  /**
   * Score a chunk based on configured importance factors.
   * If scoring is disabled, returns config.importance.defaultScore.
   */
  score(chunk: ContentChunk, config: EnhancementConfig): number {
    const importanceConfig = config.importance;

    if (!importanceConfig?.enabled) {
      return importanceConfig?.defaultScore ?? 0.5;
    }

    const baseScore = importanceConfig.defaultScore ?? 0.5;
    const factors = importanceConfig.factors ?? [];

    let weightedSum = 0;

    for (const factor of factors) {
      const rawValue = this.calculateFactorValue(factor.name, chunk);
      weightedSum += rawValue * factor.weight;
    }

    const finalScore = baseScore + weightedSum;
    return this.clamp(finalScore, 0, 1);
  }

  /**
   * Calculate the raw value (0-1) for a specific factor.
   */
  private calculateFactorValue(factorName: string, chunk: ContentChunk): number {
    switch (factorName) {
      case 'fileRole':
        return this.fileRoleFactor(chunk.fileRole);
      case 'length':
        return this.lengthFactor(chunk.text);
      case 'keywords':
        return this.keywordsFactor(chunk.text);
      case 'header':
        return this.headerFactor(chunk.sectionHeader);
      default:
        return 0;
    }
  }

  /**
   * File role weight: docs > code > config
   */
  private fileRoleFactor(fileRole: FileRole): number {
    const weights: Record<FileRole, number> = {
      [FILE_ROLES.DOCS]: 0.8,
      [FILE_ROLES.CODE]: 0.7,
      [FILE_ROLES.CONFIG]: 0.6,
    };
    return weights[fileRole] ?? 0.5;
  }

  /**
   * Length factor: longer content → higher bonus, capped at 0.1.
   * Uses sigmoid-like curve: saturates around 500 chars.
   */
  private lengthFactor(text: string): number {
    const length = text.length;
    if (length === 0) return 0;
    // Sigmoid curve: approaches 0.1 as length increases, saturates around 500 chars
    const raw = 0.1 * (1 - Math.exp(-length / 250));
    return Math.min(raw, 0.1);
  }

  /**
   * Keywords factor: scan for importance indicators.
   * +0.1 per unique keyword found, capped at 0.3.
   */
  private keywordsFactor(text: string): number {
    const upperText = text.toUpperCase();
    const keywords = ['TODO', 'FIXME', 'IMPORTANT', 'BREAKING', 'CRITICAL'];
    let count = 0;

    for (const keyword of keywords) {
      if (upperText.includes(keyword)) {
        count++;
      }
    }

    // +0.1 per keyword, max +0.3
    return Math.min(count * 0.1, 0.3);
  }

  /**
   * Header factor: +0.05 per header level detected from sectionHeader.
   * Detects header level from "## " prefix pattern.
   * Level 2 (##) = +0.05, Level 3 (###) = +0.10, etc.
   */
  private headerFactor(sectionHeader: string): number {
    if (!sectionHeader || !sectionHeader.startsWith('#')) {
      return 0;
    }

    // Count leading # characters to determine header level
    const match = sectionHeader.match(/^(#+)/);
    if (!match) return 0;

    const level = match[1].length;
    if (level < 2) return 0;
    // +0.05 per level starting from level 2: level 2 = 0.05, level 3 = 0.10, etc.
    return (level - 1) * 0.05;
  }

  /**
   * Clamp a value to [min, max].
   */
  private clamp(value: number, min: number, max: number): number {
    return Math.max(min, Math.min(max, value));
  }
}
