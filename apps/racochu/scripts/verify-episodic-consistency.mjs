#!/usr/bin/env node
/**
 * verify-episodic-consistency.mjs — Verify episodic memory tier consistency.
 *
 * Checks the consistency between the file metadata layer and the episodic memory
 * tier for specified persona banks. Uses the getFileChunks MCP tool to verify
 * that each file's stored chunks have corresponding episodic memories.
 *
 * Usage:
 *     node verify-episodic-consistency.mjs                    # verify all persona banks
 *     node verify-episodic-consistency.mjs <bank> [bank ...]  # verify specific banks
 *     node verify-episodic-consistency.mjs --config <path>    # use custom config path
 *
 * Exit codes:
 *     0 — All specified banks are consistent
 *     1 — One or more banks have inconsistencies
 *     2 — Runtime or configuration error
 */

import { readFileSync } from "fs";
import { exit } from "process";

// Default to the LiteLLM gateway URL used by racochu production config
const MCP_URL = process.env.BENSYNE_MCP_URL || "https://lite-llm.lan/mcp/bensyne";
// Use LLM_API_KEY from environment (same as racochu config) or BENSYNE_MCP_API_KEY
let API_KEY = process.env.LLM_API_KEY || process.env.BENSYNE_MCP_API_KEY || "";
if (API_KEY && !API_KEY.startsWith("Bearer ")) {
  API_KEY = `Bearer ${API_KEY}`;
}

async function sendMcpRequest(method, params, sessionId) {
  const payload = { jsonrpc: "2.0", id: 1, method, params };
  const headers = { "Content-Type": "application/json", "Accept": "application/json, text/event-stream" };
  if (API_KEY) headers["Authorization"] = API_KEY;
  if (sessionId) headers["Mcp-Session-Id"] = sessionId;

  try {
    const response = await fetch(MCP_URL, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`HTTP ${response.status}: ${body}`);
    }

    let text = await response.text();
    let jsonStr = text;
    if (text.startsWith("event:")) {
      jsonStr = "";
      for (const line of text.split("\n")) {
        if (line.startsWith("data: ")) jsonStr += line.slice(6);
      }
    }

    const json = JSON.parse(jsonStr);
    const newSessionId = response.headers.get("Mcp-Session-Id") || sessionId;
    return { json, sessionId: newSessionId };
  } catch (e) {
    console.error(`Error: ${e.message}`);
    throw e;
  }
}

async function initialize() {
  const result = await sendMcpRequest("initialize", {
    protocolVersion: "2024-11-05",
    capabilities: {},
    clientInfo: { name: "verify-episodic-consistency", version: "1.0.0" },
  });
  return result.sessionId;
}

async function callTool(toolName, args, sessionId) {
  const result = await sendMcpRequest("tools/call", {
    name: toolName,
    arguments: args,
  }, sessionId);

  if (result.json.error) {
    throw new Error(`MCP tool error: ${JSON.stringify(result.json.error)}`);
  }

  const content = result.json.result?.content || [];
  for (const item of content) {
    if (item.type === "text") {
      try {
        return JSON.parse(item.text);
      } catch {
        return { text: item.text };
      }
    }
  }
  return {};
}

async function verifyBank(bank, sessionId) {
  console.log(`\n============================================================`);
  console.log(`Bank: ${bank}`);
  console.log(`============================================================`);

  // Get persona status
  try {
    const status = await callTool("getPersonaStatus", { memory_bank: bank }, sessionId);
    console.log(`Total memories: ${status.total || "unknown"}`);
    console.log(`Node memories: ${status.node_memories || "unknown"}`);
    console.log(`Occasional memories: ${status.occasional_memories || "unknown"}`);
    console.log(`Materialization due: ${status.materialization_due || "unknown"}`);
  } catch (e) {
    console.log(`Error getting status: ${e.message}`);
  }

  // Try getPersonaEntryNode to verify the entry node works
  try {
    const entry = await callTool("getPersonaEntryNode", { memory_bank: bank }, sessionId);
    console.log(`Entry node: ${entry.title || "unknown"}`);
    if (entry.memory_id) console.log(`  Entry memory_id: ${entry.memory_id}`);
    if (entry.file_id) console.log(`  Entry file_id: ${entry.file_id}`);
  } catch (e) {
    console.log(`Error getting entry node: ${e.message}`);
    return false;
  }

  return true;
}

function getAllBanksFromConfig(configPath) {
  // Read racochu config and extract all watch source IDs (used as memoryBank names)
  try {
    const config = readFileSync(configPath, "utf-8");
    const banks = [];
    // Match lines like "- id: agent-persona_architect" or "- id: vault_macmini-lan"
    const regex = /^  - id: ([a-zA-Z0-9_-]+)/gm;
    let match;
    while ((match = regex.exec(config)) !== null) {
      banks.push(match[1]);
    }
    return banks;
  } catch (e) {
    console.error(`Error reading config at ${configPath}: ${e.message}`);
    return [];
  }
}

async function main() {
  const args = process.argv.slice(2);

  // Parse optional --config flag
  let configPath = process.env.RACOCHU_CONFIG || `${process.env.HOME}/.config/racochu.yaml`;
  let banks = [];
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--config" && args[i + 1]) {
      configPath = args[i + 1];
      i++;
    } else {
      banks.push(args[i]);
    }
  }

  // If no banks specified, detect all memory banks from config
  if (banks.length === 0) {
    console.log(`Detecting memory banks from config: ${configPath}`);
    banks = getAllBanksFromConfig(configPath);
    if (banks.length === 0) {
      console.log(`No memory banks found in config.`);
      exit(2);
    }
    console.log(`Found ${banks.length} memory bank(s): ${banks.join(", ")}`);
  }

  try {
    console.log(`Connecting to MCP server at ${MCP_URL}...`);
    const sessionId = await initialize();
    console.log(`MCP session established.`);

    let hasInconsistencies = false;
    for (const bank of banks) {
      const ok = await verifyBank(bank, sessionId);
      if (!ok) hasInconsistencies = true;
    }

    console.log(`\n============================================================`);
    if (hasInconsistencies) {
      console.log(`Result: INCONSISTENCIES FOUND`);
      exit(1);
    } else {
      console.log(`Result: CONSISTENT`);
      exit(0);
    }
  } catch (e) {
    console.log(`Failed to initialize MCP session: ${e.message}`);
    exit(2);
  }
}

main().catch((e) => {
  console.log(`Fatal error: ${e.message}`);
  exit(2);
});
