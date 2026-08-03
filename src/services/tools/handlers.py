"""MCP tool handlers with namespace routing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.domain.exceptions import ValidationError
from src.services.tools.validation import require_namespace
from src.utils.logging import log_tool_call

if TYPE_CHECKING:
    from src.services.namespace.router import NamespaceRouter


logger = logging.getLogger(__name__)


@log_tool_call("mnemosyne_remember")
async def handle_remember(router: NamespaceRouter, arguments: dict) -> dict:
    """Store a durable memory in the specified namespace."""
    namespace = require_namespace(arguments)
    content = arguments.get("content")

    logger.debug("[mnemosyne_remember] Received arguments: namespace=%s, content=%r", namespace, content)

    if not content:
        raise ValidationError("content is required")

    logger.debug("[mnemosyne_remember] Getting instance for namespace=%s", namespace)
    instance = await router.get_instance(namespace)
    logger.debug("[mnemosyne_remember] Got instance, database=%s", instance._instance.db_path)

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
        "namespace": namespace,
    }


@log_tool_call("mnemosyne_recall")
async def handle_recall(router: NamespaceRouter, arguments: dict) -> dict:
    """Search for relevant memories in the specified namespace."""
    namespace = require_namespace(arguments)
    query = arguments.get("query")

    if not query:
        raise ValidationError("query is required")

    instance = await router.get_instance(namespace)

    limit = arguments.get("limit", 5)
    results = instance.recall(query=query, limit=limit)

    return {
        "results": results,
        "namespace": namespace,
    }


@log_tool_call("mnemosyne_forget")
async def handle_forget(router: NamespaceRouter, arguments: dict) -> dict:
    """Delete a memory from the specified namespace."""
    namespace = require_namespace(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(namespace)
    result = instance.forget(memory_id=memory_id)

    return {
        "status": result.get("status", "deleted"),
        "memory_id": memory_id,
        "namespace": namespace,
    }


@log_tool_call("mnemosyne_update")
async def handle_update(router: NamespaceRouter, arguments: dict) -> dict:
    """Update memory content or importance in the specified namespace."""
    namespace = require_namespace(arguments)
    memory_id = arguments.get("memory_id")

    if not memory_id:
        raise ValidationError("memory_id is required")

    instance = await router.get_instance(namespace)

    content: Optional[str] = arguments.get("content")
    importance: Optional[float] = arguments.get("importance")
    result = instance.update(memory_id=memory_id, content=content, importance=importance)

    return {
        "status": result.get("status", "updated"),
        "memory_id": memory_id,
        "namespace": namespace,
    }


@log_tool_call("mnemosyne_sleep")
async def handle_sleep(router: NamespaceRouter, arguments: dict) -> dict:
    """Trigger memory consolidation in the specified namespace."""
    namespace = require_namespace(arguments)

    instance = await router.get_instance(namespace)
    result = instance.sleep()

    return {
        **result,
        "namespace": namespace,
    }


@log_tool_call("mnemosyne_stats")
async def handle_stats(router: NamespaceRouter, arguments: dict) -> dict:
    """Return memory statistics for the specified namespace."""
    namespace = require_namespace(arguments)

    instance = await router.get_instance(namespace)
    stats = instance.stats()

    return {
        "stats": stats,
        "namespace": namespace,
    }


@log_tool_call("mnemosyne_list_namespaces")
async def handle_list_namespaces(router: NamespaceRouter, arguments: dict) -> dict:
    """List all active namespaces with their status, descriptions, and memory counts.

    Includes both active instances AND registered namespaces (from registry).
    """
    namespaces: List[dict] = []
    seen: set[str] = set()

    # First: list all active instances
    for ns_name, client in router.instances.items():
        description = router.get_namespace_description(ns_name)

        stats = client.stats()
        memory_count = 0
        if isinstance(stats, dict):
            working = stats.get("working_count") or stats.get("working") or 0
            episodic = stats.get("episodic_count") or stats.get("episodic") or 0
            memory_count = working + episodic

        namespaces.append({
            "name": ns_name,
            "bank": client.namespace,
            "description": description or "",
            "memory_count": memory_count,
            "status": "active",
        })
        seen.add(ns_name)

    # Then: include any registered namespaces that don't have an active instance yet
    for ns_name in router.registry.list_namespaces():
        if ns_name not in seen:
            description = router.get_namespace_description(ns_name)
            namespaces.append({
                "name": ns_name,
                "bank": ns_name,
                "description": description or "",
                "memory_count": 0,
                "status": "registered",
            })

    return {
        "namespaces": namespaces,
    }


@log_tool_call("mnemosyne_register_namespace")
async def handle_register_namespace(router: NamespaceRouter, arguments: dict) -> dict:
    """Register or update a namespace description."""
    name = arguments.get("name")
    description = arguments.get("description")

    if not name:
        raise ValidationError("name is required")

    if not description:
        raise ValidationError("description is required")

    router.register_namespace(name, description)

    return {
        "status": "registered",
        "name": name,
    }
