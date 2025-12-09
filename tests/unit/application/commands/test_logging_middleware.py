"""Comprehensive tests for LoggingMiddleware."""

import logging
from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from interlock.application.commands.middleware.logging import LoggingMiddleware
from interlock.context import ExecutionContext, clear_context, set_context
from interlock.domain import Command


class SampleCommand(Command):
    """Sample command for middleware tests."""

    pass


@pytest.fixture
def command():
    """Fixture for a test command."""
    return SampleCommand(aggregate_id=ULID())


@pytest.fixture(autouse=True)
def clear_execution_context():
    """Clear execution context before and after each test."""
    clear_context()
    yield
    clear_context()


def test_logging_middleware_accepts_info_level():
    """Test that middleware accepts INFO log level."""
    middleware = LoggingMiddleware("INFO")
    assert middleware.level == logging.INFO


def test_logging_middleware_accepts_debug_level():
    """Test that middleware accepts DEBUG log level."""
    middleware = LoggingMiddleware("DEBUG")
    assert middleware.level == logging.DEBUG


def test_logging_middleware_accepts_warning_level():
    """Test that middleware accepts WARNING log level."""
    middleware = LoggingMiddleware("WARNING")
    assert middleware.level == logging.WARNING


def test_logging_middleware_accepts_error_level():
    """Test that middleware accepts ERROR log level."""
    middleware = LoggingMiddleware("ERROR")
    assert middleware.level == logging.ERROR


def test_logging_middleware_case_insensitive():
    """Test that log level is case-insensitive."""
    middleware_upper = LoggingMiddleware("INFO")
    middleware_lower = LoggingMiddleware("info")
    middleware_mixed = LoggingMiddleware("InFo")

    assert middleware_upper.level == logging.INFO
    assert middleware_lower.level == logging.INFO
    assert middleware_mixed.level == logging.INFO


@pytest.mark.asyncio
async def test_logging_middleware_logs_command_without_context(command, caplog):
    """Test logging command without execution context."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    # Verify log message
    assert "Received Command" in caplog.text

    # Verify command metadata in extra
    assert any(
        "SampleCommand" in rec.message or "SampleCommand" in str(rec.__dict__)
        for rec in caplog.records
    )

    # Command should be passed to next handler
    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_logging_middleware_logs_with_full_context(command, caplog):
    """Test logging command with full execution context."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    # Set up full execution context
    correlation_id = ULID()
    causation_id = ULID()
    command_id = ULID()

    ctx = ExecutionContext(
        correlation_id=correlation_id,
        causation_id=causation_id,
        command_id=command_id,
    )
    set_context(ctx)

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    # Verify log message
    assert "Received Command" in caplog.text

    # Verify context IDs are included in log record
    log_record = caplog.records[0]
    assert str(correlation_id) in str(log_record.__dict__)
    assert str(causation_id) in str(log_record.__dict__)
    assert str(command_id) in str(log_record.__dict__)


@pytest.mark.asyncio
async def test_logging_middleware_logs_with_partial_context(command, caplog):
    """Test logging command with partial execution context."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    # Set up partial context (only correlation_id)
    correlation_id = ULID()
    ctx = ExecutionContext(
        correlation_id=correlation_id,
        causation_id=None,
        command_id=None,
    )
    set_context(ctx)

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    # Verify log message
    assert "Received Command" in caplog.text

    # Verify only correlation_id is in log
    log_record = caplog.records[0]
    assert str(correlation_id) in str(log_record.__dict__)


@pytest.mark.asyncio
async def test_logging_middleware_includes_command_type(command, caplog):
    """Test that command type is included in log extra."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    # Verify command type in extra
    log_record = caplog.records[0]
    assert hasattr(log_record, "command_type")
    assert log_record.command_type == "SampleCommand"


@pytest.mark.asyncio
async def test_logging_middleware_includes_aggregate_id(command, caplog):
    """Test that aggregate_id is included in log extra."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    # Verify aggregate_id in extra
    log_record = caplog.records[0]
    assert hasattr(log_record, "aggregate_id")
    assert log_record.aggregate_id == str(command.aggregate_id)


@pytest.mark.asyncio
async def test_logging_middleware_respects_log_level(command, caplog):
    """Test that middleware respects the configured log level."""
    middleware_info = LoggingMiddleware("INFO")
    middleware_debug = LoggingMiddleware("DEBUG")
    next_handler = AsyncMock()

    # Test INFO level - should appear in INFO logs
    with caplog.at_level(logging.INFO):
        await middleware_info.log_command(command, next_handler)
        assert len(caplog.records) == 1
        caplog.clear()

    # Test DEBUG level - should NOT appear in INFO logs
    with caplog.at_level(logging.INFO):
        await middleware_debug.log_command(command, next_handler)
        assert len(caplog.records) == 0


@pytest.mark.asyncio
async def test_logging_middleware_calls_next_handler(command):
    """Test that middleware always calls next handler."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    await middleware.log_command(command, next_handler)

    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_logging_middleware_propagates_exceptions(command):
    """Test that middleware propagates exceptions from next handler."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock(side_effect=ValueError("Handler failed"))

    with pytest.raises(ValueError, match="Handler failed"):
        await middleware.log_command(command, next_handler)


@pytest.mark.asyncio
async def test_logging_middleware_intercept_integration(command, caplog):
    """Test that middleware.intercept properly routes to log handler."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    with caplog.at_level(logging.INFO):
        # Call via intercept (uses @intercepts routing)
        await middleware.intercept(command, next_handler)

    # Should have logged
    assert "Received Command" in caplog.text

    # And called next
    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_logging_middleware_does_not_log_command_data(command, caplog):
    """Test that middleware does not log sensitive command data."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    # Verify that the command data is NOT in the log
    # (only type and metadata should be logged)
    log_text = caplog.text
    assert "aggregate_id" not in log_text or str(command.aggregate_id) not in log_text


@pytest.mark.asyncio
async def test_logging_middleware_multiple_commands_separate_logs(caplog):
    """Test that multiple commands produce separate log entries."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    command1 = SampleCommand(aggregate_id=ULID())
    command2 = SampleCommand(aggregate_id=ULID())

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command1, next_handler)
        await middleware.log_command(command2, next_handler)

    # Should have 2 log records
    assert len(caplog.records) == 2
    assert all("Received Command" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_logging_middleware_with_correlation_id_only(command, caplog):
    """Test logging with only correlation_id in context."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    correlation_id = ULID()
    ctx = ExecutionContext(
        correlation_id=correlation_id,
        causation_id=None,
        command_id=None,
    )
    set_context(ctx)

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    log_record = caplog.records[0]
    assert hasattr(log_record, "correlation_id")
    assert log_record.correlation_id == str(correlation_id)
    # Should not have causation_id or command_id
    assert not hasattr(log_record, "causation_id") or log_record.causation_id is None
    assert not hasattr(log_record, "command_id") or log_record.command_id is None


@pytest.mark.asyncio
async def test_logging_middleware_with_causation_id_only(command, caplog):
    """Test logging with only causation_id in context."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    causation_id = ULID()
    ctx = ExecutionContext(
        correlation_id=None,
        causation_id=causation_id,
        command_id=None,
    )
    set_context(ctx)

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    log_record = caplog.records[0]
    assert hasattr(log_record, "causation_id")
    assert log_record.causation_id == str(causation_id)


@pytest.mark.asyncio
async def test_logging_middleware_with_command_id_only(command, caplog):
    """Test logging with only command_id in context."""
    middleware = LoggingMiddleware("INFO")
    next_handler = AsyncMock()

    command_id = ULID()
    ctx = ExecutionContext(
        correlation_id=None,
        causation_id=None,
        command_id=command_id,
    )
    set_context(ctx)

    with caplog.at_level(logging.INFO):
        await middleware.log_command(command, next_handler)

    log_record = caplog.records[0]
    assert hasattr(log_record, "command_id")
    assert log_record.command_id == str(command_id)
