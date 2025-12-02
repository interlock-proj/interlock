"""Integration tests for MongoDB backends (Saga, Idempotency, Checkpoint) using testcontainers."""

from datetime import datetime

import pytest
import pytest_asyncio
from pydantic import BaseModel
from testcontainers.mongodb import MongoDbContainer
from ulid import ULID

from interlock.application.commands.middleware.idempotency import IdempotencyTrackedCommand
from interlock.application.events.processing.checkpoint import Checkpoint
from interlock.integrations.mongodb import (
    MongoDBCheckpointBackend,
    MongoDBConfig,
    MongoDBConnectionManager,
    MongoDBIdempotencyBackend,
    MongoDBSagaStateStore,
)


# Sample state for saga testing
class CheckoutState(BaseModel):
    """Sample saga state."""

    order_id: str
    status: str
    inventory_reserved: bool = False


# Sample command for idempotency testing
class CreateOrderCommand(IdempotencyTrackedCommand):
    """Sample idempotent command."""

    idempotency_key: str
    customer_id: str
    total: float


# Helper to create command with aggregate_id
def create_order_command(
    idempotency_key: str, customer_id: str, total: float
) -> CreateOrderCommand:
    """Create a CreateOrderCommand with an aggregate_id."""
    return CreateOrderCommand(
        aggregate_id=ULID(),
        idempotency_key=idempotency_key,
        customer_id=customer_id,
        total=total,
    )


@pytest.fixture(scope="module")
def mongodb_container():
    """Start MongoDB container for tests."""
    container = MongoDbContainer("mongo:7")
    with container:
        yield container


@pytest_asyncio.fixture
async def connection_manager(mongodb_container):
    """Create connection manager for MongoDB container."""
    config = MongoDBConfig(uri=mongodb_container.get_connection_url(), database="test_interlock")
    async with MongoDBConnectionManager(config) as manager:
        yield manager


# ==================== Saga State Store Tests ====================


@pytest_asyncio.fixture
async def saga_state_store(connection_manager):
    """Create and initialize saga state store."""
    store = MongoDBSagaStateStore(connection_manager)
    await store.initialize_schema()
    yield store
    # Cleanup
    await connection_manager.database["saga_states"].delete_many({})


@pytest.mark.asyncio
async def test_saga_save_and_load(saga_state_store):
    """Test saving and loading saga state."""
    saga_id = "checkout_saga_123"
    state = CheckoutState(order_id="ORDER-001", status="pending")

    await saga_state_store.save(saga_id, state)
    loaded = await saga_state_store.load(saga_id)

    assert loaded is not None
    assert isinstance(loaded, CheckoutState)
    assert loaded.order_id == "ORDER-001"  # type: ignore[attr-defined]
    assert loaded.status == "pending"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_saga_load_nonexistent(saga_state_store):
    """Test loading non-existent saga returns None."""
    loaded = await saga_state_store.load("nonexistent_saga")
    assert loaded is None


@pytest.mark.asyncio
async def test_saga_update_state(saga_state_store):
    """Test updating saga state."""
    saga_id = "checkout_saga_456"
    state1 = CheckoutState(order_id="ORDER-002", status="pending")

    await saga_state_store.save(saga_id, state1)

    # Update state
    state2 = CheckoutState(order_id="ORDER-002", status="processing", inventory_reserved=True)
    await saga_state_store.save(saga_id, state2)

    loaded = await saga_state_store.load(saga_id)
    assert loaded is not None
    assert loaded.status == "processing"  # type: ignore[attr-defined]
    assert loaded.inventory_reserved is True  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_saga_delete(saga_state_store):
    """Test deleting saga state."""
    saga_id = "checkout_saga_789"
    state = CheckoutState(order_id="ORDER-003", status="completed")

    await saga_state_store.save(saga_id, state)
    await saga_state_store.delete(saga_id)

    loaded = await saga_state_store.load(saga_id)
    assert loaded is None


@pytest.mark.asyncio
async def test_saga_mark_step_complete_new_saga(saga_state_store):
    """Test marking step complete for new saga."""
    saga_id = "checkout_saga_new"
    newly_marked = await saga_state_store.mark_step_complete(saga_id, "reserve_inventory")

    assert newly_marked is True


@pytest.mark.asyncio
async def test_saga_mark_step_complete_idempotent(saga_state_store):
    """Test marking step complete is idempotent."""
    saga_id = "checkout_saga_idem"
    state = CheckoutState(order_id="ORDER-004", status="pending")

    await saga_state_store.save(saga_id, state)

    # First mark
    newly_marked1 = await saga_state_store.mark_step_complete(saga_id, "reserve_inventory")
    assert newly_marked1 is True

    # Second mark (idempotent)
    newly_marked2 = await saga_state_store.mark_step_complete(saga_id, "reserve_inventory")
    assert newly_marked2 is False


@pytest.mark.asyncio
async def test_saga_is_step_complete(saga_state_store):
    """Test checking if step is complete."""
    saga_id = "checkout_saga_check"
    state = CheckoutState(order_id="ORDER-005", status="pending")

    await saga_state_store.save(saga_id, state)

    # Initially not complete
    is_complete = await saga_state_store.is_step_complete(saga_id, "reserve_inventory")
    assert is_complete is False

    # Mark complete
    await saga_state_store.mark_step_complete(saga_id, "reserve_inventory")

    # Now complete
    is_complete = await saga_state_store.is_step_complete(saga_id, "reserve_inventory")
    assert is_complete is True


@pytest.mark.asyncio
async def test_saga_multiple_steps(saga_state_store):
    """Test multiple completed steps."""
    saga_id = "checkout_saga_multi"
    state = CheckoutState(order_id="ORDER-006", status="pending")

    await saga_state_store.save(saga_id, state)

    await saga_state_store.mark_step_complete(saga_id, "reserve_inventory")
    await saga_state_store.mark_step_complete(saga_id, "charge_payment")
    await saga_state_store.mark_step_complete(saga_id, "send_confirmation")

    assert await saga_state_store.is_step_complete(saga_id, "reserve_inventory")
    assert await saga_state_store.is_step_complete(saga_id, "charge_payment")
    assert await saga_state_store.is_step_complete(saga_id, "send_confirmation")
    assert not await saga_state_store.is_step_complete(saga_id, "nonexistent_step")


# ==================== Idempotency Backend Tests ====================


@pytest_asyncio.fixture
async def idempotency_backend(connection_manager):
    """Create and initialize idempotency backend."""
    backend = MongoDBIdempotencyBackend(connection_manager, ttl_seconds=3600)
    await backend.initialize_schema()
    yield backend
    # Cleanup
    await connection_manager.database["idempotency_keys"].delete_many({})


@pytest.mark.asyncio
async def test_idempotency_store_and_check(idempotency_backend):
    """Test storing and checking idempotency keys."""
    command = create_order_command(idempotency_key="order_123", customer_id="CUST-001", total=99.99)

    # Initially not processed
    has_processed = await idempotency_backend.has_processed_command(command)
    assert has_processed is False

    # Store as processed
    await idempotency_backend.store_processed_command(command)

    # Now processed
    has_processed = await idempotency_backend.has_processed_command(command)
    assert has_processed is True


@pytest.mark.asyncio
async def test_idempotency_store_is_idempotent(idempotency_backend):
    """Test storing same command multiple times is idempotent."""
    command = create_order_command(
        idempotency_key="order_456", customer_id="CUST-002", total=150.00
    )

    # Store multiple times (should not error)
    await idempotency_backend.store_processed_command(command)
    await idempotency_backend.store_processed_command(command)
    await idempotency_backend.store_processed_command(command)

    has_processed = await idempotency_backend.has_processed_command(command)
    assert has_processed is True


@pytest.mark.asyncio
async def test_idempotency_different_commands(idempotency_backend):
    """Test different commands are tracked independently."""
    command1 = create_order_command(
        idempotency_key="order_789", customer_id="CUST-003", total=200.00
    )
    command2 = create_order_command(
        idempotency_key="order_999", customer_id="CUST-004", total=300.00
    )

    await idempotency_backend.store_processed_command(command1)

    assert await idempotency_backend.has_processed_command(command1)
    assert not await idempotency_backend.has_processed_command(command2)


# ==================== Checkpoint Backend Tests ====================


@pytest_asyncio.fixture
async def checkpoint_backend(connection_manager):
    """Create and initialize checkpoint backend."""
    backend = MongoDBCheckpointBackend(connection_manager)
    await backend.initialize_schema()
    yield backend
    # Cleanup
    await connection_manager.database["checkpoints"].delete_many({})


@pytest.mark.asyncio
async def test_checkpoint_save_and_load(checkpoint_backend):
    """Test saving and loading checkpoints."""
    checkpoint = Checkpoint(
        processor_name="OrderProjector",
        processed_aggregate_ids={ULID(), ULID()},
        max_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        events_processed=100,
    )

    await checkpoint_backend.save_checkpoint(checkpoint)
    loaded = await checkpoint_backend.load_checkpoint("OrderProjector")

    assert loaded is not None
    assert loaded.processor_name == "OrderProjector"
    assert loaded.processed_aggregate_ids == checkpoint.processed_aggregate_ids
    assert loaded.max_timestamp == checkpoint.max_timestamp
    assert loaded.events_processed == 100


@pytest.mark.asyncio
async def test_checkpoint_load_nonexistent(checkpoint_backend):
    """Test loading non-existent checkpoint returns None."""
    loaded = await checkpoint_backend.load_checkpoint("NonexistentProcessor")
    assert loaded is None


@pytest.mark.asyncio
async def test_checkpoint_update(checkpoint_backend):
    """Test updating checkpoint."""
    agg1 = ULID()
    agg2 = ULID()
    agg3 = ULID()

    # Initial checkpoint
    checkpoint1 = Checkpoint(
        processor_name="UserProjector",
        processed_aggregate_ids={agg1, agg2},
        max_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        events_processed=50,
    )
    await checkpoint_backend.save_checkpoint(checkpoint1)

    # Updated checkpoint
    checkpoint2 = Checkpoint(
        processor_name="UserProjector",
        processed_aggregate_ids={agg1, agg2, agg3},
        max_timestamp=datetime(2025, 1, 1, 13, 0, 0),
        events_processed=75,
    )
    await checkpoint_backend.save_checkpoint(checkpoint2)

    # Load should have latest
    loaded = await checkpoint_backend.load_checkpoint("UserProjector")
    assert loaded is not None
    assert len(loaded.processed_aggregate_ids) == 3
    assert agg3 in loaded.processed_aggregate_ids
    assert loaded.events_processed == 75


@pytest.mark.asyncio
async def test_checkpoint_multiple_processors(checkpoint_backend):
    """Test multiple processors can have independent checkpoints."""
    checkpoint1 = Checkpoint(
        processor_name="Processor1",
        processed_aggregate_ids={ULID()},
        max_timestamp=datetime(2025, 1, 1, 12, 0, 0),
        events_processed=100,
    )
    checkpoint2 = Checkpoint(
        processor_name="Processor2",
        processed_aggregate_ids={ULID(), ULID()},
        max_timestamp=datetime(2025, 1, 2, 12, 0, 0),
        events_processed=200,
    )

    await checkpoint_backend.save_checkpoint(checkpoint1)
    await checkpoint_backend.save_checkpoint(checkpoint2)

    loaded1 = await checkpoint_backend.load_checkpoint("Processor1")
    loaded2 = await checkpoint_backend.load_checkpoint("Processor2")

    assert loaded1 is not None
    assert loaded2 is not None
    assert loaded1.events_processed == 100
    assert loaded2.events_processed == 200
    assert len(loaded1.processed_aggregate_ids) == 1
    assert len(loaded2.processed_aggregate_ids) == 2
