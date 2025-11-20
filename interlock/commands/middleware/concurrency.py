import asyncio
import logging
from typing import TypeVar

from ...aggregates import ConcurrencyError
from ..bus import CommandHandler, CommandMiddleware
from ..command import Command

LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=Command)


class ConcurrencyRetryMiddleware(CommandMiddleware[T]):
    """Middleware that retries commands that fail due to concurrency issues.

    This middleware is used to retry commands that fail due to concurrency issues.
    It will retry the command up to a maximum number of times with a delay between
    retries. If the command still fails after the maximum number of retries, it will
    raise a ConcurrencyError.

    Attributes:
        max_retries: The maximum number of retries to attempt.
        retry_delay: The delay between retries.
    """

    __slots__ = ("max_retries", "retry_delay")

    def __init__(self, max_retries: int, retry_delay: float):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def handle(self, command: T, next: CommandHandler[T]) -> None:
        last_error: ConcurrencyError | None = None
        for attempt in range(self.max_retries):
            try:
                await next.handle(command)
                return
            except ConcurrencyError as e:
                last_error = e
                LOGGER.warning(f"Concurrency error on attempt {attempt + 1}: {e}")
                await asyncio.sleep(self.retry_delay)
        raise ConcurrencyError(f"Max retries ({self.max_retries}) reached") from last_error
