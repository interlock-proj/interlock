"""Comprehensive tests for IdempotencyMiddleware and storage backends."""

from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from interlock.application.commands.middleware.idempotency import (
    HasIdempotencyKey,
    IdempotencyMiddleware,
    IdempotencyStorageBackend,
    InMemoryIdempotencyStorageBackend,
    NullIdempotencyStorageBackend,
)
from interlock.domain import Command


class SampleTrackedCommand(Command):
    """Sample command with idempotency tracking via field."""

    idempotency_key: str


class ComputedIdempotencyCommand(Command):
    """Sample command with computed idempotency key via property."""

    from_account: ULID
    to_account: ULID
    amount: int

    @property
    def idempotency_key(self) -> str:
        return f"{self.from_account}-{self.to_account}-{self.amount}"


class RegularCommand(Command):
    """Command without idempotency tracking."""

    data: str


@pytest.fixture
def command():
    """Fixture for a tracked command."""
    return SampleTrackedCommand(aggregate_id=ULID(), idempotency_key="test-key-123")


# Factory Method Tests


def test_in_memory_factory_returns_correct_type():
    """Test that IdempotencyStorageBackend.in_memory() returns InMemory backend."""
    backend = IdempotencyStorageBackend.in_memory()
    assert isinstance(backend, InMemoryIdempotencyStorageBackend)


def test_null_factory_returns_correct_type():
    """Test that IdempotencyStorageBackend.null() returns Null backend."""
    backend = IdempotencyStorageBackend.null()
    assert isinstance(backend, NullIdempotencyStorageBackend)


# InMemoryIdempotencyStorageBackend Tests


@pytest.mark.asyncio
async def test_in_memory_backend_stores_and_retrieves(command):
    """Test that in-memory backend stores and retrieves idempotency keys."""
    backend = InMemoryIdempotencyStorageBackend()

    # Initially, key should not be processed
    assert await backend.has_idempotency_key(command.idempotency_key) is False

    # Store the key
    await backend.store_idempotency_key(command.idempotency_key)

    # Now it should be marked as processed
    assert await backend.has_idempotency_key(command.idempotency_key) is True


@pytest.mark.asyncio
async def test_in_memory_backend_different_keys_independent():
    """Test that different idempotency keys are tracked independently."""
    backend = InMemoryIdempotencyStorageBackend()

    await backend.store_idempotency_key("key-1")

    # Only key-1 should be marked as processed
    assert await backend.has_idempotency_key("key-1") is True
    assert await backend.has_idempotency_key("key-2") is False


@pytest.mark.asyncio
async def test_in_memory_backend_same_key_different_command():
    """Test that same idempotency key is recognized regardless of command."""
    backend = InMemoryIdempotencyStorageBackend()

    await backend.store_idempotency_key("same-key")

    # Same key should be detected
    assert await backend.has_idempotency_key("same-key") is True


@pytest.mark.asyncio
async def test_in_memory_backend_multiple_stores_idempotent():
    """Test that storing the same key multiple times is idempotent."""
    backend = InMemoryIdempotencyStorageBackend()

    await backend.store_idempotency_key("test-key")
    await backend.store_idempotency_key("test-key")
    await backend.store_idempotency_key("test-key")

    # Should still only be stored once
    assert await backend.has_idempotency_key("test-key") is True
    assert len(backend.idempotency_keys) == 1


# NullIdempotencyStorageBackend Tests


@pytest.mark.asyncio
async def test_null_backend_always_returns_false(command):
    """Test that null backend always returns False (never processed)."""
    backend = NullIdempotencyStorageBackend()

    # Should return False even after storing
    assert await backend.has_idempotency_key(command.idempotency_key) is False

    await backend.store_idempotency_key(command.idempotency_key)

    assert await backend.has_idempotency_key(command.idempotency_key) is False


@pytest.mark.asyncio
async def test_null_backend_store_is_noop(command):
    """Test that null backend store operation does nothing."""
    backend = NullIdempotencyStorageBackend()

    # Should not raise any errors
    await backend.store_idempotency_key(command.idempotency_key)
    await backend.store_idempotency_key(command.idempotency_key)


# IdempotencyMiddleware Tests


@pytest.mark.asyncio
async def test_middleware_processes_new_command(command):
    """Test that middleware processes commands it hasn't seen before."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    await middleware.ensure_idempotency(command, next_handler)

    # Command should be processed
    next_handler.assert_awaited_once_with(command)

    # And marked as processed
    assert await backend.has_idempotency_key(command.idempotency_key) is True


@pytest.mark.asyncio
async def test_middleware_skips_processed_command(command):
    """Test that middleware skips commands that have been processed."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    # Mark command as already processed
    await backend.store_idempotency_key(command.idempotency_key)

    # Now try to process it again
    await middleware.ensure_idempotency(command, next_handler)

    # Command should NOT be passed to next handler
    next_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_middleware_stores_after_successful_processing(command):
    """Test that middleware stores command only after successful processing."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    # Before processing
    assert await backend.has_idempotency_key(command.idempotency_key) is False

    await middleware.ensure_idempotency(command, next_handler)

    # After processing
    assert await backend.has_idempotency_key(command.idempotency_key) is True


@pytest.mark.asyncio
async def test_middleware_does_not_store_on_failure(command):
    """Test that middleware doesn't store command if processing fails."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock(side_effect=ValueError("Processing failed"))

    with pytest.raises(ValueError, match="Processing failed"):
        await middleware.ensure_idempotency(command, next_handler)

    # Command should NOT be marked as processed
    assert await backend.has_idempotency_key(command.idempotency_key) is False


@pytest.mark.asyncio
async def test_middleware_handles_duplicate_commands():
    """Test that middleware correctly handles duplicate command submissions."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    command1 = SampleTrackedCommand(aggregate_id=ULID(), idempotency_key="duplicate-key")
    command2 = SampleTrackedCommand(
        aggregate_id=ULID(), idempotency_key="duplicate-key"
    )  # Same key

    # Process first command
    await middleware.ensure_idempotency(command1, next_handler)
    assert next_handler.await_count == 1

    # Process second command with same key
    await middleware.ensure_idempotency(command2, next_handler)

    # Should still be 1 (second command was skipped)
    assert next_handler.await_count == 1


@pytest.mark.asyncio
async def test_middleware_with_null_backend_always_processes(command):
    """Test that middleware with null backend always processes commands."""
    backend = NullIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    # Process same command multiple times
    await middleware.ensure_idempotency(command, next_handler)
    await middleware.ensure_idempotency(command, next_handler)
    await middleware.ensure_idempotency(command, next_handler)

    # Should process all 3 times (no idempotency with null backend)
    assert next_handler.await_count == 3


@pytest.mark.asyncio
async def test_middleware_intercept_integration(command):
    """Test that middleware.intercept properly routes to idempotency handler."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    # Call via intercept (uses @intercepts routing)
    await middleware.intercept(command, next_handler)

    # Command should be processed
    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_middleware_with_empty_idempotency_key():
    """Test middleware behavior with empty idempotency key."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    command = SampleTrackedCommand(aggregate_id=ULID(), idempotency_key="")

    # Should still work (empty string is valid)
    await middleware.ensure_idempotency(command, next_handler)
    next_handler.assert_awaited_once_with(command)

    # Second time with empty key should be skipped
    await middleware.ensure_idempotency(command, next_handler)
    assert next_handler.await_count == 1  # Still only 1


@pytest.mark.asyncio
async def test_middleware_different_aggregates_same_key():
    """Test that same idempotency key works across different aggregates."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    agg_id_1 = ULID()
    agg_id_2 = ULID()

    command1 = SampleTrackedCommand(aggregate_id=agg_id_1, idempotency_key="shared-key")
    command2 = SampleTrackedCommand(aggregate_id=agg_id_2, idempotency_key="shared-key")

    # Process first command
    await middleware.ensure_idempotency(command1, next_handler)
    assert next_handler.await_count == 1

    # Process second command (different aggregate, same key)
    await middleware.ensure_idempotency(command2, next_handler)

    # Should be skipped (same idempotency key)
    assert next_handler.await_count == 1


# Property-based idempotency key tests


@pytest.mark.asyncio
async def test_middleware_with_computed_idempotency_key():
    """Test that computed idempotency keys work correctly."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    from_acc = ULID()
    to_acc = ULID()

    command = ComputedIdempotencyCommand(
        aggregate_id=from_acc,
        from_account=from_acc,
        to_account=to_acc,
        amount=100,
    )

    # First process
    await middleware.ensure_idempotency(command, next_handler)
    assert next_handler.await_count == 1

    # Second process with same computed key
    command2 = ComputedIdempotencyCommand(
        aggregate_id=from_acc,
        from_account=from_acc,
        to_account=to_acc,
        amount=100,
    )
    await middleware.ensure_idempotency(command2, next_handler)

    # Should be skipped (same computed key)
    assert next_handler.await_count == 1


@pytest.mark.asyncio
async def test_middleware_different_computed_keys():
    """Test that different computed keys are independent."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    from_acc = ULID()
    to_acc = ULID()

    command1 = ComputedIdempotencyCommand(
        aggregate_id=from_acc,
        from_account=from_acc,
        to_account=to_acc,
        amount=100,
    )

    command2 = ComputedIdempotencyCommand(
        aggregate_id=from_acc,
        from_account=from_acc,
        to_account=to_acc,
        amount=200,  # Different amount = different key
    )

    await middleware.ensure_idempotency(command1, next_handler)
    await middleware.ensure_idempotency(command2, next_handler)

    # Both should be processed (different keys)
    assert next_handler.await_count == 2


# Commands without idempotency key tests


@pytest.mark.asyncio
async def test_middleware_passes_through_regular_commands():
    """Test that commands without idempotency_key pass through unchanged."""
    backend = InMemoryIdempotencyStorageBackend()
    middleware = IdempotencyMiddleware(backend)
    next_handler = AsyncMock()

    command = RegularCommand(aggregate_id=ULID(), data="test")

    # Should pass through without checking idempotency
    await middleware.ensure_idempotency(command, next_handler)
    await middleware.ensure_idempotency(command, next_handler)
    await middleware.ensure_idempotency(command, next_handler)

    # All 3 should be processed
    assert next_handler.await_count == 3


@pytest.mark.asyncio
async def test_protocol_detection():
    """Test that HasIdempotencyKey protocol detection works."""
    tracked = SampleTrackedCommand(aggregate_id=ULID(), idempotency_key="key")
    computed = ComputedIdempotencyCommand(
        aggregate_id=ULID(),
        from_account=ULID(),
        to_account=ULID(),
        amount=100,
    )
    regular = RegularCommand(aggregate_id=ULID(), data="test")

    assert isinstance(tracked, HasIdempotencyKey)
    assert isinstance(computed, HasIdempotencyKey)
    assert not isinstance(regular, HasIdempotencyKey)
