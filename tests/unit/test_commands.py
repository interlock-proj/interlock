import logging

import pytest
from ulid import ULID

from ouroboros.commands import (
    CommandBus,
    DelegateToAggregate,
    HandleWithMiddleware,
)
from ouroboros.commands.middleware import LoggingMiddleware
from tests.conftest import Counter, ExecutionTracker, IncrementCounter, SetName


@pytest.mark.asyncio
async def test_delegate_to_aggregate_executes_command(
    aggregate_id: ULID, counter_repository, counter: Counter
):
    handler = DelegateToAggregate(counter_repository)
    command = IncrementCounter(aggregate_id=aggregate_id, amount=5)

    await handler.handle(command)

    assert counter.count == 5


@pytest.mark.asyncio
async def test_delegate_to_aggregate_handles_multiple_commands(
    aggregate_id: ULID, counter_repository, counter: Counter
):
    handler = DelegateToAggregate(counter_repository)

    await handler.handle(IncrementCounter(aggregate_id=aggregate_id, amount=3))
    await handler.handle(IncrementCounter(aggregate_id=aggregate_id, amount=7))

    assert counter.count == 10


@pytest.mark.asyncio
async def test_middleware_wraps_handler_execution(
    aggregate_id: ULID, counter_repository, execution_tracker: ExecutionTracker
):
    handler = DelegateToAggregate(counter_repository)
    wrapped = HandleWithMiddleware(handler, execution_tracker)
    command = IncrementCounter(aggregate_id=aggregate_id, amount=1)

    await wrapped.handle(command)

    assert execution_tracker.executions == [
        ("start", "IncrementCounter"),
        ("end", "IncrementCounter"),
    ]


@pytest.mark.asyncio
async def test_multiple_middlewares_execute_in_order(aggregate_id: ULID, counter_repository):
    tracker1 = ExecutionTracker()
    tracker2 = ExecutionTracker()

    handler = DelegateToAggregate(counter_repository)
    wrapped = HandleWithMiddleware(handler, tracker1)
    wrapped = HandleWithMiddleware(wrapped, tracker2)

    command = IncrementCounter(aggregate_id=aggregate_id, amount=1)
    await wrapped.handle(command)

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
async def test_logging_middleware_logs_commands(aggregate_id: ULID, caplog, counter_repository):
    middleware = LoggingMiddleware("INFO")
    command = IncrementCounter(aggregate_id=aggregate_id, amount=5)
    handler = DelegateToAggregate(counter_repository)

    with caplog.at_level(logging.INFO):
        await middleware.handle(command, handler)

    assert "Received Command" in caplog.text


@pytest.mark.asyncio
async def test_command_bus_routes_command_to_aggregate(
    aggregate_id: ULID, counter_repository, counter: Counter
):
    handler = DelegateToAggregate(counter_repository)
    bus = CommandBus({IncrementCounter: handler})

    await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=10))

    assert counter.count == 10


@pytest.mark.asyncio
async def test_command_bus_routes_different_commands(
    aggregate_id: ULID, counter_repository, counter: Counter
):
    handler = DelegateToAggregate(counter_repository)
    bus = CommandBus({IncrementCounter: handler, SetName: handler})

    await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=5))
    await bus.dispatch(SetName(aggregate_id=aggregate_id, name="test"))

    assert counter.count == 5
    assert counter.name == "test"


@pytest.mark.asyncio
async def test_command_bus_raises_on_unregistered_command(aggregate_id: ULID):
    bus = CommandBus({})

    with pytest.raises(KeyError):
        await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=1))


@pytest.mark.asyncio
async def test_create_builds_working_bus(aggregate_id: ULID, counter_repository, counter: Counter):
    repositories = {IncrementCounter: counter_repository}
    bus = CommandBus.create(repositories, [])

    await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=15))

    assert counter.count == 15


@pytest.mark.asyncio
async def test_create_applies_middleware_to_matching_commands(
    aggregate_id: ULID,
    counter_repository,
    counter: Counter,
    execution_tracker: ExecutionTracker,
):
    repositories = {IncrementCounter: counter_repository}
    middlewares = [(execution_tracker, IncrementCounter)]
    bus = CommandBus.create(repositories, middlewares)

    await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=5))

    assert counter.count == 5
    assert len(execution_tracker.executions) == 2


@pytest.mark.asyncio
async def test_create_applies_middleware_to_all_subclasses(
    aggregate_id: ULID,
    counter_repository,
    counter: Counter,
    execution_tracker: ExecutionTracker,
):
    repositories = {IncrementCounter: counter_repository, SetName: counter_repository}
    middlewares = [(execution_tracker, IncrementCounter)]
    bus = CommandBus.create(repositories, middlewares)

    await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=3))
    await bus.dispatch(SetName(aggregate_id=aggregate_id, name="tracked"))

    assert counter.count == 3
    assert counter.name == "tracked"
    assert len(execution_tracker.executions) == 2


@pytest.mark.asyncio
async def test_create_does_not_apply_non_matching_middleware(
    aggregate_id: ULID, counter_repository, counter: Counter
):
    tracker1 = ExecutionTracker()
    tracker2 = ExecutionTracker()

    repositories = {IncrementCounter: counter_repository, SetName: counter_repository}
    middlewares = [(tracker1, IncrementCounter), (tracker2, SetName)]
    bus = CommandBus.create(repositories, middlewares)

    await bus.dispatch(IncrementCounter(aggregate_id=aggregate_id, amount=7))

    assert counter.count == 7
    assert len(tracker1.executions) == 2
    assert len(tracker2.executions) == 0
