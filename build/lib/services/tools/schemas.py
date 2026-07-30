"""Tool schemas with namespace parameter for MCP protocol."""

NAMESPACE_PARAM = {
    "namespace": {
        "type": "string",
        "description": "Memory namespace for isolation. Defaults to 'default' if not provided.",
        "default": "default",
    }
}

REMEMBER_SCHEMA = {
    "name": "mnemosyne_remember",
    "description": "Store a durable memory in Mnemosyne. Use for any fact, preference, identity, insight, or context that should persist across sessions. Higher importance (0.0-1.0) surfaces the memory more often.",
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The memory content to store."},
            "importance": {"type": "number", "description": "Importance 0.0-1.0. Default 0.5.", "default": 0.5},
            "source": {"type": "string", "description": "Source tag (e.g., user, tool, system). Default 'mcp'.", "default": "mcp"},
            **NAMESPACE_PARAM,
        },
        "required": ["content"],
    },
}

RECALL_SCHEMA = {
    "name": "mnemosyne_recall",
    "description": "Search Mnemosyne for relevant memories. Returns ranked results by vector similarity and text match.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Natural language query."},
            "limit": {"type": "integer", "description": "Max results. Default 5.", "default": 5},
            **NAMESPACE_PARAM,
        },
        "required": ["query"],
    },
}

FORGET_SCHEMA = {
    "name": "mnemosyne_forget",
    "description": "Permanently delete a memory by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "ID of the memory to delete"},
            **NAMESPACE_PARAM,
        },
        "required": ["memory_id"],
    },
}

UPDATE_SCHEMA = {
    "name": "mnemosyne_update",
    "description": "Update the content or importance of an existing memory by ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "ID of the memory to update"},
            "content": {"type": "string", "description": "New content for the memory (optional)"},
            "importance": {"type": "number", "description": "New importance from 0.0 to 1.0 (optional)"},
            **NAMESPACE_PARAM,
        },
        "required": ["memory_id"],
    },
}

SLEEP_SCHEMA = {
    "name": "mnemosyne_sleep",
    "description": "Run the Mnemosyne consolidation cycle. Compresses old working memories into episodic summaries.",
    "parameters": {
        "type": "object",
        "properties": {
            **NAMESPACE_PARAM,
        },
    },
}

STATS_SCHEMA = {
    "name": "mnemosyne_stats",
    "description": "Return Mnemosyne memory statistics: working count, episodic count.",
    "parameters": {
        "type": "object",
        "properties": {
            **NAMESPACE_PARAM,
        },
    },
}

LIST_NAMESPACES_SCHEMA = {
    "name": "mnemosyne_list_namespaces",
    "description": "List all available memory namespaces with their status and memory counts.",
    "parameters": {
        "type": "object",
        "properties": {},
    },
}

ALL_TOOL_SCHEMAS = [
    REMEMBER_SCHEMA,
    RECALL_SCHEMA,
    FORGET_SCHEMA,
    UPDATE_SCHEMA,
    SLEEP_SCHEMA,
    STATS_SCHEMA,
    LIST_NAMESPACES_SCHEMA,
]
