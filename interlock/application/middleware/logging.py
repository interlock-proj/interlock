"""Logging middleware for command and query tracing."""

import logging
from typing import Any

from ...context import get_context
from ...domain import Command
from ...routing import intercepts
from .base import Handler, Middleware

LOGGER = logging.getLogger(__name__)


class LoggingMiddleware(Middleware):
    """Middleware that logs command execution with correlation.

    Logs each command received at the specified logging level with the
    command type and correlation/causation IDs for distributed tracing.
    Command data is NOT logged to avoid exposing PII or sensitive
    information.

    Attributes:
        level: The numeric logging level (e.g., logging.INFO,
            logging.DEBUG).

    Examples:
        Basic usage:

        >>> app = (ApplicationBuilder()
        ...     .register_middleware(LoggingMiddleware)
        ...     .build())

        With correlation tracking:

        >>> app = (ApplicationBuilder()
        ...     .use_correlation_tracking()
        ...     .register_middleware(LoggingMiddleware)
        ...     .build())

    Note:
        For correlation tracking to work, ContextPropagationMiddleware
        should be registered before LoggingMiddleware in the
        middleware chain.
    """

    def __init__(self, level: str):
        """Initialize the logging middleware.

        Args:
            level: String representation of the log level (e.g.,
                "INFO", "DEBUG"). Case-insensitive.
        """
        self.level = getattr(logging, level.upper())

    @intercepts
    async def log_command(self, command: Command, next: Handler) -> Any:
        """Log the command type with correlation context.

        Args:
            command: The command to log and process.
            next: The next handler in the chain.

        Returns:
            The result from the command handler.
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
        return await next(command)

