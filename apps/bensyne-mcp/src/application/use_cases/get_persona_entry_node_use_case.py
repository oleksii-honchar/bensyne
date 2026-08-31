"""GetPersonaEntryNodeUseCase — persona decision-tree entry node (D2, RC2).

Locates a persona bank's entry node — the file whose ``files.metadata`` carries
``persona.entry == "true"`` — and returns it with its ``file_id`` (the id
``expandFileRelations`` requires, per the RC4 file-tools contract).

The entry node is what an agent loads to begin traversing the decision tree:
it is the root the agent must read first before following ``decision_next``
edges. This gives agents a stable, bank-scoped handle for "where do I start?".

Storage reality (verified end-to-end, Task 6):
  * The persona metadata (incl. ``persona.entry``) is written by racochu's
    ``AgentPersonaChunkingStrategy`` into ``file_metadata.db:files.metadata``.
  * The ``decision_next`` edges live in ``file_metadata.db:file_relations``.
  * The node *content* lives in mnemosyne.db; ``file_chunks.memory_id`` is the
    link. We resolve content via that same link (identical to the
    ``expandFileRelations`` composition path).

Reading the entry flag from mnemosyne.db was a bug — its ``metadata_json`` is
empty for persona nodes. The flag is authoritative in ``files.metadata``.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import structlog.stdlib
from src.application.services.file_service import derive_path_handle
from src.application.use_cases.base_use_case import BaseUseCase
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.result import ErrorWithDetails, Result


def _parse_metadata(metadata: Any) -> Dict[str, Any]:
    """Normalize a file's metadata field to a dict.

    ``File.metadata`` is already a ``dict[str, str]``; this degrades a missing
    or unexpected value to an empty dict so callers read keys without
    try/except everywhere.
    """
    if isinstance(metadata, dict):
        return metadata
    if not metadata:
        return {}
    return {}


def _persona_tags(entry_id: str, metadata: Dict[str, Any]) -> List[str]:
    """Best-effort persona tags: ['persona-node', node_id]."""
    tags: List[str] = ["persona-node"]
    node_id = metadata.get("persona.node_id")
    if node_id:
        tags.append(str(node_id))
    return tags


def _is_entry(metadata: Dict[str, Any]) -> bool:
    """True when the metadata flags this node as a persona entry node."""
    return str(metadata.get("persona.entry", "")).lower() == "true"


class GetPersonaEntryNodeUseCase(BaseUseCase[dict, dict]):
    """Resolves a persona bank's entry node and its file_id (RC4 contract)."""

    def __init__(
        self,
        file_repository: FileRepository,
        file_chunk_repository: FileChunkRepository,
        mnemosyne_client: Callable[[str], dict | None],
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.file_repository = file_repository
        self.file_chunk_repository = file_chunk_repository
        self.mnemosyne_client = mnemosyne_client

    def validate_params(self, parameters: dict) -> Result[dict]:
        """memory_bank is mandatory — missing/empty is a validation error."""
        memory_bank = parameters.get("memory_bank")
        if not memory_bank:
            return Result.ko([ErrorWithDetails("MEMORY_BANK_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Find the entry file, resolve its file_id + content, return the node."""
        files_result = self.file_repository.list_files()
        if not files_result.is_ok:
            return Result.ko(files_result.errors)

        # Locate every file flagged as an entry node.
        entry_candidates: List[tuple[Any, Dict[str, Any]]] = []
        for f in files_result.value:
            meta = _parse_metadata(f.metadata)
            if _is_entry(meta):
                entry_candidates.append((f, meta))

        if not entry_candidates:
            return Result.ko(
                [
                    ErrorWithDetails(
                        "ENTRY_NODE_NOT_FOUND",
                        {"memory_bank": parameters.get("memory_bank")},
                    )
                ]
            )

        # Deterministic selection: smallest persona.node_id, then path.
        entry_candidates.sort(
            key=lambda fm: (str(fm[1].get("persona.node_id", "")), fm[0].path)
        )
        entry_file, meta = entry_candidates[0]
        file_id = entry_file.id
        title = meta.get("persona.title") or ""

        # Resolve content + memory_id via the file's chunks → mnemosyne link.
        memory_id: Optional[str] = None
        text = ""
        chunks_result = self.file_chunk_repository.get_chunks_by_file_id(file_id)
        if chunks_result.is_ok:
            chunks = sorted(
                chunks_result.value or [], key=lambda c: c.chunk_index
            )
            if chunks:
                memory_id = chunks[0].memory_id
                node = self.mnemosyne_client(memory_id) or {}
                text = node.get("content") or ""

        return Result.ok(
            {
                "memory_id": memory_id,
                "file_id": file_id,
                "title": title,
                "text": text,
                "metadata": meta,
                "tags": _persona_tags(file_id, meta),
                "path": entry_file.path,
                "path_handle": derive_path_handle(entry_file),
            }
        )
