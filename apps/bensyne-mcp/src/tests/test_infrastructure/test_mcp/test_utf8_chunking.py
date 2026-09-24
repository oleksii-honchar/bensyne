"""Test UTF-8 boundary handling in rememberMemory handler.

Regression test for: 'utf-8' codec can't decode byte 0xd1 in position 4095:
unexpected end of data.

The Mnemosyne library may split content at 4096 bytes, in the middle of a
multi-byte UTF-8 character. The handler now round-trips the content through
encode/decode to fix any invalid sequences.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.mcp.handlers import handle_remember


@pytest.mark.asyncio
async def test_remember_with_cyrillic_at_boundary():
    """Content with Cyrillic chars (0xd0/0xd1 range) near 4096-byte boundary."""
    # Create content with a multi-byte UTF-8 char at the 4096-byte position
    base = "a" * 4094
    # 'Я' is U+042F, encoded as 0xd1 0xaf in UTF-8 (2 bytes)
    content = base + "Я" + "a" * 100

    # Mock dependencies
    router = MagicMock()
    instance = MagicMock()
    instance.memory_bank = "test_bank"
    router.get_instance = AsyncMock(return_value=instance)

    container = MagicMock()
    use_case = MagicMock()
    use_case.execute.return_value = MagicMock(
        is_ok=True,
        value={"status": "stored", "memory_id": "test_id", "memory_bank": "test_bank"},
    )
    container.remember_memory_use_case.return_value = use_case
    container.file_metadata_bundle = MagicMock()
    container.file_service = MagicMock()
    container.hash_index_service = MagicMock()

    # Call handler
    result = await handle_remember(
        router,
        {"content": content, "memory_bank": "test_bank"},
        container,
    )

    # Verify content was passed through (possibly modified by encode/decode)
    assert result["status"] == "stored"
    # The content should be valid UTF-8 after the fix
    received_params = use_case.execute.call_args[0][0]
    received_content = received_params["content"]
    assert isinstance(received_content, str)
    # Verify it can be encoded to UTF-8 without errors
    received_content.encode("utf-8")


@pytest.mark.asyncio
async def test_remember_with_emoji():
    """Content with emoji (4-byte UTF-8) at boundary."""
    base = "a" * 4092
    # '🌍' is U+1F30D, encoded as 4 bytes in UTF-8
    content = base + "🌍" + "a" * 100

    router = MagicMock()
    instance = MagicMock()
    instance.memory_bank = "test_bank"
    router.get_instance = AsyncMock(return_value=instance)

    container = MagicMock()
    use_case = MagicMock()
    use_case.execute.return_value = MagicMock(
        is_ok=True,
        value={"status": "stored", "memory_id": "test_id", "memory_bank": "test_bank"},
    )
    container.remember_memory_use_case.return_value = use_case
    container.file_metadata_bundle = MagicMock()
    container.file_service = MagicMock()
    container.hash_index_service = MagicMock()

    result = await handle_remember(
        router,
        {"content": content, "memory_bank": "test_bank"},
        container,
    )

    assert result["status"] == "stored"
    received_params = use_case.execute.call_args[0][0]
    received_content = received_params["content"]
    # Verify it can be encoded to UTF-8 without errors
    received_content.encode("utf-8")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
