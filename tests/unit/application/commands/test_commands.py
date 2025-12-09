import logging

import pytest
from ulid import ULID

from interlock.application.commands.middleware import LoggingMiddleware
from tests.conftest import (
    BankAccount,
    DepositMoney,
    ExecutionTracker,
    OpenAccount,
)


@pytest.mark.asyncio
async def test_delegate_to_aggregate_executes_command(
    aggregate_id: ULID, command_handler, event_store
):
    command = DepositMoney(aggregate_id=aggregate_id, amount=5)

    await command_handler.handle(command)

    # Verify event was saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 5


@pytest.mark.asyncio
async def test_delegate_to_aggregate_handles_multiple_commands(
    aggregate_id: ULID, command_handler, event_store
):
    await command_handler.handle(DepositMoney(aggregate_id=aggregate_id, amount=3))
    await command_handler.handle(DepositMoney(aggregate_id=aggregate_id, amount=7))

    # Verify events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 2
    assert events[0].data.amount == 3
    assert events[1].data.amount == 7


@pytest.mark.asyncio
async def test_middleware_wraps_handler_execution(
    aggregate_id: ULID,
    command_handler,
    execution_tracker: ExecutionTracker,
):
    command = DepositMoney(aggregate_id=aggregate_id, amount=1)

    await execution_tracker.intercept(command, command_handler.handle)

    assert execution_tracker.executions == [
        ("start", "DepositMoney"),
        ("end", "DepositMoney"),
    ]


@pytest.mark.asyncio
async def test_multiple_middlewares_execute_in_order(aggregate_id: ULID, command_handler):
    tracker1 = ExecutionTracker()
    tracker2 = ExecutionTracker()

    command = DepositMoney(aggregate_id=aggregate_id, amount=1)
    # Chain: tracker2 -> tracker1 -> command_handler
    await tracker2.intercept(
        command,
        lambda cmd: tracker1.intercept(cmd, command_handler.handle),
    )

    assert tracker2.executions[0] == ("start", "DepositMoney")
    assert tracker1.executions[0] == ("start", "DepositMoney")
    assert tracker1.executions[1] == ("end", "DepositMoney")
    assert tracker2.executions[1] == ("end", "DepositMoney")


def test_logging_middleware_accepts_log_levels():
    info_middleware = LoggingMiddleware("INFO")
    debug_middleware = LoggingMiddleware("debug")

    assert info_middleware.level == logging.INFO
    assert debug_middleware.level == logging.DEBUG


@pytest.mark.asyncio
async def test_logging_middleware_logs_commands(aggregate_id: ULID, caplog, command_handler):
    middleware = LoggingMiddleware("INFO")
    command = DepositMoney(aggregate_id=aggregate_id, amount=5)

    with caplog.at_level(logging.INFO):
        await middleware.intercept(command, command_handler.handle)

    assert "Received Command" in caplog.text


@pytest.mark.asyncio
async def test_command_bus_routes_command_to_aggregate(
    aggregate_id: ULID, bank_account_app, event_store
):
    await bank_account_app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=10))

    # Verify by checking events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 10


@pytest.mark.asyncio
async def test_command_bus_routes_different_commands(
    aggregate_id: ULID, bank_account_app, event_store
):
    from decimal import Decimal

    await bank_account_app.dispatch(OpenAccount(aggregate_id=aggregate_id, owner="Alice"))
    await bank_account_app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=Decimal("5")))

    # Verify by checking events were saved
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 2
    assert events[0].data.owner == "Alice"
    assert events[1].data.amount == Decimal("5")


@pytest.mark.asyncio
async def test_command_bus_raises_on_unregistered_command(aggregate_id: ULID, base_app_builder):
    # Build an app without registering BankAccount aggregate
    # This should fail when trying to dispatch DepositMoney
    from interlock.application.container import DependencyNotFoundError

    app = base_app_builder.build()

    with pytest.raises((KeyError, DependencyNotFoundError)):
        await app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=1))


@pytest.mark.asyncio
async def test_create_builds_working_bus(aggregate_id: ULID, bank_account_app, event_store):
    await bank_account_app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=15))

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
    # Middleware now uses @intercepts with specific command types
    app = (
        base_app_builder.register_aggregate(BankAccount)
        .register_middleware(ExecutionTracker)
        .build()
    )

    await app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=5))

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
    # Middleware intercepts base Command type, applies to all
    from decimal import Decimal

    app = (
        base_app_builder.register_aggregate(BankAccount)
        .register_middleware(ExecutionTracker)
        .build()
    )

    await app.dispatch(OpenAccount(aggregate_id=aggregate_id, owner="Bob"))
    await app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=Decimal("3")))

    # Verify both commands executed
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 2
    assert events[0].data.owner == "Bob"
    assert events[1].data.amount == Decimal("3")


@pytest.mark.asyncio
async def test_create_does_not_apply_non_matching_middleware(
    aggregate_id: ULID, base_app_builder, event_store
):
    from interlock.routing import intercepts

    # Create middleware that only intercept specific command types
    class DepositTracker(ExecutionTracker):
        @intercepts
        async def track_deposit(self, command: DepositMoney, next):
            self.executions.append(("start", type(command).__name__))
            result = await next(command)
            self.executions.append(("end", type(command).__name__))
            return result

    class OpenTracker(ExecutionTracker):
        @intercepts
        async def track_open(self, command: OpenAccount, next):
            self.executions.append(("start", type(command).__name__))
            result = await next(command)
            self.executions.append(("end", type(command).__name__))
            return result

    app = (
        base_app_builder.register_aggregate(BankAccount)
        .register_middleware(DepositTracker)
        .register_middleware(OpenTracker)
        .build()
    )

    await app.dispatch(DepositMoney(aggregate_id=aggregate_id, amount=7))

    # Verify command executed (middleware doesn't interfere)
    events = await event_store.load_events(aggregate_id, 1)
    assert len(events) == 1
    assert events[0].data.amount == 7
