#!/usr/bin/env node
//
// Cleanup legacy `memories` table entries across all memory banks.
//
// The `memories` table is write-only and never read in the BEAM architecture.
// This script deletes all entries from the `memories` table to reduce
// confusion and database clutter.
//
// BEAM architecture notes:
// - `memories` table is legacy (write-only, never read) — all active data is in `episodic_memory`
// - This cleanup is safe and does not affect recall or persona operations
//
// Usage: node scripts/cleanup-legacy-memories.mjs [bank-name]
//        bank-name defaults to all banks if not specified
//
// Options:
//   --base=<path>     Base directory containing banks (default: ../../bensyne-mcp/data)
//   --dry-run         Show what would be deleted without actually deleting
//
// Exit codes:
//   0 — Success (all banks cleaned or dry-run completed)
//   1 — Error (bank not found, database error, etc.)
//

import { execSync } from 'child_process';
import { existsSync, readdirSync, mkdtempSync, rmSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { tmpdir } from 'os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BENSYNE_DATA_DIR = process.env.BENSYNE_DATA_DIR || `${__dirname}/../../bensyne-mcp/data`;

function query(db, sql) {
    try {
        const result = execSync(`sqlite3 -readonly "${db}"`, {
            input: sql,
            encoding: 'utf8',
            timeout: 30000,
        });
        return result.trim();
    } catch (e) {
        console.error(`Query failed: ${sql}`);
        console.error(e.message);
        return '';
    }
}

function execute(db, sql) {
    try {
        const result = execSync(`sqlite3 "${db}"`, {
            input: sql,
            encoding: 'utf8',
            timeout: 30000,
        });
        return result.trim();
    } catch (e) {
        console.error(`Execution failed: ${sql}`);
        console.error(e.message);
        throw e;
    }
}

async function cleanupBank(bankName, dbPath, dryRun) {
    console.log(`\n=== Cleaning bank: ${bankName} ===`);

    // Copy database to temp location to avoid WAL mode issues
    const tmpDir = mkdtempSync(join(tmpdir(), 'cleanup-bank-'));
    const tmpDb = join(tmpDir, 'mnemosyne.db');
    try {
        execSync(`cp "${dbPath}" "${tmpDb}"`, { encoding: 'utf8', timeout: 30000 });
    } catch (e) {
        console.error(`Failed to copy database: ${e.message}`);
        rmSync(tmpDir, { recursive: true, force: true });
        return false;
    }

    console.log(`Working on temp copy: ${tmpDb}`);

    // Count legacy memories before cleanup
    const countBefore = query(tmpDb, 'SELECT COUNT(*) FROM memories');
    console.log(`Legacy memories before cleanup: ${countBefore}`);

    if (dryRun) {
        console.log(`[DRY RUN] Would delete ${countBefore} legacy memories from bank: ${bankName}`);
        // Clean up temp directory
        rmSync(tmpDir, { recursive: true, force: true });
        return true;
    }

    // Delete all entries from memories table
    execute(tmpDb, 'DELETE FROM memories;');

    // Count after cleanup
    const countAfter = query(tmpDb, 'SELECT COUNT(*) FROM memories');
    console.log(`Legacy memories after cleanup: ${countAfter}`);

    if (countAfter !== '0') {
        console.error(`FAIL: Expected 0 memories after cleanup, got ${countAfter}`);
        rmSync(tmpDir, { recursive: true, force: true });
        return false;
    }

    // Vacuum the database to reclaim space
    console.log('Vacuuming database...');
    execute(tmpDb, 'VACUUM;');

    // Copy cleaned database back
    console.log('Copying cleaned database back...');
    try {
        execSync(`cp "${tmpDb}" "${dbPath}"`, { encoding: 'utf8', timeout: 30000 });
    } catch (e) {
        console.error(`Failed to copy cleaned database back: ${e.message}`);
        rmSync(tmpDir, { recursive: true, force: true });
        return false;
    }

    // Clean up temp directory
    rmSync(tmpDir, { recursive: true, force: true });

    console.log(`PASS: Cleaned ${countBefore} legacy memories from bank: ${bankName}`);
    return true;
}

async function main() {
    let baseDir = null;
    let bankName = null;
    let dryRun = false;

    for (let i = 2; i < process.argv.length; i++) {
        const arg = process.argv[i];
        if (arg.startsWith('--base=')) {
            baseDir = arg.slice(7);
        } else if (arg === '--dry-run') {
            dryRun = true;
        } else if (arg.startsWith('/')) {
            baseDir = arg;
        } else {
            bankName = arg;
        }
    }

    if (!baseDir) {
        baseDir = BENSYNE_DATA_DIR;
    }

    if (dryRun) {
        console.log('DRY RUN MODE: No changes will be made to the databases.');
    }

    if (bankName) {
        const dbPath = join(baseDir, 'banks', bankName, 'mnemosyne.db');
        if (!existsSync(dbPath)) {
            console.error(`ERROR: Bank "${bankName}" not found at ${dbPath}`);
            process.exit(1);
        }
        const success = await cleanupBank(bankName, dbPath, dryRun);
        process.exit(success ? 0 : 1);
    } else {
        // Clean all banks
        const banksDir = join(baseDir, 'banks');
        if (!existsSync(banksDir)) {
            console.error(`ERROR: Banks directory not found at ${banksDir}`);
            process.exit(1);
        }

        const banks = readdirSync(banksDir);
        let allPassed = true;
        let totalCleaned = 0;

        for (const bank of banks) {
            const dbPath = join(banksDir, bank, 'mnemosyne.db');
            if (existsSync(dbPath)) {
                const success = await cleanupBank(bank, dbPath, dryRun);
                if (!success) allPassed = false;
            }
        }

        console.log(`\n=== Summary ===`);
        if (dryRun) {
            console.log(`[DRY RUN] Completed. No databases were modified.`);
        } else {
            console.log(`Cleanup completed. ${allPassed ? 'All' : 'Some'} banks were cleaned successfully.`);
        }
        process.exit(allPassed ? 0 : 1);
    }
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});