import asyncio
import logging

from ....domain import Command
from ....domain.exceptions import ConcurrencyError
from ....routing import intercepts
from ..bus import CommandHandler, CommandMiddleware

LOGGER = logging.getLogger(__name__)


class ConcurrencyRetryMiddleware(CommandMiddleware):
    """Middleware that retries commands that fail due to concurrency issues.

    This middleware is used to retry commands that fail due to concurrency
    issues. It will retry the command up to a maximum number of times with a
    delay between retries. If the command still fails after the maximum number
    of retries, it will raise a ConcurrencyError.

    Attributes:
        max_retries: The maximum number of retries to attempt.
        retry_delay: The delay between retries.
    """

    __slots__ = ("max_retries", "retry_delay")

    def __init__(self, max_retries: int, retry_delay: float):
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    @intercepts
    async def retry_on_concurrency(
        self, command: Command, next: CommandHandler
    ) -> None:
        """Intercept all commands and retry on concurrency errors.

        Args:
            command: The command to process.
            next: The next handler in the middleware chain.
        """
        last_error: ConcurrencyError | None = None
        for attempt in range(self.max_retries):
            try:
                await next(command)
                return
            except ConcurrencyError as e:
                last_error = e
                LOGGER.warning(
                    f"Concurrency error on attempt {attempt + 1}: {e}"
                )
                await asyncio.sleep(self.retry_delay)
        raise ConcurrencyError(
            f"Max retries ({self.max_retries}) reached"
        ) from last_error
