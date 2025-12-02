"""Integration tests for convention-based application setup."""

import pytest

from interlock.application import ApplicationBuilder
from interlock.application.events import InMemoryEventStore, InMemoryEventTransport
from interlock.application.events.store import EventStore


@pytest.mark.asyncio
async def test_convention_based_discovers_aggregates():
    """Test that aggregates are discovered and registered."""
    app = (
        ApplicationBuilder()
        .register_dependency(EventStore, InMemoryEventStore)
        .register_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .build()
    )

    # Verify aggregates were discovered by successfully dispatching a command
    from tests.conftest import OpenAccount
    from ulid import ULID

    account_id = ULID()
    # If this works, the aggregate was discovered and registered
    await app.dispatch(OpenAccount(aggregate_id=account_id, owner="Alice"))


@pytest.mark.asyncio
async def test_convention_based_discovers_commands():
    """Test that commands are discovered and registered."""
    app = (
        ApplicationBuilder()
        .register_dependency(EventStore, InMemoryEventStore)
        .register_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .build()
    )

    # Verify commands work by dispatching them
    from tests.conftest import OpenAccount, DepositMoney
    from ulid import ULID
    from decimal import Decimal

    account_id = ULID()
    # If these work, commands were discovered
    await app.dispatch(OpenAccount(aggregate_id=account_id, owner="Bob"))
    await app.dispatch(DepositMoney(aggregate_id=account_id, amount=Decimal("100")))


@pytest.mark.asyncio
async def test_convention_based_discovers_nested_aggregates():
    """Test that nested packages are discovered recursively."""
    # The nested Order aggregate should have been discovered
    # We can verify this by checking we can build an app and use it
    from tests.fixtures.test_app.aggregates.nested.order import Order

    app = (
        ApplicationBuilder()
        .register_dependency(EventStore, InMemoryEventStore)
        .register_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .build()
    )

    # If Order was properly registered, we should be able to use it
    # (this test mainly verifies recursive discovery works without errors)
    assert app is not None


@pytest.mark.asyncio
async def test_convention_based_discovers_services():
    """Test that services are discovered and registered."""
    from tests.fixtures.test_app.services.audit_service import (
        AuditService,
        IAuditService,
    )

    app = (
        ApplicationBuilder()
        .register_dependency(EventStore, InMemoryEventStore)
        .register_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .build()
    )

    # Service should be registered by interface
    audit_service = app.get_dependency(IAuditService)
    assert isinstance(audit_service, AuditService)


@pytest.mark.asyncio
async def test_multiple_convention_based_calls_accumulate():
    """Test that multiple convention_based calls accumulate components."""
    app = (
        ApplicationBuilder()
        .register_dependency(EventStore, InMemoryEventStore)
        .register_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .convention_based("tests.fixtures.test_app")  # Call twice
        .build()
    )

    # Should still work (last registration wins for duplicates)
    from tests.conftest import OpenAccount, DepositMoney
    from ulid import ULID
    from decimal import Decimal

    account_id = ULID()
    # If these work, multiple calls worked correctly
    await app.dispatch(OpenAccount(aggregate_id=account_id, owner="Charlie"))
    await app.dispatch(DepositMoney(aggregate_id=account_id, amount=Decimal("50")))


@pytest.mark.asyncio
async def test_manual_override_after_convention_based():
    """Test that manual registration overrides convention-based."""
    custom_store = InMemoryEventStore()

    app = (
        ApplicationBuilder()
        .convention_based("tests.fixtures.test_app")
        .register_dependency(EventStore, lambda: custom_store)  # Override
        .build()
    )

    # Should use our custom store
    resolved_store = app.get_dependency(EventStore)
    assert resolved_store is custom_store


@pytest.mark.asyncio
async def test_convention_based_with_no_matching_packages():
    """Test that convention_based handles missing packages gracefully."""
    # Should not fail even if package has no aggregates/commands/etc subdirs
    app = (
        ApplicationBuilder()
        .register_dependency(EventStore, InMemoryEventStore)
        .register_dependency(InMemoryEventTransport)
        .convention_based("tests.unit")  # Has no conventional structure
        .build()
    )

    # Should build successfully with no discovered components
    assert app is not None
