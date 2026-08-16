import * as fs from 'fs/promises';

module.exports = async (): Promise<void> => {
  // Stop Bensyne
  const stopBensyne = (globalThis as unknown as Record<string, unknown>).__BENSYNE_STOP__ as
    (() => Promise<void>) | undefined;
  if (stopBensyne != null) {
    await stopBensyne();
  }
  delete (globalThis as unknown as Record<string, unknown>).__BENSYNE_STOP__;

  // Clean up temp root (contains config + watch dir) — set by global-setup.ts
  const e2eRoot = process.env.E2E_TEMP_ROOT;
  if (e2eRoot != null) {
    try {
      await fs.rm(e2eRoot, { recursive: true, force: true });
      console.log(`[E2E-GlobalTeardown] Temp root cleaned up: ${e2eRoot}`);
    } catch {
      // Ignore cleanup errors
    }
  }
  delete process.env.E2E_TEMP_ROOT;
  delete process.env.E2E_WATCH_DIR;
  delete process.env.E2E_OBSIDIAN_WATCH_DIR;
  delete process.env.E2E_DATA_DIR;
};
