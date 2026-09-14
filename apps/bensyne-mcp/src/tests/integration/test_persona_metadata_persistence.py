"""Integration test: verify persona node metadata (conditions/veto) persists across re-ingestion.

This test reproduces the bug where persona.conditions and persona.veto are lost after re-ingestion.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.expand_file_relations_use_case import ExpandFileRelationsUseCase
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.application.services.file_service import FileService
from src.utils.structured_logging import LoggerMock

BANK = "agent-persona_metadata_persistence_test"


@pytest.fixture
def mnemosyne(tmp_path: Path) -> Generator[MnemosyneClient, None, None]:
    client = MnemosyneClient(memory_bank=BANK, data_dir=str(tmp_path / "data"))
    yield client


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / "file_metadata" / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def chunk_repository(manager: FileMetadataConnectionManager) -> FileChunkRepository:
    return FileChunkRepository(manager)


@pytest.fixture
def file_repository(manager: FileMetadataConnectionManager) -> FileRepository:
    return FileRepository(manager)


@pytest.fixture
def relation_repository(manager: FileMetadataConnectionManager) -> FileRelationRepository:
    return FileRelationRepository(manager)


@pytest.fixture
def hash_service(tmp_path: Path) -> HashIndexService:
    return HashIndexService(memory_bank=BANK, db_path=tmp_path / "hash_index.db")


@pytest.fixture
def file_service(
    file_repository: FileRepository,
    chunk_repository: FileChunkRepository,
    relation_repository: FileRelationRepository,
) -> FileService:
    return FileService(
        file_repository=file_repository,
        chunk_repository=chunk_repository,
        relation_repository=relation_repository,
        logger=LoggerMock(),
    )


@pytest.fixture
def remember_use_case(
    mnemosyne: MnemosyneClient,
    hash_service: HashIndexService,
    file_service: FileService,
) -> RememberMemoryUseCase:
    return RememberMemoryUseCase(
        memory_repository=mnemosyne,
        hash_index_service=hash_service,
        file_service=file_service,
        logger=LoggerMock(),
    )


@pytest.fixture
def expand_use_case(
    mnemosyne: MnemosyneClient,
    file_service: FileService,
    relation_repository: FileRelationRepository,
) -> ExpandFileRelationsUseCase:
    return ExpandFileRelationsUseCase(
        mnemosyne_client=mnemosyne,
        file_service=file_service,
        relation_repository=relation_repository,
        logger=LoggerMock(),
    )


def _ingest_persona_node(
    use_case: RememberMemoryUseCase,
    file_path: Path,
    node_id: str,
    title: str,
    conditions: list,
    veto: list,
    decision_next: list,
) -> dict:
    """Ingest a persona decision node with full metadata."""
    import json
    import hashlib

    now = datetime.now().isoformat()
    # Generate a valid SHA-256 hash for the chunk
    content = f"Node {node_id}: {title}\n\nThis is the body of the node."
    chunk_hash = hashlib.sha256(content.encode()).hexdigest()

    return use_case.execute({
        "content": content,
        "source": "test",
        "importance": 0.9,
        "metadata": {
            "chunk_hash": chunk_hash,
            "filePath": str(file_path),
            "sourceType": "agent-persona",
            "extra": {
                "persona.node_id": node_id,
                "persona.title": title,
                "persona.entry": "false",
                "persona.conditions": json.dumps(conditions),
                "persona.veto": json.dumps(veto),
                "persona.created": now,
                "persona.updated": now,
                "persona.status": "active",
            },
            "edges": [
                {
                    "target_file_path": str(Path(file_path).parent / edge),
                    "edge_type": "decision_next",
                    "edge_data": json.dumps(edge),
                }
                for edge in decision_next
            ],
        },
    })


class TestPersonaMetadataPersistence:
    """Verify persona node metadata (conditions/veto) survives re-ingestion."""

    def test_metadata_persists_after_reingestion(
        self,
        remember_use_case: RememberMemoryUseCase,
        expand_use_case: ExpandFileRelationsUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """Re-ingesting the same node should not lose persona.conditions/veto."""
        node_file = tmp_path / "researcher" / "100-test-node.md"
        node_file.parent.mkdir(parents=True)
        node_file.write_text("---\nnode_id: 100-test-node\n---\nTest node body")

        # First ingestion
        result1 = _ingest_persona_node(
            remember_use_case,
            node_file,
            "100-test-node",
            "Test Decision Node",
            ["condition A"],
            ["veto A"],
            ["110-child.md"],
        )
        assert result1.is_ok
        assert result1.value["status"] == "stored"

        # Check the file materialization result
        fm = result1.value.get("file_materialization")
        print(f"File materialization result: {fm}")
        assert fm is not None
        assert fm.get("status") == "ok"
        file_id = fm.get("file_id")

        # Retrieve and verify metadata is present
        expand_result = expand_use_case.execute({"file_id": file_id})
        assert expand_result.is_ok
        source = expand_result.value["source_file"]

        print(f"First retrieval - conditions: {source['metadata'].get('persona.conditions')}")
        print(f"First retrieval - veto: {source['metadata'].get('persona.veto')}")

        assert source["metadata"].get("persona.node_id") == "100-test-node"
        assert source["metadata"].get("persona.conditions") == '["condition A"]'
        assert source["metadata"].get("persona.veto") == '["veto A"]'

        # Re-ingest (same content, same hash) — simulates user re-ingesting all trees
        result2 = _ingest_persona_node(
            remember_use_case,
            node_file,
            "100-test-node",
            "Test Decision Node",
            ["condition A"],
            ["veto A"],
            ["110-child.md"],
        )
        assert result2.is_ok
        assert result2.value["status"] == "deduplicated"

        # Check the file materialization result after re-ingestion
        fm2 = result2.value.get("file_materialization")
        print(f"File materialization result (reingestion): {fm2}")
        assert fm2 is not None
        assert fm2.get("status") == "ok"
        file_id2 = fm2.get("file_id")

        # Retrieve again and verify metadata is STILL present
        expand_result2 = expand_use_case.execute({"file_id": file_id2})
        assert expand_result2.is_ok
        source2 = expand_result2.value["source_file"]

        print(f"After reingestion - conditions: {source2['metadata'].get('persona.conditions')}")
        print(f"After reingestion - veto: {source2['metadata'].get('persona.veto')}")

        assert source2["metadata"].get("persona.node_id") == "100-test-node"
        assert source2["metadata"].get("persona.conditions") == '["condition A"]'
        assert source2["metadata"].get("persona.veto") == '["veto A"]'

    def test_metadata_persists_after_content_change(
        self,
        remember_use_case: RememberMemoryUseCase,
        expand_use_case: ExpandFileRelationsUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """Updating the node body should not lose persona metadata."""
        node_file = tmp_path / "researcher" / "100-updated.md"
        node_file.parent.mkdir(parents=True)
        node_file.write_text("---\nnode_id: 100-updated\n---\nOriginal body")

        result1 = _ingest_persona_node(
            remember_use_case,
            node_file,
            "100-updated",
            "Updated Node",
            ["updated condition"],
            ["updated veto"],
            [],
        )
        assert result1.is_ok

        # Verify metadata
        fm1 = result1.value.get("file_materialization")
        assert fm1 is not None and fm1.get("status") == "ok"
        expand_result1 = expand_use_case.execute({"file_id": fm1.get("file_id")})
        source1 = expand_result1.value["source_file"]
        assert source1["metadata"].get("persona.conditions") == '["updated condition"]'
        assert source1["metadata"].get("persona.veto") == '["updated veto"]'

        # Update content (new hash)
        node_file.write_text("---\nnode_id: 100-updated\n---\nUpdated body")
        result2 = _ingest_persona_node(
            remember_use_case,
            node_file,
            "100-updated",
            "Updated Node",
            ["updated condition"],
            ["updated veto"],
            [],
        )
        assert result2.is_ok

        # Verify metadata survived content change
        fm2 = result2.value.get("file_materialization")
        assert fm2 is not None and fm2.get("status") == "ok"
        expand_result2 = expand_use_case.execute({"file_id": fm2.get("file_id")})
        source2 = expand_result2.value["source_file"]
        assert source2["metadata"].get("persona.conditions") == '["updated condition"]'
        assert source2["metadata"].get("persona.veto") == '["updated veto"]'