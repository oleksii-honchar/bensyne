import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { aLogger } from './infrastructure/logging/logger.test-utils';
import { CliArgsService } from './infrastructure/services/cli-args.service';

/**
 * Config-resolution contract (user directive):
 * - dist runs (nx run racochu:start) → global ~/.config/racochu.yaml unless -c/--config or APP_CONFIG_PATH set
 * - dev runs (nx run racochu:start:dev, nodemon) → local dev.yaml
 *
 * Leak path under test: Nx auto-loads apps/racochu/.env into task env, and NestJS
 * ConfigModule loads .env from CWD at bootstrap. APP_CONFIG_PATH must NOT live in .env;
 * it is scoped to the start:dev script only.
 */

const APP_ROOT = path.join(__dirname, '..');

function readDotEnv(file: string): Record<string, string> {
  const vars: Record<string, string> = {};
  const filePath = path.join(APP_ROOT, file);
  if (!fs.existsSync(filePath)) {
    return vars;
  }
  for (const line of fs.readFileSync(filePath, 'utf-8').split('\n')) {
    const match = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (match) {
      vars[match[1]] = match[2];
    }
  }
  return vars;
}

function readPkgJson(): { scripts: Record<string, string> } {
  return JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf-8'));
}

function readProjectJson(): { targets: Record<string, { options: { command: string } }> } {
  return JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'project.json'), 'utf-8'));
}

/** Applies .env vars like Nx/dotenvx would (existing process env wins). Returns undo fn. */
function applyDotEnvLikeNx(envFile: string): () => void {
  const env = readDotEnv(envFile);
  const applied: Record<string, string | undefined> = {};
  for (const [key, value] of Object.entries(env)) {
    if (process.env[key] === undefined) {
      applied[key] = undefined;
      process.env[key] = value;
    }
  }
  return () => {
    for (const [key, value] of Object.entries(applied)) {
      process.env[key] = value as string | undefined;
    }
  };
}

describe('Racochu config resolution — dist global / dev.yaml via start:dev only', () => {
  describe('environment files must not leak dev config into dist runs', () => {
    it('apps/racochu/.env must not define APP_CONFIG_PATH', () => {
      expect(readDotEnv('.env').APP_CONFIG_PATH).toBeUndefined();
    });

    it('apps/racochu/.env.tpl must not define APP_CONFIG_PATH', () => {
      expect(readDotEnv('.env.tpl').APP_CONFIG_PATH).toBeUndefined();
    });

    it('start and start:prod scripts (dist) must not set APP_CONFIG_PATH', () => {
      const scripts = readPkgJson().scripts;
      expect(scripts.start).toBeDefined();
      expect(scripts['start:prod']).toBeDefined();
      expect(scripts.start).not.toMatch(/APP_CONFIG_PATH/);
      expect(scripts['start:prod']).not.toMatch(/APP_CONFIG_PATH/);
    });
  });

  describe('start:dev scoping — nodemon with dev.yaml', () => {
    it('start:dev script runs nodemon with APP_CONFIG_PATH=dev.yaml', () => {
      const scripts = readPkgJson().scripts;
      expect(scripts['start:dev']).toBeDefined();
      expect(scripts['start:dev']).toContain('nodemon');
      expect(scripts['start:dev']).toMatch(/APP_CONFIG_PATH=dev\.yaml/);
    });

    it('nodemon exec still goes through the ts-node dev script', () => {
      const nodemon = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'nodemon.json'), 'utf-8'));
      expect(nodemon.exec).toContain('npm run ts-node');
    });

    it('project.json exposes a start:dev nx target running the dev script', () => {
      const project = readProjectJson();
      expect(project.targets['start:dev']).toBeDefined();
      expect(project.targets['start:dev'].options.command).toContain('npm run start:dev');
    });
  });

  describe('resolution behavior', () => {
    afterEach(() => {
      delete process.env.APP_CONFIG_PATH;
    });

    it('dist start (nx loads .env into env): resolves to global ~/.config/racochu.yaml', () => {
      const undo = applyDotEnvLikeNx('.env');
      try {
        const result = new CliArgsService(aLogger()).parse([]);
        expect(result.config).toBe(path.join(os.homedir(), '.config', 'racochu.yaml'));
      } finally {
        undo();
      }
    });

    it('dist start: -c/--config overrides .env and global default', () => {
      const undo = applyDotEnvLikeNx('.env');
      try {
        expect(new CliArgsService(aLogger()).parse(['-c', '/custom.yaml']).config).toBe('/custom.yaml');
        expect(new CliArgsService(aLogger()).parse(['--config', '/custom2.yaml']).config).toBe(
          '/custom2.yaml',
        );
      } finally {
        undo();
      }
    });

    it('dev start (APP_CONFIG_PATH=dev.yaml from start:dev script): resolves dev.yaml', () => {
      const undo = applyDotEnvLikeNx('.env');
      process.env.APP_CONFIG_PATH = 'dev.yaml';
      try {
        expect(new CliArgsService(aLogger()).parse([]).config).toBe('dev.yaml');
      } finally {
        undo();
      }
    });
  });
});
