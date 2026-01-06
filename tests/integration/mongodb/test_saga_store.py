"""Integration tests for MongoSagaStateStore."""

import pytest
import pytest_asyncio
from pydantic import BaseModel

from interlock.integrations.mongodb import MongoConfiguration, MongoSagaStateStore


class CheckoutState(BaseModel):
    order_id: str
    status: str
    inventory_reserved: bool = False
    payment_charged: bool = False


@pytest_asyncio.fixture
async def saga_store(mongo_config: MongoConfiguration):
    """Create a MongoSagaStateStore for testing."""
    return MongoSagaStateStore(mongo_config)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_save_and_load_state(saga_store: MongoSagaStateStore):
    """Test saving and loading saga state."""
    state = CheckoutState(order_id="order-1", status="started")

    await saga_store.save("order-1", state)
    loaded = await saga_store.load("order-1")

    assert loaded is not None
    assert loaded.order_id == "order-1"
    assert loaded.status == "started"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_state(saga_store: MongoSagaStateStore):
    """Test updating saga state."""
    state = CheckoutState(order_id="order-2", status="started")
    await saga_store.save("order-2", state)

    # Update state
    state.status = "completed"
    state.inventory_reserved = True
    await saga_store.save("order-2", state)

    loaded = await saga_store.load("order-2")
    assert loaded is not None
    assert loaded.status == "completed"
    assert loaded.inventory_reserved is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_state(saga_store: MongoSagaStateStore):
    """Test deleting saga state."""
    state = CheckoutState(order_id="order-3", status="started")
    await saga_store.save("order-3", state)

    await saga_store.delete("order-3")
    loaded = await saga_store.load("order-3")

    assert loaded is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_load_nonexistent_state(saga_store: MongoSagaStateStore):
    """Test loading state for a saga that doesn't exist."""
    loaded = await saga_store.load("nonexistent")
    assert loaded is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mark_step_complete(saga_store: MongoSagaStateStore):
    """Test marking a step as complete."""
    saga_id = "order-4"

    # First time should return True (newly marked)
    was_new = await saga_store.mark_step_complete(saga_id, "reserve_inventory")
    assert was_new is True

    # Second time should return False (already complete)
    was_new = await saga_store.mark_step_complete(saga_id, "reserve_inventory")
    assert was_new is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_is_step_complete(saga_store: MongoSagaStateStore):
    """Test checking if a step is complete."""
    saga_id = "order-5"

    assert await saga_store.is_step_complete(saga_id, "charge_payment") is False

    await saga_store.mark_step_complete(saga_id, "charge_payment")

    assert await saga_store.is_step_complete(saga_id, "charge_payment") is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_multiple_steps_complete(saga_store: MongoSagaStateStore):
    """Test marking multiple steps as complete."""
    saga_id = "order-6"

    await saga_store.mark_step_complete(saga_id, "step1")
    await saga_store.mark_step_complete(saga_id, "step2")
    await saga_store.mark_step_complete(saga_id, "step3")

    assert await saga_store.is_step_complete(saga_id, "step1") is True
    assert await saga_store.is_step_complete(saga_id, "step2") is True
    assert await saga_store.is_step_complete(saga_id, "step3") is True
    assert await saga_store.is_step_complete(saga_id, "step4") is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_also_removes_completed_steps(saga_store: MongoSagaStateStore):
    """Test that deleting state also removes completed steps."""
    saga_id = "order-7"

    state = CheckoutState(order_id=saga_id, status="started")
    await saga_store.save(saga_id, state)
    await saga_store.mark_step_complete(saga_id, "reserve_inventory")

    assert await saga_store.is_step_complete(saga_id, "reserve_inventory") is True

    await saga_store.delete(saga_id)

    # After delete, step should no longer be marked complete
    assert await saga_store.is_step_complete(saga_id, "reserve_inventory") is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_independent_sagas(saga_store: MongoSagaStateStore):
    """Test that saga states are independent."""
    state1 = CheckoutState(order_id="order-8", status="started")
    state2 = CheckoutState(order_id="order-9", status="completed")

    await saga_store.save("order-8", state1)
    await saga_store.save("order-9", state2)

    await saga_store.mark_step_complete("order-8", "step1")

    loaded1 = await saga_store.load("order-8")
    loaded2 = await saga_store.load("order-9")

    assert loaded1 is not None
    assert loaded1.status == "started"
    assert loaded2 is not None
    assert loaded2.status == "completed"

    assert await saga_store.is_step_complete("order-8", "step1") is True
    assert await saga_store.is_step_complete("order-9", "step1") is False
