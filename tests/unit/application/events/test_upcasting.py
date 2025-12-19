"""Unit tests for event upcasting infrastructure."""

from uuid import uuid4

import pytest
from pydantic import BaseModel

from interlock.application.events.upcasting import (
    EagerUpcastingStrategy,
    EventUpcaster,
    LazyUpcastingStrategy,
    UpcastingPipeline,
)
from interlock.application.events.upcasting.pipeline import extract_upcaster_types
from interlock.domain import Event


# Test event types (V1, V2, V3 for chain testing)
class AccountCreatedV1(BaseModel):
    """Version 1: Single owner_name field."""

    owner_name: str


class AccountCreatedV2(BaseModel):
    """Version 2: Split into first_name and last_name."""

    first_name: str
    last_name: str


class AccountCreatedV3(BaseModel):
    """Version 3: Added email field."""

    first_name: str
    last_name: str
    email: str


# Upcasters
class AccountCreatedV1ToV2(EventUpcaster[AccountCreatedV1, AccountCreatedV2]):
    """Upcast V1 to V2 by splitting owner_name."""

    async def upcast_payload(self, data: AccountCreatedV1) -> AccountCreatedV2:
        parts = data.owner_name.split(" ", 1)
        return AccountCreatedV2(first_name=parts[0], last_name=parts[1] if len(parts) > 1 else "")


class AccountCreatedV2ToV3(EventUpcaster[AccountCreatedV2, AccountCreatedV3]):
    """Upcast V2 to V3 by adding default email."""

    async def upcast_payload(self, data: AccountCreatedV2) -> AccountCreatedV3:
        email = f"{data.first_name.lower()}.{data.last_name.lower()}@example.com"
        return AccountCreatedV3(first_name=data.first_name, last_name=data.last_name, email=email)


class ConditionalUpcaster(EventUpcaster[AccountCreatedV1, AccountCreatedV2]):
    """Upcaster that only transforms events with specific criteria."""

    async def can_upcast(self, event: Event[AccountCreatedV1]) -> bool:
        # Only upcast if owner_name contains a space
        return " " in event.data.owner_name

    async def upcast_payload(self, data: AccountCreatedV1) -> AccountCreatedV2:
        parts = data.owner_name.split(" ", 1)
        return AccountCreatedV2(first_name=parts[0], last_name=parts[1])


# Test type extraction
class TestExtractUpcasterTypes:
    """Test extracting generic type parameters from upcasters."""

    def test_extract_types_from_simple_upcaster(self):
        """Should extract source and target types from EventUpcaster[T, U]."""
        source, target = extract_upcaster_types(AccountCreatedV1ToV2)
        assert source == AccountCreatedV1
        assert target == AccountCreatedV2

    def test_extract_types_from_chain_upcaster(self):
        """Should extract types from second upcaster in chain."""
        source, target = extract_upcaster_types(AccountCreatedV2ToV3)
        assert source == AccountCreatedV2
        assert target == AccountCreatedV3

    def test_extract_types_from_conditional_upcaster(self):
        """Should extract types even from upcasters with custom logic."""
        source, target = extract_upcaster_types(ConditionalUpcaster)
        assert source == AccountCreatedV1
        assert target == AccountCreatedV2

    def test_extract_types_fails_without_generic_base(self):
        """Should raise ValueError if class doesn't inherit EventUpcaster[T, U]."""

        class NotAnUpcaster:
            pass

        with pytest.raises(ValueError, match="no __orig_bases__ found"):
            extract_upcaster_types(NotAnUpcaster)


# Test EventUpcaster
class TestEventUpcaster:
    """Test the EventUpcaster base class."""

    @pytest.mark.asyncio
    async def test_upcast_event_preserves_metadata(self):
        """Should preserve event metadata when upcasting."""
        event_id = uuid4()
        aggregate_id = uuid4()
        sequence_number = 5
        original_event = Event(
            id=event_id,
            aggregate_id=aggregate_id,
            data=AccountCreatedV1(owner_name="John Doe"),
            sequence_number=sequence_number,
        )

        upcaster = AccountCreatedV1ToV2()
        upcasted = await upcaster.upcast_event(original_event)

        # Metadata preserved
        assert upcasted.id == event_id
        assert upcasted.aggregate_id == aggregate_id
        assert upcasted.sequence_number == sequence_number
        assert upcasted.timestamp == original_event.timestamp

        # Data transformed
        assert upcasted.data.first_name == "John"
        assert upcasted.data.last_name == "Doe"

    @pytest.mark.asyncio
    async def test_upcast_payload_transforms_data(self):
        """Should correctly transform event data."""
        upcaster = AccountCreatedV1ToV2()
        v1_data = AccountCreatedV1(owner_name="Alice Smith")
        v2_data = await upcaster.upcast_payload(v1_data)

        assert v2_data.first_name == "Alice"
        assert v2_data.last_name == "Smith"

    @pytest.mark.asyncio
    async def test_upcast_payload_handles_single_name(self):
        """Should handle single-word names gracefully."""
        upcaster = AccountCreatedV1ToV2()
        v1_data = AccountCreatedV1(owner_name="Madonna")
        v2_data = await upcaster.upcast_payload(v1_data)

        assert v2_data.first_name == "Madonna"
        assert v2_data.last_name == ""

    @pytest.mark.asyncio
    async def test_can_upcast_default_returns_true(self):
        """Default can_upcast should return True."""
        upcaster = AccountCreatedV1ToV2()
        event = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Test User"),
            sequence_number=1,
        )
        assert await upcaster.can_upcast(event) is True

    @pytest.mark.asyncio
    async def test_can_upcast_custom_logic(self):
        """Should support custom can_upcast logic."""
        upcaster = ConditionalUpcaster()

        # Should upcast (has space)
        event_with_space = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="John Doe"),
            sequence_number=1,
        )
        assert await upcaster.can_upcast(event_with_space) is True

        # Should not upcast (no space)
        event_without_space = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Madonna"),
            sequence_number=1,
        )
        assert await upcaster.can_upcast(event_without_space) is False


# Test UpcastingStrategy
class TestUpcastingStrategy:
    """Test upcasting strategies."""

    def test_lazy_strategy_only_upcasts_on_read(self):
        """Lazy strategy should only upcast when reading."""
        strategy = LazyUpcastingStrategy()
        assert strategy.should_upcast_on_read() is True
        assert strategy.should_upcast_on_write() is False

    def test_eager_strategy_upcasts_on_read_and_write(self):
        """Eager strategy should upcast on both read and write."""
        strategy = EagerUpcastingStrategy()
        assert strategy.should_upcast_on_read() is True
        assert strategy.should_upcast_on_write() is True


# Test UpcastingPipeline
class TestUpcastingPipeline:
    """Test the upcasting pipeline."""

    def test_register_upcaster_with_instance(self, upcaster_map):
        """Should register upcaster instance."""
        upcaster = AccountCreatedV1ToV2()
        upcaster_map.register_upcaster(upcaster)
        UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        assert AccountCreatedV1 in upcaster_map.upcasters
        assert upcaster in upcaster_map.upcasters[AccountCreatedV1]

    def test_register_upcaster_with_class(self, upcaster_map):
        """Should instantiate and register upcaster class."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        assert AccountCreatedV1 in upcaster_map.upcasters
        assert len(upcaster_map.upcasters[AccountCreatedV1]) == 1
        assert isinstance(upcaster_map.upcasters[AccountCreatedV1][0], AccountCreatedV1ToV2)

    def test_register_upcaster_with_explicit_types(self, upcaster_map):
        """Should support explicit type registration."""
        upcaster = AccountCreatedV1ToV2()
        upcaster_map.register_upcaster(upcaster)
        UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        assert AccountCreatedV1 in upcaster_map.upcasters

    @pytest.mark.asyncio
    async def test_upcast_single_event(self, upcaster_map):
        """Should upcast a single event."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        event = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Jane Doe"),
            sequence_number=1,
        )

        upcasted = await pipeline.upcast(event)
        assert isinstance(upcasted.data, AccountCreatedV2)
        assert upcasted.data.first_name == "Jane"
        assert upcasted.data.last_name == "Doe"

    @pytest.mark.asyncio
    async def test_upcast_returns_unchanged_if_no_upcaster(self, upcaster_map):
        """Should return event unchanged if no upcaster registered."""
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        event = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="John Doe"),
            sequence_number=1,
        )

        upcasted = await pipeline.upcast(event)
        assert upcasted is event
        assert isinstance(upcasted.data, AccountCreatedV1)

    @pytest.mark.asyncio
    async def test_upcast_chain_v1_to_v3(self, upcaster_map):
        """Should chain multiple upcasters (V1→V2→V3)."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        upcaster_map.register_upcaster(AccountCreatedV2ToV3())
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        event = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Bob Smith"),
            sequence_number=1,
        )

        # Chain upcast through V1→V2→V3
        upcasted = await pipeline.upcast_chain(event)

        assert isinstance(upcasted.data, AccountCreatedV3)
        assert upcasted.data.first_name == "Bob"
        assert upcasted.data.last_name == "Smith"
        assert upcasted.data.email == "bob.smith@example.com"

    @pytest.mark.asyncio
    async def test_upcast_chain_stops_when_no_more_upcasters(self, upcaster_map):
        """Should stop chaining when no more upcasters match."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        # Note: No V2→V3 upcaster registered
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        event = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Alice Jones"),
            sequence_number=1,
        )

        upcasted = await pipeline.upcast_chain(event)
        # Should stop at V2
        assert isinstance(upcasted.data, AccountCreatedV2)
        assert upcasted.data.first_name == "Alice"

    @pytest.mark.asyncio
    async def test_upcast_chain_prevents_infinite_loops(self, upcaster_map):
        """Should prevent infinite loops with max_steps."""

        # Create a truly circular chain: V1→V2→V1→V2...
        class V1ToV2Circular(EventUpcaster[AccountCreatedV1, AccountCreatedV2]):
            async def upcast_payload(self, data: AccountCreatedV1) -> AccountCreatedV2:
                return AccountCreatedV2(first_name=data.owner_name, last_name="")

        class V2ToV1Circular(EventUpcaster[AccountCreatedV2, AccountCreatedV1]):
            async def upcast_payload(self, data: AccountCreatedV2) -> AccountCreatedV1:
                return AccountCreatedV1(owner_name=data.first_name)

        upcaster_map.register_upcaster(V1ToV2Circular())
        upcaster_map.register_upcaster(V2ToV1Circular())
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        event = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Test"),
            sequence_number=1,
        )

        with pytest.raises(RuntimeError, match="exceeded max steps"):
            await pipeline.upcast_chain(event, max_steps=5)

    @pytest.mark.asyncio
    async def test_read_upcast_lazy_strategy(self, upcaster_map):
        """Lazy strategy should upcast on read."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        events = [
            Event(
                aggregate_id=uuid4(),
                data=AccountCreatedV1(owner_name="User One"),
                sequence_number=1,
            ),
            Event(
                aggregate_id=uuid4(),
                data=AccountCreatedV1(owner_name="User Two"),
                sequence_number=2,
            ),
        ]

        upcasted = await pipeline.read_upcast(events)

        assert len(upcasted) == 2
        assert all(isinstance(e.data, AccountCreatedV2) for e in upcasted)

    @pytest.mark.asyncio
    async def test_write_upcast_lazy_strategy(self, upcaster_map):
        """Lazy strategy should NOT upcast on write."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        events = [
            Event(
                aggregate_id=uuid4(),
                data=AccountCreatedV1(owner_name="User One"),
                sequence_number=1,
            )
        ]

        upcasted = await pipeline.write_upcast(events)

        # Should be unchanged (lazy doesn't upcast on write)
        assert upcasted is events
        assert isinstance(upcasted[0].data, AccountCreatedV1)

    @pytest.mark.asyncio
    async def test_write_upcast_eager_strategy(self, upcaster_map):
        """Eager strategy should upcast on write."""
        upcaster_map.register_upcaster(AccountCreatedV1ToV2())
        pipeline = UpcastingPipeline(EagerUpcastingStrategy(), upcaster_map)

        events = [
            Event(
                aggregate_id=uuid4(),
                data=AccountCreatedV1(owner_name="User One"),
                sequence_number=1,
            )
        ]

        upcasted = await pipeline.write_upcast(events)

        assert isinstance(upcasted[0].data, AccountCreatedV2)

    @pytest.mark.asyncio
    async def test_conditional_upcaster_respects_can_upcast(self, upcaster_map):
        """Should respect can_upcast predicate."""
        upcaster_map.register_upcaster(ConditionalUpcaster())
        pipeline = UpcastingPipeline(LazyUpcastingStrategy(), upcaster_map)

        # Event that should be upcasted (has space)
        event_yes = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="John Doe"),
            sequence_number=1,
        )

        # Event that should NOT be upcasted (no space)
        event_no = Event(
            aggregate_id=uuid4(),
            data=AccountCreatedV1(owner_name="Madonna"),
            sequence_number=2,
        )

        upcasted_yes = await pipeline.upcast(event_yes)
        upcasted_no = await pipeline.upcast(event_no)

        # First should be upcasted
        assert isinstance(upcasted_yes.data, AccountCreatedV2)
        assert upcasted_yes.data.first_name == "John"

        # Second should be unchanged
        assert upcasted_no is event_no
        assert isinstance(upcasted_no.data, AccountCreatedV1)
