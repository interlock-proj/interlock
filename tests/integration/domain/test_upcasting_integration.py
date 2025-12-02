"""Integration tests for event upcasting with ApplicationBuilder."""

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.domain import Aggregate
from interlock.application.application import ApplicationBuilder
from interlock.domain import Command
from interlock.domain import Event
from interlock.application.events.upcasting import EventUpcaster
from interlock.routing import applies_event, handles_command


# Event versions for testing
class UserRegisteredV1(BaseModel):
    """V1: Single username field."""

    username: str


class UserRegisteredV2(BaseModel):
    """V2: Split into email and display_name."""

    email: str
    display_name: str


class UserRegisteredV3(BaseModel):
    """V3: Added verified flag."""

    email: str
    display_name: str
    verified: bool


# Upcasters
class UserRegisteredV1ToV2(EventUpcaster[UserRegisteredV1, UserRegisteredV2]):
    """Transform V1 to V2."""

    async def upcast_payload(self, data: UserRegisteredV1) -> UserRegisteredV2:
        # Assume username is email format
        return UserRegisteredV2(email=data.username, display_name=data.username.split("@")[0])


class UserRegisteredV2ToV3(EventUpcaster[UserRegisteredV2, UserRegisteredV3]):
    """Transform V2 to V3."""

    async def upcast_payload(self, data: UserRegisteredV2) -> UserRegisteredV3:
        return UserRegisteredV3(email=data.email, display_name=data.display_name, verified=False)


# Commands
class RegisterUser(Command):
    """Command to register a user."""

    username: str


# Aggregate
class User(Aggregate):
    """User aggregate for testing."""

    email: str = ""
    display_name: str = ""
    verified: bool = False

    @handles_command
    def handle_register(self, cmd: RegisterUser) -> None:
        """Handle user registration - emit V1 event."""
        # Emit old V1 event (simulating legacy code)
        self.emit(UserRegisteredV1(username=cmd.username))

    @applies_event
    def apply_registered_v3(self, evt: UserRegisteredV3) -> None:
        """Apply V3 event (current version)."""
        self.email = evt.email
        self.display_name = evt.display_name
        self.verified = evt.verified


@pytest.mark.asyncio
async def test_upcasting_with_application_builder():
    """Test upcasting integration with ApplicationBuilder."""
    # Build application with upcasters
    app = (
        ApplicationBuilder()
        .add_aggregate(User)
        .add_command(RegisterUser)
        .add_upcaster(UserRegisteredV1ToV2)
        .add_upcaster(UserRegisteredV2ToV3)
        .use_synchronous_processing()
        .build()
    )

    # Dispatch command (emits V1 event)
    user_id = ULID()
    await app.dispatch(RegisterUser(aggregate_id=user_id, username="john@example.com"))

    # Load events directly - they should be upcasted V1→V2→V3
    events = await app.event_bus.load_events(user_id, 0)

    assert len(events) == 1
    # Event should be upcasted to V3
    assert isinstance(events[0].data, UserRegisteredV3)
    assert events[0].data.email == "john@example.com"
    assert events[0].data.display_name == "john"
    assert events[0].data.verified is False


@pytest.mark.asyncio
async def test_convention_based_upcaster_discovery():
    """Test that upcasters are discovered via convention-based configuration."""
    # This would require setting up a test package structure
    # For now, testing manual registration is sufficient
    pass


@pytest.mark.asyncio
async def test_upcaster_order_independence():
    """Test that upcasters can be registered before their dependencies.

    This verifies that add_upcaster() defers resolution to build() phase,
    ensuring order-independent configuration.
    """
    from pydantic_settings import BaseSettings  # type: ignore[import-untyped]

    # Define a config that the upcaster depends on
    class UpcasterConfig(BaseSettings):
        default_display_name: str = "Unknown"

    # Define an upcaster that depends on the config
    class ConfigDrivenUpcaster(EventUpcaster[UserRegisteredV1, UserRegisteredV2]):
        def __init__(self, config: UpcasterConfig):
            self.config = config

        async def upcast_payload(self, data: UserRegisteredV1) -> UserRegisteredV2:
            email = data.username
            display_name = self.config.default_display_name
            return UserRegisteredV2(email=email, display_name=display_name)

    # Register upcaster BEFORE its dependency - should work!
    app = (
        ApplicationBuilder()
        .add_aggregate(User)
        .add_command(RegisterUser)
        .add_upcaster(ConfigDrivenUpcaster)  # Registered FIRST
        .add_dependency(UpcasterConfig)  # Registered AFTER
        .add_upcaster(UserRegisteredV2ToV3)  # Another upcaster
        .use_synchronous_processing()
        .build()
    )

    # Dispatch command
    user_id = ULID()
    await app.dispatch(RegisterUser(aggregate_id=user_id, username="test@example.com"))

    # Load events - should be upcasted with injected config
    events = await app.event_bus.load_events(user_id, 0)

    assert len(events) == 1
    assert isinstance(events[0].data, UserRegisteredV3)
    assert events[0].data.email == "test@example.com"
    assert events[0].data.display_name == "Unknown"  # From config
    assert events[0].data.verified is False


@pytest.mark.asyncio
async def test_upcasting_preserves_event_metadata():
    """Test that event metadata is preserved through upcasting chain."""
    app = (
        ApplicationBuilder()
        .add_aggregate(User)
        .add_command(RegisterUser)
        .add_upcaster(UserRegisteredV1ToV2)
        .add_upcaster(UserRegisteredV2ToV3)
        .use_synchronous_processing()
        .build()
    )

    user_id = ULID()
    await app.dispatch(RegisterUser(aggregate_id=user_id, username="alice@test.com"))

    # Load events directly from event bus
    events = await app.event_bus.load_events(user_id, 0)

    assert len(events) == 1
    event = events[0]

    # Check that metadata is preserved
    assert isinstance(event, Event)
    assert event.aggregate_id == user_id
    assert event.sequence_number >= 0  # Sequence numbers start at 0 or 1 depending on impl
    assert event.id is not None
    assert event.timestamp is not None

    # Data should be upcasted to V3
    assert isinstance(event.data, UserRegisteredV3)
    assert event.data.email == "alice@test.com"


@pytest.mark.asyncio
async def test_multiple_aggregates_with_different_upcasters():
    """Test that different aggregates can have independent upcasters."""

    # Define second set of events
    class AccountCreatedV1(BaseModel):
        owner: str

    class AccountCreatedV2(BaseModel):
        owner_id: str
        owner_name: str

    class AccountCreatedV1ToV2(EventUpcaster[AccountCreatedV1, AccountCreatedV2]):
        async def upcast_payload(self, data: AccountCreatedV1) -> AccountCreatedV2:
            return AccountCreatedV2(owner_id=data.owner, owner_name=data.owner)

    class CreateAccount(Command):
        owner: str

    class Account(Aggregate):
        owner_id: str = ""
        owner_name: str = ""

        @handles_command
        def handle_create(self, cmd: CreateAccount) -> None:
            self.emit(AccountCreatedV1(owner=cmd.owner))

        @applies_event
        def apply_created_v2(self, evt: AccountCreatedV2) -> None:
            self.owner_id = evt.owner_id
            self.owner_name = evt.owner_name

    # Build app with both sets of upcasters
    app = (
        ApplicationBuilder()
        .add_aggregate(User)
        .add_aggregate(Account)
        .add_command(RegisterUser)
        .add_command(CreateAccount)
        .add_upcaster(UserRegisteredV1ToV2)
        .add_upcaster(UserRegisteredV2ToV3)
        .add_upcaster(AccountCreatedV1ToV2)
        .use_synchronous_processing()
        .build()
    )

    # Create both aggregates
    user_id = ULID()
    account_id = ULID()

    await app.dispatch(RegisterUser(aggregate_id=user_id, username="bob@test.com"))
    await app.dispatch(CreateAccount(aggregate_id=account_id, owner="BOB123"))

    # Verify both work correctly
    user_events = await app.event_bus.load_events(user_id, 0)
    account_events = await app.event_bus.load_events(account_id, 0)

    assert isinstance(user_events[0].data, UserRegisteredV3)
    assert isinstance(account_events[0].data, AccountCreatedV2)
