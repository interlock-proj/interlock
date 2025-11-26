import logging
from typing import TypeVar

from ...context import get_context
from ..bus import CommandHandler, CommandMiddleware
from ..command import Command

LOGGER = logging.getLogger(__name__)
T = TypeVar("T", bound=Command)


class LoggingMiddleware(CommandMiddleware[Command]):
    """Middleware that logs command execution with correlation tracking.

    Logs each command received at the specified logging level with the command
    type and correlation/causation IDs for distributed tracing. Command data is
    NOT logged to avoid exposing PII or sensitive information.

    Attributes:
        level: The numeric logging level (e.g., logging.INFO, logging.DEBUG).

    Examples:
        Basic usage:

        >>> app = (ApplicationBuilder()
        ...     .add_middleware(Command, LoggingMiddleware("INFO"))
        ...     .build())

        With correlation tracking:

        >>> app = (ApplicationBuilder()
        ...     .use_correlation_tracking()  # Enables ContextPropagationMiddleware
        ...     .add_middleware(Command, LoggingMiddleware("INFO"))
        ...     .build())
        >>> # Logs will now include correlation_id, causation_id, command_id

    Note:
        For correlation tracking to work, ContextPropagationMiddleware should
        be registered before LoggingMiddleware in the middleware chain.
    """

    def __init__(self, level: str):
        """Initialize the logging middleware.

        Args:
            level: String representation of the log level (e.g., "INFO", "DEBUG").
                   Case-insensitive.
        """
        self.level = getattr(logging, level.upper())

    async def handle(self, command: T, next: CommandHandler) -> None:
        """Log the command type with correlation context and pass to next handler.

        Args:
            command: The command to log and process.
            next: The next handler in the chain.
        """
        # Build log extra with command type and aggregate_id only
        extra = {
            "command_type": type(command).__name__,
            "aggregate_id": str(command.aggregate_id),
        }

        # Add correlation context if available
        ctx = get_context()
        if ctx.correlation_id is not None:
            extra["correlation_id"] = str(ctx.correlation_id)
        if ctx.causation_id is not None:
            extra["causation_id"] = str(ctx.causation_id)
        if ctx.command_id is not None:
            extra["command_id"] = str(ctx.command_id)

        LOGGER.log(self.level, "Received Command", extra=extra)
        await next.handle(command)
