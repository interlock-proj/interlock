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
        .add_dependency(EventStore, InMemoryEventStore)
        .add_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .use_synchronous_processing()
        .build()
    )

    # Check that aggregates were discovered
    assert len(app.command_bus.handlers) > 0


@pytest.mark.asyncio
async def test_convention_based_discovers_commands():
    """Test that commands are discovered and registered."""
    # For this test, we'll manually register just the commands we know have handlers
    # The convention discovery finds commands but they need handlers
    app = (
        ApplicationBuilder()
        .add_dependency(EventStore, InMemoryEventStore)
        .add_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .use_synchronous_processing()
        .build()
    )

    # At least some commands should be registered
    assert len(app.command_bus.handlers) >= 2


@pytest.mark.asyncio
async def test_convention_based_discovers_nested_aggregates():
    """Test that nested packages are discovered recursively."""
    # The nested Order aggregate should have been discovered
    # We can verify this by checking the aggregates set
    from tests.fixtures.test_app.aggregates.nested.order import Order

    builder = ApplicationBuilder().convention_based("tests.fixtures.test_app")
    assert Order in builder.aggregates


@pytest.mark.asyncio
async def test_convention_based_discovers_services():
    """Test that services are discovered and registered."""
    from tests.fixtures.test_app.services.audit_service import (
        AuditService,
        IAuditService,
    )

    app = (
        ApplicationBuilder()
        .add_dependency(EventStore, InMemoryEventStore)
        .add_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .use_synchronous_processing()
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
        .add_dependency(EventStore, InMemoryEventStore)
        .add_dependency(InMemoryEventTransport)
        .convention_based("tests.fixtures.test_app")
        .convention_based("tests.fixtures.test_app")  # Call twice
        .use_synchronous_processing()
        .build()
    )

    # Should still work (last registration wins for duplicates)
    from tests.fixtures.test_app.commands.bank_commands import DepositMoney

    assert DepositMoney in app.command_bus.handlers


@pytest.mark.asyncio
async def test_manual_override_after_convention_based():
    """Test that manual registration overrides convention-based."""
    custom_store = InMemoryEventStore()

    app = (
        ApplicationBuilder()
        .convention_based("tests.fixtures.test_app")
        .add_dependency(EventStore, custom_store)  # Override
        .use_synchronous_processing()
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
        .add_dependency(EventStore, InMemoryEventStore)
        .add_dependency(InMemoryEventTransport)
        .convention_based("tests.unit")  # Has no conventional structure
        .use_synchronous_processing()
        .build()
    )

    # Should build successfully with no discovered components
    assert app is not None
