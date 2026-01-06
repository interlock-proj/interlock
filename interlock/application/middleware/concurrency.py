"""Concurrency retry middleware for handling optimistic locking conflicts."""

import asyncio
import logging
from typing import Any

from ...domain import Command
from ...domain.exceptions import ConcurrencyError
from ...routing import intercepts
from .base import Handler, Middleware

LOGGER = logging.getLogger(__name__)


class ConcurrencyRetryMiddleware(Middleware):
    """Middleware that retries commands that fail due to concurrency issues.

    This middleware retries commands that fail due to concurrency conflicts.
    It will attempt the command up to `max_attempts` times with a delay
    between attempts. If the command still fails after all attempts, it will
    raise a ConcurrencyError.

    Attributes:
        max_attempts: The maximum number of attempts (initial + retries).
            Must be positive. For example, max_attempts=3 means 1 initial
            attempt + up to 2 retries.
        retry_delay: The delay in seconds between retry attempts.
            Must be non-negative.

    Examples:
        Retry up to 3 times with 0.1s delay:

        >>> middleware = ConcurrencyRetryMiddleware(max_attempts=3, retry_delay=0.1)

        No delay between retries:

        >>> middleware = ConcurrencyRetryMiddleware(max_attempts=5, retry_delay=0.0)
    """

    __slots__ = ("max_attempts", "retry_delay")

    def __init__(self, max_attempts: int, retry_delay: float):
        """Initialize the concurrency retry middleware.

        Args:
            max_attempts: Maximum number of attempts (must be positive).
            retry_delay: Delay in seconds between retries (must be non-negative).

        Raises:
            ValueError: If max_attempts <= 0 or retry_delay < 0.
        """
        if max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if retry_delay < 0:
            raise ValueError("retry_delay must be non-negative")
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay

    @intercepts
    async def retry_on_concurrency(self, command: Command, next: Handler) -> Any:  # type: ignore[type-arg]
        """Intercept all commands and retry on concurrency errors.

        Args:
            command: The command to process.
            next: The next handler in the middleware chain.

        Returns:
            The result from the command handler.

        Raises:
            ConcurrencyError: If all attempts fail due to concurrency conflicts.
            Exception: Any non-ConcurrencyError exceptions are re-raised immediately.
        """
        last_error: ConcurrencyError | None = None
        for attempt in range(self.max_attempts):
            try:
                return await next(command)
            except ConcurrencyError as e:
                last_error = e
                LOGGER.warning(
                    f"Concurrency error on attempt {attempt + 1}/{self.max_attempts}: {e}"
                )
                # Don't sleep after the last attempt
                if attempt < self.max_attempts - 1:
                    await asyncio.sleep(self.retry_delay)
        raise ConcurrencyError(f"Max attempts ({self.max_attempts}) reached") from last_error
