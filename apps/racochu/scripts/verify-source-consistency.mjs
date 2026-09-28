#!/usr/bin/env node
//
// Verify source consistency across all memory banks.
//
// Checks:
// 1. File-based sources: file → memory → episodic chain
// 2. Agent session banks: memory → episodic chain
// 3. Flags memories not connected to either files or episodic
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
    const issues = [];

    // Count memories in different tiers
    const memoriesCount = countQuery(dbPath, 'SELECT COUNT(*) FROM memories');
    const episodicCount = countQuery(dbPath, 'SELECT COUNT(*) FROM episodic_memory');
    const workingCount = countQuery(dbPath, 'SELECT COUNT(*) FROM working_memory');

    console.log(`Memories: ${memoriesCount}`);
    console.log(`Episodic: ${episodicCount}`);
    console.log(`Working: ${workingCount}`);

    if (isAgentSessionBank(bankName)) {
        // Agent session banks: verify memory → episodic chain
        console.log('Checking memory → episodic chain...');
        const missingEpisodic = countQuery(
            dbPath,
            'SELECT COUNT(*) FROM memories m WHERE NOT EXISTS (SELECT 1 FROM episodic_memory e WHERE e.id = m.id)'
        );
        if (missingEpisodic > 0) {
            issues.push(`${missingEpisodic} memories not in episodic_memory`);
        }

        // Check for episodic entries without memory table entries (post-ADR-13 style)
        const episodicWithoutMemory = countQuery(
            dbPath,
            'SELECT COUNT(*) FROM episodic_memory e WHERE NOT EXISTS (SELECT 1 FROM memories m WHERE m.id = e.id)'
        );
        if (episodicWithoutMemory > 0) {
            console.log(`Note: ${episodicWithoutMemory} episodic entries without memory table entries (post-ADR-13)`);
        }
    }

    if (isFileBasedBank(bankName)) {
        // File-based banks: verify file → memory → episodic chain
        console.log('Checking file → memory → episodic chain...');

        // Get file IDs from memory metadata
        const fileMemories = query(dbPath, 'SELECT id FROM memories WHERE metadata_json LIKE "%file_id%"');
        const fileMemoryIds = fileMemories.map(m => m.id);

        // Check that file memories have episodic entries
        if (fileMemoryIds.length > 0) {
            const missingEpisodic = countQuery(
                dbPath,
                `SELECT COUNT(*) FROM memories m WHERE m.metadata_json LIKE '%file_id%' AND NOT EXISTS (SELECT 1 FROM episodic_memory e WHERE e.id = m.id)`
            );
            if (missingEpisodic > 0) {
                issues.push(`${missingEpisodic} file memories not in episodic_memory`);
            }

            // Check that episodic entries have content
            const emptyContent = countQuery(
                dbPath,
                `SELECT COUNT(*) FROM episodic_memory e WHERE e.id IN (${fileMemoryIds.map(id => `'${id}'`).join(',')}) AND (e.content IS NULL OR e.content = '')`
            );
            if (emptyContent > 0) {
                issues.push(`${emptyContent} file episodic entries with empty content`);
            }
        }

        // Check FTS index coverage
        const ftsCount = countQuery(dbPath, 'SELECT COUNT(*) FROM fts_episodes');
        if (ftsCount < episodicCount) {
            issues.push(`FTS index incomplete (${ftsCount} < ${episodicCount})`);
        }
    }

    // Check for memories not connected to episodic (leftover pre-migration entries)
    const orphanedMemories = countQuery(
        dbPath,
        'SELECT COUNT(*) FROM memories m WHERE NOT EXISTS (SELECT 1 FROM episodic_memory e WHERE e.id = m.id)'
    );
    if (orphanedMemories > 0) {
        console.log(`Note: ${orphanedMemories} orphaned memories not in episodic_memory (pre-migration)`);
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
    const baseDir = process.argv[2] || BENSYNE_DATA_DIR;
    const bankName = process.argv[3] || null;

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