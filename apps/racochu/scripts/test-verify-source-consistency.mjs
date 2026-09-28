#!/usr/bin/env node
// Test harness for verify-source-consistency.mjs
// Creates test databases with various scenarios and runs the verification script

import { execSync } from 'child_process';
import { mkdtempSync, rmSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { tmpdir } from 'os';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SCRIPT = join(__dirname, 'verify-source-consistency.mjs');

function setupTestBank(name, setupSql) {
    const baseDir = mkdtempSync(join(tmpdir(), `verify-test-${name}-`));
    const banksDir = join(baseDir, 'banks', name);
    execSync(`mkdir -p "${banksDir}"`);
    const dbPath = join(banksDir, 'mnemosyne.db');

    // Create empty database
    execSync(`sqlite3 "${dbPath}" ""`);

    // Run setup SQL
    const allSql = `
CREATE TABLE IF NOT EXISTS episodic_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    source TEXT DEFAULT 'test',
    importance REAL DEFAULT 0.5,
    metadata_json TEXT DEFAULT '{}',
    veracity REAL DEFAULT 1.0,
    memory_type TEXT DEFAULT 'episodic',
    created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_until TEXT
);
CREATE TABLE IF NOT EXISTS file_chunks (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    start_line INTEGER,
    end_line INTEGER
);
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    file_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS working_memory (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_episodes USING fts5(content);
${setupSql}
`;
    execSync(`sqlite3 "${dbPath}"`, { input: allSql, encoding: 'utf8' });
    return { baseDir, dbPath };
}

function runVerify(baseDir, bankName, expectFail = false) {
    try {
        const result = execSync(`node "${SCRIPT}" --base="${baseDir}" "${bankName}"`, {
            encoding: 'utf8',
            timeout: 60000,
        });
        console.log(result);
        if (expectFail) {
            console.log('❌ Expected FAIL but got PASS');
            return false;
        }
        console.log('✅ PASS as expected');
        return true;
    } catch (e) {
        if (expectFail) {
            console.log(e.output ? e.output.join('') : e.message);
            console.log('✅ FAIL as expected');
            return true;
        }
        console.log(e.output ? e.output.join('') : e.message);
        console.log('❌ Unexpected FAIL');
        return false;
    }
}

function cleanup(baseDir) {
    rmSync(baseDir, { recursive: true, force: true });
}

let allPassed = true;

// Test 1: Clean episodic entries, no file_chunks needed (agent-session bank)
console.log('\n=== Test 1: Clean episodic entries (agent-session bank) ===');
{
    const { baseDir, dbPath } = setupTestBank('agent-session-test', `
        INSERT INTO episodic_memory (id, content, source) VALUES
            ('mem1', 'This is a test memory', 'test'),
            ('mem2', 'Another test memory', 'test');
    `);
    allPassed = runVerify(baseDir, 'agent-session-test') && allPassed;
    cleanup(baseDir);
}

// Test 2: Empty episodic memory content
console.log('\n=== Test 2: Empty episodic content (should FAIL) ===');
{
    const { baseDir, dbPath } = setupTestBank('agent-session-empty', `
        INSERT INTO episodic_memory (id, content, source) VALUES
            ('mem1', '', 'test');
    `);
    allPassed = runVerify(baseDir, 'agent-session-empty', true) && allPassed;
    cleanup(baseDir);
}

// Test 3: Clean file-based bank with proper file_chunks
console.log('\n=== Test 3: Clean file-based bank with proper file_chunks ===');
{
    const { baseDir, dbPath } = setupTestBank('vault_clean', `
        INSERT INTO episodic_memory (id, content, source, metadata_json) VALUES
            ('mem1', 'File content 1', 'test', '{"file_id": "file1"}');
        INSERT INTO file_chunks (id, file_id, memory_id, chunk_index) VALUES
            ('chunk1', 'file1', 'mem1', 0);
        INSERT INTO files (id, file_path) VALUES
            ('file1', '/test/file1.txt');
        INSERT INTO fts_episodes (content) VALUES ('File content 1');
    `);
    allPassed = runVerify(baseDir, 'vault_clean') && allPassed;
    cleanup(baseDir);
}

// Test 4: Orphaned file_chunks (no corresponding episodic memory)
console.log('\n=== Test 4: Orphaned file_chunks (should FAIL) ===');
{
    const { baseDir, dbPath } = setupTestBank('vault_orphaned_chunks', `
        INSERT INTO file_chunks (id, file_id, memory_id, chunk_index) VALUES
            ('chunk1', 'file1', 'missing_mem', 0);
        INSERT INTO files (id, file_path) VALUES
            ('file1', '/test/file1.txt');
    `);
    allPassed = runVerify(baseDir, 'vault_orphaned_chunks', true) && allPassed;
    cleanup(baseDir);
}

// Test 5: File-backed episodic without file_chunks entry
console.log('\n=== Test 5: File-backed episodic without file_chunks (should FAIL) ===');
{
    const { baseDir, dbPath } = setupTestBank('vault_missing_chunks', `
        INSERT INTO episodic_memory (id, content, source, metadata_json) VALUES
            ('mem1', 'File content 1', 'test', '{"file_id": "file1"}');
        INSERT INTO files (id, file_path) VALUES
            ('file1', '/test/file1.txt');
    `);
    allPassed = runVerify(baseDir, 'vault_missing_chunks', true) && allPassed;
    cleanup(baseDir);
}

// Test 6: File_chunks with invalid file_id
console.log('\n=== Test 6: file_chunks with empty file_id (should FAIL) ===');
{
    const { baseDir, dbPath } = setupTestBank('vault_bad_file_id', `
        INSERT INTO episodic_memory (id, content, source, metadata_json) VALUES
            ('mem1', 'File content 1', 'test', '{"file_id": "file1"}');
        INSERT INTO file_chunks (id, file_id, memory_id, chunk_index) VALUES
            ('chunk1', '', 'mem1', 0);
    `);
    allPassed = runVerify(baseDir, 'vault_bad_file_id', true) && allPassed;
    cleanup(baseDir);
}

// Test 7: Incomplete FTS index
console.log('\n=== Test 7: Incomplete FTS index (should FAIL) ===');
{
    const { baseDir, dbPath } = setupTestBank('vault_incomplete_fts', `
        INSERT INTO episodic_memory (id, content, source, metadata_json) VALUES
            ('mem1', 'File content 1', 'test', '{"file_id": "file1"}'),
            ('mem2', 'File content 2', 'test', '{"file_id": "file2"}');
        INSERT INTO file_chunks (id, file_id, memory_id, chunk_index) VALUES
            ('chunk1', 'file1', 'mem1', 0),
            ('chunk2', 'file2', 'mem2', 0);
        INSERT INTO files (id, file_path) VALUES
            ('file1', '/test/file1.txt'),
            ('file2', '/test/file2.txt');
        INSERT INTO fts_episodes (content) VALUES ('File content 1');
    `);
    allPassed = runVerify(baseDir, 'vault_incomplete_fts', true) && allPassed;
    cleanup(baseDir);
}

console.log('\n=== Summary ===');
if (allPassed) {
    console.log('✅ All tests passed');
    process.exit(0);
} else {
    console.log('❌ Some tests failed');
    process.exit(1);
}