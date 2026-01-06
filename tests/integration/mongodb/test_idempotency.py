"""Integration tests for MongoIdempotencyStorage."""

import pytest
import pytest_asyncio

from interlock.integrations.mongodb import MongoConfiguration, MongoIdempotencyStorage


@pytest_asyncio.fixture
async def idempotency_storage(mongo_config: MongoConfiguration):
    """Create a MongoIdempotencyStorage for testing."""
    return MongoIdempotencyStorage(mongo_config)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_store_and_check_key(idempotency_storage: MongoIdempotencyStorage):
    """Test storing and checking an idempotency key."""
    key = "test-key-1"

    # Key should not exist initially
    assert await idempotency_storage.has_idempotency_key(key) is False

    # Store the key
    await idempotency_storage.store_idempotency_key(key)

    # Key should exist now
    assert await idempotency_storage.has_idempotency_key(key) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_store_key_idempotent(idempotency_storage: MongoIdempotencyStorage):
    """Test that storing the same key twice doesn't raise an error."""
    key = "test-key-2"

    await idempotency_storage.store_idempotency_key(key)
    # Should not raise
    await idempotency_storage.store_idempotency_key(key)

    assert await idempotency_storage.has_idempotency_key(key) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_independent_keys(idempotency_storage: MongoIdempotencyStorage):
    """Test that different keys are independent."""
    key1 = "test-key-3"
    key2 = "test-key-4"

    await idempotency_storage.store_idempotency_key(key1)

    assert await idempotency_storage.has_idempotency_key(key1) is True
    assert await idempotency_storage.has_idempotency_key(key2) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_nonexistent_key(idempotency_storage: MongoIdempotencyStorage):
    """Test checking a key that doesn't exist."""
    assert await idempotency_storage.has_idempotency_key("nonexistent") is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_keys(idempotency_storage: MongoIdempotencyStorage):
    """Test storing and checking multiple keys."""
    keys = ["key-a", "key-b", "key-c", "key-d", "key-e"]

    for key in keys:
        await idempotency_storage.store_idempotency_key(key)

    for key in keys:
        assert await idempotency_storage.has_idempotency_key(key) is True

    assert await idempotency_storage.has_idempotency_key("key-f") is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_key_with_special_characters(idempotency_storage: MongoIdempotencyStorage):
    """Test storing keys with special characters."""
    keys = [
        "command-123-456",
        "user@example.com:action",
        "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "key/with/slashes",
        "key.with.dots",
    ]

    for key in keys:
        await idempotency_storage.store_idempotency_key(key)
        assert await idempotency_storage.has_idempotency_key(key) is True
