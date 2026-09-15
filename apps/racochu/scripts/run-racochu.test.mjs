import { EventEmitter } from 'node:events';

import { describe, expect, it, jest } from '@jest/globals';

const mod = await import('./run-racochu.mjs');

describe('resolveExtraCaCerts', () => {
  const home = '/home/tester';

  it('preserves an explicitly supplied NODE_EXTRA_CA_CERTS', () => {
    expect(
      mod.resolveExtraCaCerts({
        env: { NODE_EXTRA_CA_CERTS: '/explicit/ca.pem' },
        exists: () => true,
        home,
      }),
    ).toBe('/explicit/ca.pem');
  });

  it('uses the first available local fallback PEM', () => {
    const candidates = mod.localCaCandidates(home);
    expect(mod.resolveExtraCaCerts({ env: {}, exists: path => path === candidates[1], home })).toBe(
      candidates[1],
    );
  });

  it('leaves the variable unset when no fallback PEM exists', () => {
    expect(mod.createLaunchEnv({ env: { KEEP: 'yes' }, exists: () => false, home })).toEqual({
      KEEP: 'yes',
    });
  });
});

describe('runRacochu', () => {
  it('passes the selected CA to cleanup and the runtime command', async () => {
    const spawned = [];
    const spawnFn = jest.fn((command, args, options) => {
      spawned.push({ command, args, options });
      const child = new EventEmitter();
      queueMicrotask(() => child.emit('exit', 0, null));
      return child;
    });
    const cleanupFn = jest.fn(async () => undefined);

    await expect(
      mod.runRacochu({
        command: 'node',
        args: ['dist/src/main.js'],
        env: {},
        exists: path => path.endsWith('/.config/better-opencode/extra-ca.pem'),
        home: '/home/tester',
        spawnFn,
        cleanupFn,
      }),
    ).resolves.toBe(0);

    expect(cleanupFn).toHaveBeenCalledWith(
      expect.objectContaining({
        NODE_EXTRA_CA_CERTS: '/home/tester/.config/better-opencode/extra-ca.pem',
      }),
    );
    expect(spawned).toHaveLength(1);
    expect(spawned[0]).toEqual(
      expect.objectContaining({
        command: 'node',
        args: ['dist/src/main.js'],
        options: expect.objectContaining({
          env: expect.objectContaining({
            NODE_EXTRA_CA_CERTS: '/home/tester/.config/better-opencode/extra-ca.pem',
          }),
        }),
      }),
    );
  });

  it('does not run cleanup for nested ts-node launches', async () => {
    const child = new EventEmitter();
    const spawnFn = jest.fn(() => {
      queueMicrotask(() => child.emit('exit', 0, null));
      return child;
    });
    const cleanupFn = jest.fn();

    await mod.runRacochu({ command: 'dotenvx', skipCleanup: true, spawnFn, cleanupFn });

    expect(cleanupFn).not.toHaveBeenCalled();
    expect(spawnFn).toHaveBeenCalledTimes(1);
  });
});
