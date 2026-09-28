#!/usr/bin/env node
//
// Verify that all file memories in a bank are properly stored in
// the episodic memory database.
//
// Usage: node verify-file-memories-episodic.mjs [bank-name]
//        bank-name defaults to "vault_bensyne" if not specified
//
// This script:
// 1. Counts all memories in the bank
// 2. Counts all episodic entries
// 3. Verifies each memory has a corresponding episodic entry
// 4. Checks that memory content is not null
// 5. Checks FTS index coverage
//

import { execSync } from 'child_process';
import { existsSync } from 'fs';
import { homedir, tmpdir } from 'os';
import { mkdtempSync, writeFileSync, rmSync } from 'fs';
import { join } from 'path';

function runQuery(db, query) {
    try {
        const result = execSync(`sqlite3 -readonly -json "${db}" "${query}"`, {
            encoding: 'utf8',
            timeout: 30000,
        });
        return JSON.parse(result);
    } catch (e) {
        console.error(`Query failed: ${query}`);
        console.error(e.message);
        process.exit(1);
    }
}

function countQuery(db, query) {
    try {
        const result = execSync(`sqlite3 -readonly "${db}" "${query}"`, {
            encoding: 'utf8',
            timeout: 30000,
        });
        return parseInt(result.trim(), 10);
    } catch (e) {
        console.error(`Count query failed: ${query}`);
        console.error(e.message);
        process.exit(1);
    }
}

const BANK_NAME = process.argv[2] || 'vault_bensyne';

// Accept optional database path as third argument
let BANK_PATH = process.argv[3] || null;

// If no explicit path, try multiple base locations
if (!BANK_PATH) {
    const BASE_CANDIDATES = [
        `${homedir()}/.bensyne/data/banks`,
        './data/banks',
        `/home/tuiteraz/puma-lan/lite-llm/mcp/bensyne/data/banks`,
    ];

    for (const base of BASE_CANDIDATES) {
        if (existsSync(`${base}/${BANK_NAME}/mnemosyne.db`)) {
            BANK_PATH = `${base}/${BANK_NAME}/mnemosyne.db`;
            break;
        }
    }
}

if (!BANK_PATH) {
    console.error(`ERROR: Bank "${BANK_NAME}" not found.`);
    console.error('Usage: node verify-file-memories-episodic.mjs [bank-name] [db-path]');
    process.exit(1);
}

console.log(`Bank: ${BANK_NAME}`);
console.log(`Database: ${BANK_PATH}`);
console.log('');

// Copy database to temp location to avoid locking issues
const tmpDir = mkdtempSync(join(tmpdir(), 'verify-bank-'));
const tmpDb = join(tmpDir, 'mnemosyne.db');
try {
    execSync(`cp "${BANK_PATH}" "${tmpDb}"`, { encoding: 'utf8', timeout: 30000 });
    console.log(`Working on temp copy: ${tmpDb}`);
    console.log('');
} catch (e) {
    console.error(`Failed to copy database: ${e.message}`);
    process.exit(1);
}

let exitCode = 0;

console.log('=== Memory Verification ===');
console.log('');

// Count all memories in the bank
console.log('Step 1: Counting all memories in bank...');
const totalMemoryCount = countQuery(tmpDb, 'SELECT COUNT(*) FROM memories');
console.log(`Total memories: ${totalMemoryCount}`);

// Count episodic memories
console.log('');
console.log('Step 2: Counting episodic entries...');
const totalEpisodicCount = countQuery(tmpDb, 'SELECT COUNT(*) FROM episodic_memory');
console.log(`Total episodic entries: ${totalEpisodicCount}`);

// Check that all memories have episodic entries
console.log('');
console.log('Step 3: Verifying episodic coverage...');
const missingCount = countQuery(
    tmpDb,
    'SELECT COUNT(*) FROM memories m WHERE NOT EXISTS (SELECT 1 FROM episodic_memory e WHERE e.id = m.id)'
);

if (missingCount > 0) {
    console.log(`MISSING: ${missingCount} memories have no episodic entry`);
    exitCode = 1;
} else {
    console.log(`OK: All memories have episodic entries`);
}

// Check that episodic entries have content
console.log('');
console.log('Step 4: Verifying episodic content is populated...');
const nullContentCount = countQuery(
    tmpDb,
    "SELECT COUNT(*) FROM episodic_memory WHERE content IS NULL OR content = ''"
);

if (nullContentCount > 0) {
    console.log(`NULL/EMPTY CONTENT: ${nullContentCount} episodic entries have null or empty content`);
    exitCode = 1;
} else {
    console.log(`OK: All episodic entries have content`);
}

// Check working memory
console.log('');
console.log('Step 5: Checking working memory...');
const workingCount = countQuery(tmpDb, 'SELECT COUNT(*) FROM working_memory');
console.log(`Working memory entries: ${workingCount}`);

// Check consolidated facts
console.log('');
console.log('Step 6: Checking consolidated facts...');
const consolidatedCount = countQuery(tmpDb, 'SELECT COUNT(*) FROM consolidated_facts');
console.log(`Consolidated facts: ${consolidatedCount}`);

// Check FTS index
console.log('');
console.log('Step 7: Checking FTS index...');
const ftsCount = countQuery(tmpDb, 'SELECT COUNT(*) FROM fts_episodes');
console.log(`FTS index entries: ${ftsCount}`);

if (ftsCount < totalEpisodicCount) {
    console.log(`WARNING: FTS index has fewer entries (${ftsCount}) than episodic memory (${totalEpisodicCount})`);
    exitCode = 1;
} else {
    console.log(`OK: FTS index is complete`);
}

// Clean up temp directory
try {
    rmSync(tmpDir, { recursive: true, force: true });
} catch (e) {
    // Ignore cleanup errors
}

console.log('');
console.log('=== Summary ===');
if (exitCode === 0) {
    console.log(`PASS: All memories in "${BANK_NAME}" are properly stored in episodic memory`);
} else {
    console.log(`FAIL: Issues found in "${BANK_NAME}" (see above)`);
}

process.exit(exitCode);