#!/usr/bin/env node
//
// Verify source consistency across all memory banks (BEAM architecture).
//
// BEAM architecture notes:
// - `memories` table is legacy (write-only, never read) — check `episodic_memory` directly
// - `file_chunks` index links file-backed memories (node_memories in getPersonaStatus)
// - Memories are classified by file association and temporality, not by table placement
//
// Checks:
// 1. Episodic memory count (direct, not via legacy `memories` table)
// 2. Legacy `memories` table entries (should be 0 — write-only, never read)
// 3. file_chunks index integrity for file-backed memories
// 4. Orphaned file_chunks entries (chunks without corresponding episodic memories)
// 5. Missing index entries (episodic memories that should be file-backed but lack file_chunks)
// 6. FTS index coverage
//
// Usage: npx dotenvx run -- node scripts/verify-source-consistency.mjs [bank-name]
//        bank-name defaults to all banks if not specified
//

import { execSync } from 'child_process';
import { existsSync, readdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const BENSYNE_DATA_DIR = process.env.BENSYNE_DATA_DIR || `${__dirname}/../../bensyne-mcp/data`;
const RACOCHU_DB = process.env.RACOCHU_DB || `${__dirname}/../data/racochu.db`;

function query(db, sql) {
    try {
        const result = execSync(`sqlite3 -readonly -json "${db}"`, {
            input: sql,
            encoding: 'utf8',
            timeout: 30000,
        });
        const rows = JSON.parse(result);
        return rows;
    } catch (e) {
        console.error(`Query failed: ${sql}`);
        console.error(e.message);
        return [];
    }
}

function countQuery(db, sql) {
    try {
        const result = execSync(`sqlite3 -readonly "${db}"`, {
            input: sql,
            encoding: 'utf8',
            timeout: 30000,
        });
        return parseInt(result.trim(), 10);
    } catch (e) {
        console.error(`Count query failed: ${sql}`);
        console.error(e.message);
        return 0;
    }
}

function isAgentSessionBank(bankName) {
    return bankName.startsWith('agent-session-') || bankName === 'agent-sessions';
}

function isFileBasedBank(bankName) {
    return bankName.startsWith('vault_') || bankName.startsWith('obsidian_') || bankName.startsWith('agent-persona_');
}

async function verifyBank(bankName, dbPath) {
    console.log(`\n=== Verifying bank: ${bankName} ===`);
    console.log(`Working on: ${dbPath}`);
    const issues = [];

    // In BEAM architecture, episodic_memory is the primary table.
    // The `memories` table is legacy (write-only, never read).
    const episodicCount = countQuery(dbPath, 'SELECT COUNT(*) FROM episodic_memory');
    console.log(`Episodic memories: ${episodicCount}`);

    // Check 2: Legacy `memories` table should be empty (write-only, never read in BEAM)
    const legacyMemoriesCount = countQuery(dbPath, 'SELECT COUNT(*) FROM memories');
    console.log(`Legacy memories table entries: ${legacyMemoriesCount}`);
    if (legacyMemoriesCount > 0) {
        issues.push(`Legacy 'memories' table has ${legacyMemoriesCount} entries (should be 0 — run cleanup-legacy-memories.mjs)`);
    }

    if (isAgentSessionBank(bankName)) {
        // Agent session banks: verify episodic entries are present
        console.log('Checking episodic_memory entries...');

        // Check that episodic entries have content
        const emptyContent = countQuery(
            dbPath,
            'SELECT COUNT(*) FROM episodic_memory WHERE content IS NULL OR content = ""'
        );
        if (emptyContent > 0) {
            issues.push(`${emptyContent} episodic memories with empty content`);
        }
    }

    if (isFileBasedBank(bankName)) {
        // File-based banks: verify file_chunks index integrity
        console.log('Checking file_chunks index integrity...');

        // Check 1: Orphaned file_chunks entries (chunks without corresponding episodic memories)
        const orphanedChunks = countQuery(
            dbPath,
            'SELECT COUNT(*) FROM file_chunks fc WHERE NOT EXISTS (SELECT 1 FROM episodic_memory em WHERE em.id = fc.memory_id)'
        );
        if (orphanedChunks > 0) {
            issues.push(`${orphanedChunks} orphaned file_chunks entries (no corresponding episodic memory)`);
        }

        // Check 2: Episodic memories that should be file-backed but lack file_chunks entries
        // A memory is considered "should be file-backed" if its metadata_json contains file_id
        const fileBackedWithoutChunks = countQuery(
            dbPath,
            'SELECT COUNT(*) FROM episodic_memory em WHERE em.metadata_json LIKE "%file_id%" AND NOT EXISTS (SELECT 1 FROM file_chunks fc WHERE fc.memory_id = em.id)'
        );
        if (fileBackedWithoutChunks > 0) {
            issues.push(`${fileBackedWithoutChunks} episodic memories that should be file-backed but lack file_chunks entries`);
        }

        // Check 3: Verify file_chunks have valid file IDs
        const chunksWithoutFile = countQuery(
            dbPath,
            'SELECT COUNT(*) FROM file_chunks fc WHERE fc.file_id IS NULL OR fc.file_id = ""'
        );
        if (chunksWithoutFile > 0) {
            issues.push(`${chunksWithoutFile} file_chunks entries without valid file_id`);
        }

        // Check FTS index coverage
        const ftsCount = countQuery(dbPath, 'SELECT COUNT(*) FROM fts_episodes');
        if (ftsCount < episodicCount) {
            issues.push(`FTS index incomplete (${ftsCount} < ${episodicCount})`);
        }
    }

    if (issues.length > 0) {
        console.log(`FAIL: ${bankName}`);
        issues.forEach(issue => console.log(`  - ${issue}`));
        return false;
    }

    console.log(`PASS: ${bankName}`);
    return true;
}

async function main() {
    let baseDir = null;
    let bankName = null;

    for (let i = 2; i < process.argv.length; i++) {
        const arg = process.argv[i];
        if (arg.startsWith('--base=')) {
            baseDir = arg.slice(7);
        } else if (arg.startsWith('/')) {
            baseDir = arg;
        } else {
            bankName = arg;
        }
    }

    if (!baseDir) {
        baseDir = BENSYNE_DATA_DIR;
    }

    if (bankName) {
        const dbPath = join(baseDir, 'banks', bankName, 'mnemosyne.db');
        if (!existsSync(dbPath)) {
            console.error(`ERROR: Bank "${bankName}" not found at ${dbPath}`);
            process.exit(1);
        }
        const success = await verifyBank(bankName, dbPath);
        process.exit(success ? 0 : 1);
    } else {
        // Verify all banks
        const banksDir = join(baseDir, 'banks');
        if (!existsSync(banksDir)) {
            console.error(`ERROR: Banks directory not found at ${banksDir}`);
            process.exit(1);
        }

        const banks = readdirSync(banksDir);
        let allPassed = true;

        for (const bank of banks) {
            const dbPath = join(banksDir, bank, 'mnemosyne.db');
            if (existsSync(dbPath)) {
                const success = await verifyBank(bank, dbPath);
                if (!success) allPassed = false;
            }
        }

        console.log(`\n=== Summary ===`);
        if (allPassed) {
            console.log('All banks passed verification.');
            process.exit(0);
        } else {
            console.log('Some banks failed verification.');
            process.exit(1);
        }
    }
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});