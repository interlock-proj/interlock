"""Context propagation middleware for correlation and causation tracking.

This middleware automatically manages execution context for commands, enabling
distributed tracing across the entire system. It extracts context from commands
and sets up the execution context before command execution.
"""

from typing import Any
from uuid import uuid4

from ...context import ExecutionContext, clear_context, set_context
from ...domain import Command
from ...routing import intercepts
from .base import Handler, Middleware


class ContextPropagationMiddleware(Middleware):
    """Middleware that propagates execution context from commands.

    This middleware extracts correlation_id, causation_id, and command_id from
    incoming commands and sets up the execution context before the command is
    handled. This enables:

    1. **Distributed Tracing**: Track entire operations across
       services
    2. **Causation Tracking**: Understand what caused each
       command/event
    3. **Automatic Context Flow**: Events emitted by aggregates
       automatically inherit the context set by this middleware

    **Context Setup**:
    - If command has correlation_id: use it
    - If command has no correlation_id: generate a new one
      (entry point)
    - If command has causation_id: use it
    - If command has no causation_id: use correlation_id
      (self-referencing entry point)
    - Always use command.command_id for tracking

    **Context Cleanup**:
    The middleware ensures the context is cleared after command
    execution (even if the command fails) to prevent context leakage
    between operations.

    **Middleware Order**:
    This middleware should typically run early in the middleware
    chain, before logging or other cross-cutting concerns that might
    need access to context.

    Examples:
        Add to all commands:

        >>> app = (ApplicationBuilder()
        ...     .register_middleware(ContextPropagationMiddleware)
        ...     .build())

        Add with other middleware:

        >>> app = (ApplicationBuilder()
        ...     .register_middleware(ContextPropagationMiddleware)
        ...     .register_middleware(LoggingMiddleware)
        ...     .build())

    Note:
        This middleware is automatically registered when using
        ApplicationBuilder.use_correlation_tracking().
    """

    @intercepts
    async def propagate_context(self, command: Command, next: Handler) -> Any:
        """Set up execution context and pass command to next handler.

        The context is cleared after command execution (even on
        failure) to prevent context leakage.

        Args:
            command: The command to process. Context is extracted from
                its correlation_id, causation_id, and command_id
                fields.
            next: The next handler in the middleware chain.

        Returns:
            The result from the command handler.
        """
        # Extract context from command, generate defaults for missing values
        correlation_id = command.correlation_id
        if correlation_id is None:
            # Entry point: generate new correlation_id
            correlation_id = uuid4()

        causation_id = command.causation_id
        if causation_id is None:
            # Entry point: self-referencing causation
            causation_id = correlation_id

        # Create and set execution context
        ctx = ExecutionContext(
            correlation_id=correlation_id,
            causation_id=causation_id,
            command_id=command.command_id,
        )
        set_context(ctx)

        try:
            # Pass to next handler with context set
            return await next(command)
        finally:
            # Always clear context after command execution to prevent leakage
            clear_context()

