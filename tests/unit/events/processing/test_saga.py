"""Tests for Saga infrastructure."""

import pytest
from pydantic import BaseModel

from interlock.events.processing import (
    InMemorySagaStateStore,
    Saga,
    SagaStateStore,
    saga_step,
)
from interlock.routing import handles_event


class CheckoutInitiated(BaseModel):
    saga_id: str
    customer_id: str


class InventoryReserved(BaseModel):
    order_id: str
    items: list[str]


class PaymentCharged(BaseModel):
    order_id: str
    transaction_id: str


class OrderCompleted(BaseModel):
    saga_id: str


class CheckoutState(BaseModel):
    order_id: str
    status: str
    inventory_reserved: bool = False
    payment_charged: bool = False


class CheckoutSaga(Saga[CheckoutState]):
    """Test saga for checkout process."""

    def __init__(self, state_store: SagaStateStore):
        super().__init__(state_store)
        self.dispatched_commands = []

    @handles_event
    @saga_step("initiate_checkout")
    async def on_checkout_initiated(self, event: CheckoutInitiated) -> None:
        state = CheckoutState(order_id=event.saga_id, status="started")
        await self.set_state(event.saga_id, state)
        self.dispatched_commands.append("ReserveInventory")

    @handles_event
    @saga_step("reserve_inventory", saga_id=lambda e: e.order_id)
    async def on_inventory_reserved(self, event: InventoryReserved) -> None:
        state = await self.get_state(event.order_id)
        state.inventory_reserved = True
        state.status = "inventory_reserved"
        await self.set_state(event.order_id, state)
        self.dispatched_commands.append("ChargePayment")

    @handles_event
    @saga_step("charge_payment", saga_id=lambda e: e.order_id)
    async def on_payment_charged(self, event: PaymentCharged) -> None:
        state = await self.get_state(event.order_id)
        state.payment_charged = True
        state.status = "payment_charged"
        await self.set_state(event.order_id, state)
        self.dispatched_commands.append("CompleteOrder")

    @handles_event
    @saga_step("complete_order")
    async def on_order_completed(self, event: OrderCompleted) -> None:
        await self.delete_state(event.saga_id)


@pytest.mark.asyncio
async def test_in_memory_store_save_and_load():
    """Test saving and loading state."""
    store = InMemorySagaStateStore()
    state = CheckoutState(order_id="order-1", status="started")

    await store.save("order-1", state)
    loaded = await store.load("order-1")

    assert loaded is not None
    assert loaded.order_id == "order-1"
    assert loaded.status == "started"


@pytest.mark.asyncio
async def test_in_memory_store_delete():
    """Test deleting state."""
    store = InMemorySagaStateStore()
    state = CheckoutState(order_id="order-1", status="started")

    await store.save("order-1", state)
    await store.delete("order-1")
    loaded = await store.load("order-1")

    assert loaded is None


@pytest.mark.asyncio
async def test_in_memory_store_mark_step_complete():
    """Test marking steps as complete."""
    store = InMemorySagaStateStore()

    was_new = await store.mark_step_complete("order-1", "reserve_inventory")
    assert was_new is True

    was_new = await store.mark_step_complete("order-1", "reserve_inventory")
    assert was_new is False


@pytest.mark.asyncio
async def test_in_memory_store_is_step_complete():
    """Test checking if step is complete."""
    store = InMemorySagaStateStore()

    assert await store.is_step_complete("order-1", "reserve_inventory") is False

    await store.mark_step_complete("order-1", "reserve_inventory")

    assert await store.is_step_complete("order-1", "reserve_inventory") is True


@pytest.mark.asyncio
async def test_saga_state_management():
    """Test saga can save and load state."""
    store = InMemorySagaStateStore()
    saga = CheckoutSaga(store)

    event1 = CheckoutInitiated(saga_id="order-1", customer_id="customer-1")
    await saga.on_checkout_initiated(event1)

    state = await saga.get_state("order-1")
    assert state is not None
    assert state.order_id == "order-1"
    assert state.status == "started"
    assert state.inventory_reserved is False

    event2 = InventoryReserved(order_id="order-1", items=["item-1"])
    await saga.on_inventory_reserved(event2)

    state = await saga.get_state("order-1")
    assert state.inventory_reserved is True
    assert state.status == "inventory_reserved"


@pytest.mark.asyncio
async def test_saga_step_idempotency():
    """Test saga steps are idempotent."""
    store = InMemorySagaStateStore()
    saga = CheckoutSaga(store)

    event = CheckoutInitiated(saga_id="order-1", customer_id="customer-1")

    await saga.on_checkout_initiated(event)
    assert len(saga.dispatched_commands) == 1
    assert saga.dispatched_commands[0] == "ReserveInventory"

    await saga.on_checkout_initiated(event)
    assert len(saga.dispatched_commands) == 1


@pytest.mark.asyncio
async def test_saga_step_with_custom_extractor():
    """Test saga step with custom saga_id extractor."""
    store = InMemorySagaStateStore()
    saga = CheckoutSaga(store)

    event1 = CheckoutInitiated(saga_id="order-1", customer_id="customer-1")
    await saga.on_checkout_initiated(event1)

    event2 = InventoryReserved(order_id="order-1", items=["item-1"])
    await saga.on_inventory_reserved(event2)

    state = await saga.get_state("order-1")
    assert state.inventory_reserved is True

    await saga.on_inventory_reserved(event2)
    assert len([c for c in saga.dispatched_commands if c == "ChargePayment"]) == 1


@pytest.mark.asyncio
async def test_saga_step_missing_saga_id_raises_error():
    """Test saga step raises error if event missing saga_id."""

    class EventWithoutSagaId(BaseModel):
        order_id: str

    class TestSaga(Saga[CheckoutState]):
        def __init__(self, state_store: SagaStateStore):
            super().__init__(state_store)

        @handles_event
        @saga_step("test_step")
        async def on_event(self, event: EventWithoutSagaId) -> None:
            pass

    store = InMemorySagaStateStore()
    saga = TestSaga(store)

    event = EventWithoutSagaId(order_id="order-1")

    with pytest.raises(ValueError, match="must have 'saga_id' field"):
        await saga.on_event(event)


@pytest.mark.asyncio
async def test_saga_delete_state():
    """Test saga can delete state."""
    store = InMemorySagaStateStore()
    saga = CheckoutSaga(store)

    event1 = CheckoutInitiated(saga_id="order-1", customer_id="customer-1")
    await saga.on_checkout_initiated(event1)

    assert await saga.get_state("order-1") is not None

    event2 = OrderCompleted(saga_id="order-1")
    await saga.on_order_completed(event2)

    assert await saga.get_state("order-1") is None


@pytest.mark.asyncio
async def test_saga_full_workflow():
    """Test complete saga workflow."""
    store = InMemorySagaStateStore()
    saga = CheckoutSaga(store)

    event1 = CheckoutInitiated(saga_id="order-1", customer_id="customer-1")
    await saga.on_checkout_initiated(event1)

    state = await saga.get_state("order-1")
    assert state.status == "started"
    assert "ReserveInventory" in saga.dispatched_commands

    event2 = InventoryReserved(order_id="order-1", items=["item-1"])
    await saga.on_inventory_reserved(event2)

    state = await saga.get_state("order-1")
    assert state.status == "inventory_reserved"
    assert state.inventory_reserved is True
    assert "ChargePayment" in saga.dispatched_commands

    event3 = PaymentCharged(order_id="order-1", transaction_id="txn-123")
    await saga.on_payment_charged(event3)

    state = await saga.get_state("order-1")
    assert state.status == "payment_charged"
    assert state.payment_charged is True
    assert "CompleteOrder" in saga.dispatched_commands

    event4 = OrderCompleted(saga_id="order-1")
    await saga.on_order_completed(event4)

    state = await saga.get_state("order-1")
    assert state is None


@pytest.mark.asyncio
async def test_saga_step_exception_handling():
    """Test saga step exception handling."""

    class FailingSaga(Saga[CheckoutState]):
        def __init__(self, state_store: SagaStateStore):
            super().__init__(state_store)

        @handles_event
        @saga_step("failing_step")
        async def on_event(self, event: CheckoutInitiated) -> None:
            raise RuntimeError("Step failed")

    store = InMemorySagaStateStore()
    saga = FailingSaga(store)

    event = CheckoutInitiated(saga_id="order-1", customer_id="customer-1")

    with pytest.raises(RuntimeError, match="Step failed"):
        await saga.on_event(event)

    assert await store.is_step_complete("order-1", "failing_step") is False
