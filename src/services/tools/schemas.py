"""Tool schemas with memory_bank parameter for MCP protocol."""

MEMORY_BANK_PARAM = {
    "memory_bank": {
        "type": "string",
        "description": "Memory bank for isolation. This parameter is required.",
    }
}

REMEMBER_SCHEMA = {
    "name": "memory_remember",
    "description": "Store a durable memory in Mnemosyne. Use for any fact, preference, identity, insight, or context that should persist across sessions. Higher importance (0.0-1.0) surfaces the memory more often.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The memory content to store."},
            "importance": {"type": "number", "description": "Importance 0.0-1.0. Default 0.5.", "default": 0.5},
            "source": {"type": "string", "description": "Source tag (e.g., user, tool, system). Default 'mcp'.", "default": "mcp"},
            **MEMORY_BANK_PARAM,
        },
        "required": ["content", "memory_bank"],
    },
}

RECALL_SCHEMA = {
    "name": "memory_recall",
    "description": "Search Mnemosyne for relevant memories. Returns ranked results by vector similarity and text match.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language query."},
            "limit": {"type": "integer", "description": "Max results. Default 5.", "default": 5},
            **MEMORY_BANK_PARAM,
        },
        "required": ["query", "memory_bank"],
    },
}

FORGET_SCHEMA = {
    "name": "memory_forget",
    "description": "Permanently delete a memory by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "ID of the memory to delete"},
            **MEMORY_BANK_PARAM,
        },
        "required": ["memory_id", "memory_bank"],
    },
}

UPDATE_SCHEMA = {
    "name": "memory_update",
    "description": "Update the content or importance of an existing memory by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "ID of the memory to update"},
            "content": {"type": "string", "description": "New content for the memory (optional)"},
            "importance": {"type": "number", "description": "New importance from 0.0 to 1.0 (optional)"},
            **MEMORY_BANK_PARAM,
        },
        "required": ["memory_id", "memory_bank"],
    },
}

SLEEP_SCHEMA = {
    "name": "memory_sleep",
    "description": "Run the Mnemosyne consolidation cycle. Compresses old working memories into episodic summaries.",
    "parameters": {
        "type": "object",
        "properties": {
            **MEMORY_BANK_PARAM,
        },
        "required": ["memory_bank"],
    },
}

STATS_SCHEMA = {
    "name": "memory_stats",
    "description": "Return Mnemosyne memory statistics: working count, episodic count.",
    "parameters": {
        "type": "object",
        "properties": {
            **MEMORY_BANK_PARAM,
        },
        "required": ["memory_bank"],
    },
}

LIST_BANKS_SCHEMA = {
    "name": "memory_list_banks",
    "description": "List all available memory banks with their status and memory counts.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

REGISTER_BANK_SCHEMA = {
    "name": "memory_register_bank",
    "description": "Register a new memory bank with a description. Use to create named banks for isolating different memory contexts (e.g., projects, users, domains).",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Memory bank name (e.g., 'project-alpha', 'user-123')."},
            "description": {"type": "string", "description": "Human-readable description of the memory bank purpose."},
        },
        "required": ["name", "description"],
    },
}

ALL_TOOL_SCHEMAS = [
    REMEMBER_SCHEMA,
    RECALL_SCHEMA,
    FORGET_SCHEMA,
    UPDATE_SCHEMA,
    SLEEP_SCHEMA,
    STATS_SCHEMA,
    LIST_BANKS_SCHEMA,
    REGISTER_BANK_SCHEMA,
]
