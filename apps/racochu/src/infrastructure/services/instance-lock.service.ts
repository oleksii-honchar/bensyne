import fs from 'fs';
import path from 'path';
import { findProjectRoot } from '../prisma/prisma.service';

/**
 * C6 — watch-mode single-instance guard. An exclusive lock file under the
 * resolved data dir holds the holder's pid. Acquire is `open('wx')`; on
 * EEXIST the holder's liveness is checked with `process.kill(pid, 0)`:
 * alive ⇒ refuse (report the holder pid); dead or unreadable ⇒ unlink and
 * retry once. One-shot CLI modes never instantiate this service.
 */
export type LockAcquireResult = { acquired: true } | { acquired: false; holderPid: number | null };

export class InstanceLockService {
  private held = false;

  constructor(private readonly lockPath: string) {}

  acquire(): LockAcquireResult {
    fs.mkdirSync(path.dirname(this.lockPath), { recursive: true });
    if (this.tryCreate()) {
      this.held = true;
      return { acquired: true };
    }
    // EEXIST — the holder's liveness decides: alive ⇒ refuse untouched;
    // dead or unreadable ⇒ reclaim and retry exactly once.
    const firstHolder = this.readHolderPid();
    if (firstHolder !== null && this.isAlive(firstHolder)) {
      return { acquired: false, holderPid: firstHolder };
    }
    try {
      fs.unlinkSync(this.lockPath);
    } catch {
      // Already gone — the retry below still gets its one fresh attempt.
    }
    if (this.tryCreate()) {
      this.held = true;
      return { acquired: true };
    }
    // Lost the retry race — report the current holder without touching the file.
    return { acquired: false, holderPid: this.readHolderPid() };
  }

  /** Removes the lock only if this process holds it; a non-holder no-op. */
  release(): void {
    if (!this.held) {
      return;
    }
    this.held = false;
    try {
      fs.unlinkSync(this.lockPath);
    } catch {
      // Lock already removed externally — nothing left to clean up.
    }
  }

  holdsLock(): boolean {
    return this.held;
  }

  private tryCreate(): boolean {
    let fd: number | undefined;
    try {
      fd = fs.openSync(this.lockPath, 'wx');
      fs.writeSync(fd, String(process.pid));
      return true;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'EEXIST') {
        throw error;
      }
      return false;
    } finally {
      if (fd !== undefined) {
        fs.closeSync(fd);
      }
    }
  }

  private readHolderPid(): number | null {
    try {
      const raw = fs.readFileSync(this.lockPath, 'utf-8').trim();
      const pid = Number(raw);
      return Number.isSafeInteger(pid) && pid > 0 ? pid : null;
    } catch {
      return null;
    }
  }

  private isAlive(pid: number): boolean {
    try {
      process.kill(pid, 0);
      return true;
    } catch (error) {
      // EPERM means the process exists but cannot be signalled — still alive.
      return (error as NodeJS.ErrnoException).code === 'EPERM';
    }
  }
}

/**
 * Lock location for the current app installation: `<projectRoot>/data/` — the
 * same existing project-root resolution (findProjectRoot) used for the
 * database data dir. Never process.env.
 */
export function resolveWatchLockPath(): string {
  return path.join(findProjectRoot(__dirname), 'data', 'racochu.watch.lock');
}
