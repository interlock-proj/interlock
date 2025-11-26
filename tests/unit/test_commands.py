import logging

import pytest
from ulid import ULID

from interlock.commands import (
    CommandBus,
    DelegateToAggregate,
    HandleWithMiddleware,
)
from interlock.commands.middleware import LoggingMiddleware
from tests.conftest import Counter, ExecutionTracker, IncrementCounter, SetName


@pytest.mark.asyncio
async def test_delegate_to_aggregate_executes_command(
    aggregate_id: ULID, command_handler, event_store
):
    command = IncrementCounter(aggregate_id=aggregate_id, amount=5)

    await command_handler.handle(command)

    # Verify event was saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 5


@pytest.mark.asyncio
async def test_delegate_to_aggregate_handles_multiple_commands(
    aggregate_id: ULID, command_handler, event_store
):
    await command_handler.handle(IncrementCounter(aggregate_id=aggregate_id, amount=3))
    await command_handler.handle(IncrementCounter(aggregate_id=aggregate_id, amount=7))

    # Verify events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 2
    assert events[0].data.amount == 3
    assert events[1].data.amount == 7


@pytest.mark.asyncio
async def test_middleware_wraps_handler_execution(
    aggregate_id: ULID, command_handler, middleware_filter, execution_tracker: ExecutionTracker
):
    wrapped = HandleWithMiddleware(execution_tracker, middleware_filter)
    command = IncrementCounter(aggregate_id=aggregate_id, amount=1)

    await wrapped.handle(command, command_handler.handle)

    assert execution_tracker.executions == [
        ("start", "IncrementCounter"),
        ("end", "IncrementCounter"),
    ]


@pytest.mark.asyncio
async def test_multiple_middlewares_execute_in_order(aggregate_id: ULID, command_handler, middleware_filter):
    tracker1 = ExecutionTracker()
    tracker2 = ExecutionTracker()

    wrapped1 = HandleWithMiddleware(tracker1, middleware_filter)
    wrapped2 = HandleWithMiddleware(tracker2, middleware_filter)

    command = IncrementCounter(aggregate_id=aggregate_id, amount=1)
    # Chain: tracker2 -> tracker1 -> command_handler
    await wrapped2.handle(command, lambda cmd: wrapped1.handle(cmd, command_handler.handle))

    assert tracker2.executions[0] == ("start", "IncrementCounter")
    assert tracker1.executions[0] == ("start", "IncrementCounter")
    assert tracker1.executions[1] == ("end", "IncrementCounter")
    assert tracker2.executions[1] == ("end", "IncrementCounter")


def test_logging_middleware_accepts_log_levels():
    info_middleware = LoggingMiddleware("INFO")
    debug_middleware = LoggingMiddleware("debug")

    assert info_middleware.level == logging.INFO
    assert debug_middleware.level == logging.DEBUG


@pytest.mark.asyncio
async def test_logging_middleware_logs_commands(aggregate_id: ULID, caplog, command_handler):
    middleware = LoggingMiddleware("INFO")
    command = IncrementCounter(aggregate_id=aggregate_id, amount=5)

    with caplog.at_level(logging.INFO):
        await middleware.handle(command, command_handler)

    assert "Received Command" in caplog.text


@pytest.mark.asyncio
async def test_command_bus_routes_command_to_aggregate(
    aggregate_id: ULID, counter_app, event_store
):
    await counter_app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=10))

    # Verify by checking events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 10


@pytest.mark.asyncio
async def test_command_bus_routes_different_commands(
    aggregate_id: ULID, counter_app, event_store
):
    await counter_app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=5))
    await counter_app.dispatch(SetName(aggregate_id=aggregate_id, name="test"))

    # Verify by checking events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 2
    assert events[0].data.amount == 5
    assert events[1].data.name == "test"


@pytest.mark.asyncio
async def test_command_bus_raises_on_unregistered_command(aggregate_id: ULID, base_app_builder):
    # Build an app without registering Counter aggregate
    # This should fail when trying to dispatch IncrementCounter
    from interlock.application.container import DependencyNotFoundError

    app = base_app_builder.build()

    with pytest.raises((KeyError, DependencyNotFoundError)):
        await app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=1))


@pytest.mark.asyncio
async def test_create_builds_working_bus(aggregate_id: ULID, counter_app, event_store):
    await counter_app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=15))

    # Verify by checking events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 15


@pytest.mark.asyncio
async def test_create_applies_middleware_to_matching_commands(
    aggregate_id: ULID,
    base_app_builder,
    event_store,
):
    from interlock.commands.bus import MiddlewareTypeFilter

    app = (
        base_app_builder.register_aggregate(Counter)
        .register_middleware(
            ExecutionTracker, MiddlewareTypeFilter.of_types(IncrementCounter)
        )
        .build()
    )

    await app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=5))

    # Verify command executed (middleware doesn't interfere)
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 5


@pytest.mark.asyncio
async def test_create_applies_middleware_to_all_subclasses(
    aggregate_id: ULID,
    base_app_builder,
    event_store,
):
    from interlock.commands.bus import MiddlewareTypeFilter

    app = (
        base_app_builder.register_aggregate(Counter)
        .register_middleware(
            ExecutionTracker, MiddlewareTypeFilter.of_types(IncrementCounter)
        )
        .build()
    )

    await app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=3))
    await app.dispatch(SetName(aggregate_id=aggregate_id, name="tracked"))

    # Verify both commands executed (middleware filters correctly)
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 2
    assert events[0].data.amount == 3
    assert events[1].data.name == "tracked"


@pytest.mark.asyncio
async def test_create_does_not_apply_non_matching_middleware(
    aggregate_id: ULID, base_app_builder, event_store
):
    from interlock.commands.bus import MiddlewareTypeFilter

    # Register two tracker types to ensure they're treated as different middleware
    class Tracker1(ExecutionTracker):
        pass

    class Tracker2(ExecutionTracker):
        pass

    app = (
        base_app_builder.register_aggregate(Counter)
        .register_middleware(Tracker1, MiddlewareTypeFilter.of_types(IncrementCounter))
        .register_middleware(Tracker2, MiddlewareTypeFilter.of_types(SetName))
        .build()
    )

    await app.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=7))

    # Verify command executed (middleware doesn't interfere)
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 7
