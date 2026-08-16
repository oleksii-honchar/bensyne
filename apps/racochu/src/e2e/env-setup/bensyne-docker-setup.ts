import { exec } from 'child_process';
import type { IncomingMessage } from 'http';
import * as http from 'http';
import * as path from 'path';
import { promisify } from 'util';

const execAsync = promisify(exec);
const DOCKER_COMPOSE_FILE = path.resolve(__dirname, 'docker-compose.bensyne.yml');
const PROJECT_NAME = 'rag-e2e-bensyne';
const BENSYNE_URL = 'http://localhost:3001';
const STARTUP_TIMEOUT_MS = 60000;

async function dockerCompose(args: string[]): Promise<void> {
  const cmd = `docker compose -p ${PROJECT_NAME} -f ${DOCKER_COMPOSE_FILE} ${args.join(' ')}`;
  await execAsync(cmd, { timeout: STARTUP_TIMEOUT_MS });
}

async function waitForBensyne(maxAttempts = 60): Promise<void> {
  const checkInterval = 1000;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      await new Promise<void>((resolve, reject) => {
        const req = http.get(`${BENSYNE_URL}/health`, { timeout: 2000 }, (res: IncomingMessage) => {
          res.resume();
          resolve();
        });
        req.on('error', reject);
      });
      return;
    } catch {
      if (attempt === maxAttempts) {
        throw new Error(
          `Bensyne did not become ready at ${BENSYNE_URL}/health within ${maxAttempts * checkInterval}ms`,
        );
      }
      await new Promise(r => setTimeout(r, checkInterval));
    }
  }
}

/**
 * Starts Bensyne MCP via Docker Compose.
 * Returns a cleanup function to stop and remove containers/volumes.
 */
export async function startBensyneDocker(): Promise<() => Promise<void>> {
  await dockerCompose(['up', '-d', '--wait']);
  await waitForBensyne();
  console.log(`[E2E] Bensyne MCP started at ${BENSYNE_URL}`);

  return async () => {
    console.log('[E2E] Stopping Bensyne MCP...');
    try {
      await dockerCompose(['down', '-v']);
    } catch (error) {
      console.warn('[E2E] Failed to stop Bensyne MCP:', error);
    }
  };
}
