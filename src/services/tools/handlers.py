"""MCP tool handlers with memory bank routing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.domain.exceptions import ValidationError
from src.services.tools.validation import require_memory_bank
from src.utils.logging import log_tool_call

if TYPE_CHECKING:
    from src.services.bank.router import MemoryBankRouter


logger = logging.getLogger(__name__)


@log_tool_call("memory_remember")
async def handle_remember(router: MemoryBankRouter, arguments: dict) -> dict:
    """Store a durable memory in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    content = arguments.get("content")

    logger.debug("[memory_remember] Received arguments: memory_bank=%s, content=%r", memory_bank, content)

    if not content:
        raise ValidationError("content is required")

    logger.debug("[memory_remember] Getting instance for memory_bank=%s", memory_bank)
    instance = await router.get_instance(memory_bank)
    logger.debug("[memory_remember] Got instance, database=%s", instance._instance.db_path)

    # Extract only valid kwargs for Mnemosyne.remember()
    kwargs: Dict[str, Any] = {"content": content}
    for key in ("importance", "source", "scope", "valid_until", "extract_entities", "extract", "metadata", "veracity"):
        if key in arguments:
            kwargs[key] = arguments[key]

    result = instance.remember(**kwargs)
    # client.remember() returns {"memory_id": ..., "status": ...}
    memory_id = result.get("memory_id") if isinstance(result, dict) else result
    return {
        "status": result.get("status", "stored") if isinstance(result, dict) else "stored",
        "memory_id": memory_id,
        "memory_bank": memory_bank,
    }


@log_tool_call("memory_recall")
async def handle_recall(router: MemoryBankRouter, arguments: dict) -> dict:
    """Search for relevant memories in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    query = arguments.get("query")

    if not query:
        raise ValidationError("query is required")

    instance = await router.get_instance(memory_bank)

    limit = arguments.get("limit", 5)
    results = instance.recall(query=query, limit=limit)

    return {
        "results": results,
        "memory_bank": memory_bank,
    }


@log_tool_call("memory_forget")
async def handle_forget(router: MemoryBankRouter, arguments: dict) -> dict:
    """Delete a memory from the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(memory_bank)
    result = instance.forget(memory_id=memory_id)

    return {
        "status": result.get("status", "deleted"),
        "memory_id": memory_id,
        "memory_bank": memory_bank,
    }


@log_tool_call("memory_update")
async def handle_update(router: MemoryBankRouter, arguments: dict) -> dict:
    """Update memory content or importance in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(memory_bank)

    content: Optional[str] = arguments.get("content")
    importance: Optional[float] = arguments.get("importance")
    result = instance.update(memory_id=memory_id, content=content, importance=importance)

    return {
        "status": result.get("status", "updated"),
        "memory_id": memory_id,
        "memory_bank": memory_bank,
    }


@log_tool_call("memory_sleep")
async def handle_sleep(router: MemoryBankRouter, arguments: dict) -> dict:
    """Trigger memory consolidation in the specified memory bank."""
    memory_bank = require_memory_bank(arguments)

    instance = await router.get_instance(memory_bank)
    result = instance.sleep()

    return {
        **result,
        "memory_bank": memory_bank,
    }


@log_tool_call("memory_stats")
async def handle_stats(router: MemoryBankRouter, arguments: dict) -> dict:
    """Return memory statistics for the specified memory bank."""
    memory_bank = require_memory_bank(arguments)

    instance = await router.get_instance(memory_bank)
    stats = instance.stats()

    return {
        "stats": stats,
        "memory_bank": memory_bank,
    }


@log_tool_call("memory_list_banks")
async def handle_list_banks(router: MemoryBankRouter, arguments: dict) -> dict:
    """List all active memory banks with their status, descriptions, and memory counts.

    Includes both active instances AND registered memory banks (from registry).
    """
    banks: List[dict] = []
    seen: set[str] = set()

    # First: list all active instances
    for bank_name, client in router.instances.items():
        description = router.get_bank_description(bank_name)

        stats = client.stats()
        memory_count = 0
        if isinstance(stats, dict):
            working = stats.get("working_count") or stats.get("working") or 0
            episodic = stats.get("episodic_count") or stats.get("episodic") or 0
            memory_count = working + episodic

        banks.append({
            "name": bank_name,
            "bank": client.memory_bank,
            "description": description or "",
            "memory_count": memory_count,
            "status": "active",
        })
        seen.add(bank_name)

    # Then: include any registered banks that don't have an active instance yet
    for bank_name in router.registry.list_banks():
        if bank_name not in seen:
            description = router.get_bank_description(bank_name)
            banks.append({
                "name": bank_name,
                "bank": bank_name,
                "description": description or "",
                "memory_count": 0,
                "status": "registered",
            })

    return {
        "banks": banks,
    }


@log_tool_call("memory_register_bank")
async def handle_register_bank(router: MemoryBankRouter, arguments: dict) -> dict:
    """Register or update a memory bank description."""
    name = arguments.get("name")
    description = arguments.get("description")

    if not name:
        raise ValidationError("name is required")

    if not description:
        raise ValidationError("description is required")

    router.register_bank(name, description)

    return {
        "status": "registered",
        "name": name,
    }
