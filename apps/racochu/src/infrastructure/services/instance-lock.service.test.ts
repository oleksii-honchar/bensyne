import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { InstanceLockService, resolveWatchLockPath } from './instance-lock.service';

// Plan T5 test strategy: tmp dir + fake pids against REAL OS semantics —
// process.kill liveness and fs 'wx' exclusivity are never faked here.
// An alive holder = this jest process's own pid (guaranteed live, and foreign
// to every InstanceLockService under test). A dead holder = a pid above every
// supported OS ceiling: process.kill(deadPid, 0) throws ESRCH for real.

const DEAD_PID = 2147483647;

describe('InstanceLockService', () => {
  let lockDir: string;
  let lockPath: string;

  beforeEach(() => {
    lockDir = fs.mkdtempSync(path.join(os.tmpdir(), 'racochu-instance-lock-'));
    lockPath = path.join(lockDir, 'racochu.watch.lock');
  });

  afterEach(() => {
    fs.rmSync(lockDir, { recursive: true, force: true });
  });

  describe('acquire', () => {
    it('acquires a fresh lock and its content is the holder pid', () => {
      const lock = new InstanceLockService(lockPath);

      const result = lock.acquire();

      expect(result).toEqual({ acquired: true });
      expect(fs.existsSync(lockPath)).toBe(true);
      expect(fs.readFileSync(lockPath, 'utf-8')).toBe(String(process.pid));
    });

    it('refuses when a live process already holds the lock, reporting the holder pid', () => {
      // process.pid is alive as far as the service is concerned (it is not the
      // holder of this file): the real liveness check refuses us.
      fs.writeFileSync(lockPath, String(process.pid));
      const lock = new InstanceLockService(lockPath);

      const result = lock.acquire();

      expect(result).toEqual({ acquired: false, holderPid: process.pid });
      // The refusal must leave the holder's file untouched.
      expect(fs.readFileSync(lockPath, 'utf-8')).toBe(String(process.pid));
    });

    it('reclaims a stale lock file (dead holder pid) on retry and acquires it', () => {
      fs.writeFileSync(lockPath, String(DEAD_PID));
      const lock = new InstanceLockService(lockPath);

      const result = lock.acquire();

      expect(result).toEqual({ acquired: true });
      expect(fs.readFileSync(lockPath, 'utf-8')).toBe(String(process.pid));
    });

    it('reclaims an unreadable lock file (no valid pid inside) and acquires', () => {
      fs.writeFileSync(lockPath, 'not-a-pid');
      const lock = new InstanceLockService(lockPath);

      const result = lock.acquire();

      expect(result).toEqual({ acquired: true });
      expect(fs.readFileSync(lockPath, 'utf-8')).toBe(String(process.pid));
    });

    it('acquires again after release', () => {
      const lock = new InstanceLockService(lockPath);
      expect(lock.acquire()).toEqual({ acquired: true });
      lock.release();
      expect(fs.existsSync(lockPath)).toBe(false);

      const result = lock.acquire();

      expect(result).toEqual({ acquired: true });
      expect(fs.readFileSync(lockPath, 'utf-8')).toBe(String(process.pid));
    });

    it('creates the lock file inside a missing directory (data dir default layout)', () => {
      const nested = path.join(lockDir, 'data', 'racochu.watch.lock');
      const lock = new InstanceLockService(nested);

      const result = lock.acquire();

      expect(result).toEqual({ acquired: true });
      expect(fs.readFileSync(nested, 'utf-8')).toBe(String(process.pid));
    });
  });

  describe('release', () => {
    it('removes the lock file when this instance holds it', () => {
      const lock = new InstanceLockService(lockPath);
      lock.acquire();

      lock.release();

      expect(fs.existsSync(lockPath)).toBe(false);
    });

    it('is a no-op for a non-holder: another process’s lock file stays untouched', () => {
      fs.writeFileSync(lockPath, String(process.pid));
      const nonHolder = new InstanceLockService(lockPath);

      nonHolder.release();

      expect(fs.existsSync(lockPath)).toBe(true);
      expect(fs.readFileSync(lockPath, 'utf-8')).toBe(String(process.pid));
    });

    it('reports whether this process holds the lock', () => {
      const lock = new InstanceLockService(lockPath);
      expect(lock.holdsLock()).toBe(false);
      lock.acquire();
      expect(lock.holdsLock()).toBe(true);
      lock.release();
      expect(lock.holdsLock()).toBe(false);
    });
  });
});

describe('resolveWatchLockPath', () => {
  it('resolves the lock under the app data dir (same project-root resolution as the database)', () => {
    const expected = path.join(__dirname, '..', '..', '..', 'data', 'racochu.watch.lock');

    expect(resolveWatchLockPath()).toBe(expected);
  });
});
