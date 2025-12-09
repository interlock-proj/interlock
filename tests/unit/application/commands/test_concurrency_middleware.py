"""Comprehensive tests for ConcurrencyRetryMiddleware."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from ulid import ULID

from interlock.application.commands.middleware.concurrency import (
    ConcurrencyRetryMiddleware,
)
from interlock.domain import Command
from interlock.domain.exceptions import ConcurrencyError


class SampleCommand(Command):
    """Sample command for middleware tests."""

    pass


@pytest.fixture
def command():
    """Fixture for a test command."""
    return SampleCommand(aggregate_id=ULID())


def test_middleware_validates_max_attempts_positive():
    """Test that max_attempts must be positive."""
    with pytest.raises(ValueError, match="max_attempts must be positive"):
        ConcurrencyRetryMiddleware(max_attempts=0, retry_delay=0.1)

    with pytest.raises(ValueError, match="max_attempts must be positive"):
        ConcurrencyRetryMiddleware(max_attempts=-1, retry_delay=0.1)


def test_middleware_validates_retry_delay_non_negative():
    """Test that retry_delay must be non-negative."""
    with pytest.raises(ValueError, match="retry_delay must be non-negative"):
        ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=-0.1)


def test_middleware_accepts_valid_parameters():
    """Test that valid parameters are accepted."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.1)
    assert middleware.max_attempts == 3
    assert middleware.retry_delay == 0.1


def test_middleware_accepts_zero_delay():
    """Test that zero delay is valid."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=5, retry_delay=0.0)
    assert middleware.retry_delay == 0.0


@pytest.mark.asyncio
async def test_successful_command_no_retry(command):
    """Test that successful commands don't trigger retries."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.1)
    next_handler = AsyncMock()

    await middleware.retry_on_concurrency(command, next_handler)

    # Should only call once (no retries)
    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_single_retry_succeeds(command):
    """Test that command succeeds after one retry."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.01)
    next_handler = AsyncMock(
        side_effect=[ConcurrencyError("Conflict"), None]  # Fail, then succeed
    )

    await middleware.retry_on_concurrency(command, next_handler)

    # Should call twice (initial + 1 retry)
    assert next_handler.await_count == 2


@pytest.mark.asyncio
async def test_multiple_retries_succeed(command):
    """Test that command succeeds after multiple retries."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=5, retry_delay=0.01)
    next_handler = AsyncMock(
        side_effect=[
            ConcurrencyError("Conflict 1"),
            ConcurrencyError("Conflict 2"),
            ConcurrencyError("Conflict 3"),
            None,  # Succeed on 4th attempt
        ]
    )

    await middleware.retry_on_concurrency(command, next_handler)

    # Should call 4 times (initial + 3 retries)
    assert next_handler.await_count == 4


@pytest.mark.asyncio
async def test_max_attempts_exhausted(command):
    """Test that ConcurrencyError is raised when max attempts exhausted."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.01)
    next_handler = AsyncMock(side_effect=ConcurrencyError("Persistent conflict"))

    with pytest.raises(ConcurrencyError, match="Max attempts \\(3\\) reached"):
        await middleware.retry_on_concurrency(command, next_handler)

    # Should call 3 times (all attempts)
    assert next_handler.await_count == 3


@pytest.mark.asyncio
async def test_max_attempts_one_no_retry(command):
    """Test that max_attempts=1 means no retries."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=1, retry_delay=0.1)
    next_handler = AsyncMock(side_effect=ConcurrencyError("Conflict"))

    with pytest.raises(ConcurrencyError, match="Max attempts \\(1\\) reached"):
        await middleware.retry_on_concurrency(command, next_handler)

    # Should only call once (no retries)
    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_non_concurrency_error_passes_through(command):
    """Test that non-ConcurrencyError exceptions are not retried."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.1)
    next_handler = AsyncMock(side_effect=ValueError("Different error"))

    with pytest.raises(ValueError, match="Different error"):
        await middleware.retry_on_concurrency(command, next_handler)

    # Should only call once (no retry for non-ConcurrencyError)
    next_handler.assert_awaited_once_with(command)


@pytest.mark.asyncio
async def test_retry_delay_is_applied(command):
    """Test that retry_delay is actually applied between attempts."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.05)
    next_handler = AsyncMock(side_effect=ConcurrencyError("Conflict"))

    start_time = asyncio.get_event_loop().time()

    with pytest.raises(ConcurrencyError):
        await middleware.retry_on_concurrency(command, next_handler)

    elapsed_time = asyncio.get_event_loop().time() - start_time

    # Should have 2 delays (between 3 attempts)
    # Allow some tolerance for test execution time
    assert elapsed_time >= 0.08  # 2 * 0.05 = 0.1, with some margin


@pytest.mark.asyncio
async def test_no_delay_after_final_attempt(command):
    """Test that no delay happens after the final failed attempt."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=2, retry_delay=0.1)
    next_handler = AsyncMock(side_effect=ConcurrencyError("Conflict"))

    start_time = asyncio.get_event_loop().time()

    with pytest.raises(ConcurrencyError):
        await middleware.retry_on_concurrency(command, next_handler)

    elapsed_time = asyncio.get_event_loop().time() - start_time

    # Should have only 1 delay (between attempt 1 and 2, not after attempt 2)
    # Total time should be close to 0.1s, not 0.2s
    assert elapsed_time < 0.15  # Allow some margin


@pytest.mark.asyncio
async def test_concurrency_error_chaining(command):
    """Test that the final ConcurrencyError has the last error as cause."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=2, retry_delay=0.01)
    original_error = ConcurrencyError("Original conflict")
    next_handler = AsyncMock(side_effect=original_error)

    try:
        await middleware.retry_on_concurrency(command, next_handler)
        pytest.fail("Expected ConcurrencyError")
    except ConcurrencyError as e:
        # Check that the original error is chained
        assert e.__cause__ is original_error


@pytest.mark.asyncio
async def test_middleware_intercept_integration(command):
    """Test that middleware.intercept properly routes to retry handler."""
    middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.01)
    next_handler = AsyncMock(side_effect=[ConcurrencyError("Conflict"), None])

    # Call via intercept (uses @intercepts routing)
    await middleware.intercept(command, next_handler)

    # Should have retried once
    assert next_handler.await_count == 2
