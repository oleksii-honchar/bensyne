import { ConfigService } from '@nestjs/config';

import { formatLocalIsoTimestamp, pinoLoggerConfigFactory } from './pino-logger-config.factory';

describe('pino-logger-config.factory', () => {
  const configService = {
    get: () => undefined,
  } as unknown as ConfigService;

  describe('formatLocalIsoTimestamp', () => {
    it('formats a known local instant as YYYY-MM-DDTHH:MM:SS.mmm±HH:MM with the host offset', () => {
      const localInstant = new Date(2026, 7, 23, 18, 29, 5, 123); // local-time constructor
      const output = formatLocalIsoTimestamp(localInstant);

      const offsetMinutes = -localInstant.getTimezoneOffset();
      const sign = offsetMinutes >= 0 ? '+' : '-';
      const abs = Math.abs(offsetMinutes);
      const expectedOffset = `${sign}${String(Math.floor(abs / 60)).padStart(2, '0')}:${String(
        abs % 60,
      ).padStart(2, '0')}`;

      expect(output).toBe(`2026-08-23T18:29:05.123${expectedOffset}`);
      expect(output).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/);
      expect(output).not.toContain('Z');
    });

    it('handles a positive offset and zero-pads the offset', () => {
      // 2026-01-15 09:05:07.040 local — offset sign/zero-padding computed from the host
      const localInstant = new Date(2026, 0, 15, 9, 5, 7, 40);
      const output = formatLocalIsoTimestamp(localInstant);

      expect(output).toMatch(/^2026-01-15T09:05:07\.040[+-]\d{2}:\d{2}$/);
      expect(output).not.toContain('Z');
    });
  });

  describe('pinoLoggerConfigFactory', () => {
    it('timestamp option emits a local-time ISO fragment, not UTC', () => {
      const params = pinoLoggerConfigFactory(configService);
      const pinoHttp = params.pinoHttp as { timestamp?: () => string };
      const fragment = pinoHttp.timestamp?.() ?? '';

      expect(fragment).toMatch(/^,"timestamp":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}"$/);
      expect(fragment).not.toContain('Z');
    });

    it('console pretty transport renders host local time via SYS translateTime', () => {
      const params = pinoLoggerConfigFactory(configService);
      const pinoHttp = params.pinoHttp as unknown as {
        transport?: {
          targets?: { target: string; options: { translateTime?: string } }[];
        };
      };
      const consoleTarget = pinoHttp.transport?.targets?.find(t => t.target === 'pino-pretty');

      expect(consoleTarget?.options.translateTime).toBe('SYS:yyyy-mm-dd HH:MM:ss');
    });
  });

  describe('file transport (pino-roll)', () => {
    it('uses pino-roll v4 rotation options (frequency, limit.count, symlink)', () => {
      const params = pinoLoggerConfigFactory(configService);
      const pinoHttp = params.pinoHttp as unknown as {
        transport?: {
          targets?: { target: string; options: Record<string, unknown> }[];
        };
      };
      const rollTarget = pinoHttp.transport?.targets?.find(t => t.target === 'pino-roll');

      expect(rollTarget?.options).toMatchObject({
        frequency: 'daily',
        limit: { count: 3 },
      });
      expect(rollTarget?.options).not.toHaveProperty('period');
      expect(rollTarget?.options).not.toHaveProperty('keep');
      expect(rollTarget?.options?.limit).toMatchObject({ removeOtherLogFiles: true });
      expect(rollTarget?.options?.symlink).toBe(true);
    });
  });
});
