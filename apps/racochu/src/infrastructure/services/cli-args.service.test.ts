import packageJson from '../../../package.json';
import { BasePinoLogger } from '../logging/base-pino-logger';
import { aLogger } from '../logging/logger.test-utils';
import { CliArgsService, ParsedCliArgs } from './cli-args.service';

describe('CliArgsService', () => {
  let service: CliArgsService;
  let mockLogger: jest.Mocked<BasePinoLogger>;

  beforeEach(() => {
    mockLogger = aLogger();
    service = new CliArgsService(mockLogger);
  });

  describe('parse', () => {
    it('should return default values when no args provided', () => {
      // Isolate from APP_CONFIG_PATH (e.g. apps/racochu/.env under NX) so the
      // ~/.config/racochu.yaml fallback is exercised deterministically.
      const saved = process.env.APP_CONFIG_PATH;
      delete process.env.APP_CONFIG_PATH;

      const result = service.parse([]);

      if (saved === undefined) {
        delete process.env.APP_CONFIG_PATH;
      } else {
        process.env.APP_CONFIG_PATH = saved;
      }

      expect(result).toEqual<ParsedCliArgs>({
        config: expect.stringContaining('racochu.yaml'),
        verbose: false,
        help: false,
        version: false,
        dryRun: false,
        watch: true,
        forceReprocess: false,
        processOnly: false,
        source: null,
      });
    });

    it('should override config path with --config', () => {
      const result = service.parse(['--config', '/custom/path.yaml']);

      expect(result.config).toBe('/custom/path.yaml');
    });

    it('should override config path with -c', () => {
      const result = service.parse(['-c', '/short/path.yaml']);

      expect(result.config).toBe('/short/path.yaml');
    });

    it('should enable verbose with --verbose', () => {
      const result = service.parse(['--verbose']);

      expect(result.verbose).toBe(true);
    });

    it('should enable verbose with -v', () => {
      const result = service.parse(['-v']);

      expect(result.verbose).toBe(true);
    });

    it('should set help flag with --help', () => {
      const result = service.parse(['--help']);

      expect(result.help).toBe(true);
    });

    it('should set help flag with -h', () => {
      const result = service.parse(['-h']);

      expect(result.help).toBe(true);
    });

    it('should set version flag with --version', () => {
      const result = service.parse(['--version']);

      expect(result.version).toBe(true);
    });

    it('should set version flag with -V', () => {
      const result = service.parse(['-V']);

      expect(result.version).toBe(true);
    });

    it('should enable dry-run with --dry-run', () => {
      const result = service.parse(['--dry-run']);

      expect(result.dryRun).toBe(true);
    });

    it('should keep watch true with --watch', () => {
      const result = service.parse(['--watch']);

      expect(result.watch).toBe(true);
    });

    it('should set processOnly true and watch false with --process-only', () => {
      const result = service.parse(['--process-only']);

      expect(result.processOnly).toBe(true);
      expect(result.watch).toBe(false);
    });

    it('should enable force-reprocess with --force-reprocess', () => {
      const result = service.parse(['--force-reprocess']);

      expect(result.forceReprocess).toBe(true);
    });

    it('should enable force-reprocess with -f', () => {
      const result = service.parse(['-f']);

      expect(result.forceReprocess).toBe(true);
    });

    it('should set source with --source', () => {
      const result = service.parse(['--source', 'obsidian-vault']);

      expect(result.source).toBe('obsidian-vault');
    });

    it('should set source with -s', () => {
      const result = service.parse(['-s', 'agent-sessions']);

      expect(result.source).toBe('agent-sessions');
    });

    it('should handle multiple flags together', () => {
      const result = service.parse(['-v', '-f', '-s', 'obsidian-vault', '--process-only']);

      expect(result.verbose).toBe(true);
      expect(result.forceReprocess).toBe(true);
      expect(result.source).toBe('obsidian-vault');
      expect(result.processOnly).toBe(true);
      expect(result.watch).toBe(false);
    });
  });

  describe('showHelp', () => {
    it('should write help text to stdout', () => {
      const writeSpy = jest.spyOn(process.stdout, 'write').mockImplementation(() => true);
      service.showHelp();

      expect(writeSpy).toHaveBeenCalledTimes(1);
      const output = writeSpy.mock.calls[0][0] as string;
      expect(output).toContain('racochu');
      expect(output).toContain('--config');
      expect(output).toContain('--verbose');
      expect(output).toContain('--help');
      expect(output).toContain('--version');
      expect(output).toContain('--force-reprocess');
      expect(output).toContain('--source');
      expect(output).toContain('--process-only');
      writeSpy.mockRestore();
    });
  });

  describe('showVersion', () => {
    it('should write version from package.json to stdout', () => {
      const writeSpy = jest.spyOn(process.stdout, 'write').mockImplementation(() => true);
      service.showVersion();

      expect(writeSpy).toHaveBeenCalledTimes(1);
      const output = writeSpy.mock.calls[0][0] as string;
      expect(output).toBe(`racochu v${packageJson.version}\n`);
      writeSpy.mockRestore();
    });
  });
});
