import contextvars
from dataclasses import dataclass, replace

from ulid import ULID


@dataclass(frozen=True)
class ExecutionContext:
    """Immutable context for tracking request flow through the system.

    ExecutionContext captures the causal relationship between commands and
    events as they flow through the system, enabling distributed tracing and debugging.

    Attributes:
        correlation_id: Unique ID that traces an entire logical operation across
            all commands, events, and services. Remains constant throughout the flow.
        causation_id: ID of what directly caused this operation. For events, this
            is the command_id that triggered them. For saga commands, this is the
            event ID that triggered them.
        command_id: Unique identifier for the current command being executed.
            When this command emits events, this becomes their causation_id.

    Examples:
        Create a new context at system entry point:

        >>> ctx = ExecutionContext.create()
        >>> print(ctx.correlation_id)  # Auto-generated UUID

        Create context with specific IDs:

        >>> ctx = ExecutionContext(
        ...     correlation_id=uuid4(),
        ...     causation_id=uuid4(),
        ...     command_id=uuid4()
        ... )

        Create a child context for an event:

        >>> event_ctx = ctx.for_event(event_id=uuid4())
        >>> # correlation_id stays the same
        >>> # causation_id becomes the event_id
        >>> # command_id is cleared
    """

    correlation_id: ULID | None = None
    causation_id: ULID | None = None
    command_id: ULID | None = None

    @classmethod
    def create(cls, correlation_id: ULID | None = None) -> "ExecutionContext":
        """Create a new context, typically at a system entry point.

        Args:
            correlation_id: Optional correlation ID. If not provided, a new UUID
                is generated. At entry points, causation_id is set to correlation_id
                (self-referencing).

        Returns:
            A new ExecutionContext instance.

        Example:
            >>> # At HTTP endpoint
            >>> ctx = ExecutionContext.create()
            >>> command = MyCommand(
            ...     aggregate_id=...,
            ...     correlation_id=ctx.correlation_id,
            ...     causation_id=ctx.correlation_id
            ... )
        """
        if correlation_id is None:
            correlation_id = ULID()

        return cls(
            correlation_id=correlation_id,
            causation_id=correlation_id,  # Self-referencing at entry
            command_id=None,
        )

    def for_command(self, command_id: ULID) -> "ExecutionContext":
        """Create a child context for executing a command.

        The correlation_id is inherited. The command_id is set. When the command
        has a causation_id from the original command, that becomes the causation.

        Args:
            command_id: The ID of the command being executed.

        Returns:
            A new ExecutionContext with command_id set.

        Example:
            >>> ctx = get_context()
            >>> cmd_ctx = ctx.for_command(command.command_id)
            >>> set_context(cmd_ctx)
        """
        return replace(self, command_id=command_id)

    def for_event(self, event_id: ULID) -> "ExecutionContext":
        """Create a child context for processing an event.

        The correlation_id is inherited. The causation_id becomes the event_id.
        The command_id is cleared (since we're not in a command context).

        Args:
            event_id: The ID of the event being processed.

        Returns:
            A new ExecutionContext with causation_id set to event_id.

        Example:
            >>> # In event processor
            >>> ctx = get_context()
            >>> event_ctx = ctx.for_event(event.id)
            >>> set_context(event_ctx)
        """
        return replace(self, causation_id=event_id, command_id=None)

    def with_causation(self, causation_id: ULID) -> "ExecutionContext":
        """Create a new context with updated causation_id.

        Args:
            causation_id: The new causation ID.

        Returns:
            A new ExecutionContext with updated causation_id.

        Example:
            >>> ctx = ctx.with_causation(command.command_id)
        """
        return replace(self, causation_id=causation_id)


# Context variable for storing the current execution context
_context: contextvars.ContextVar[ExecutionContext | None] = contextvars.ContextVar(
    "execution_context", default=None
)


def get_context() -> ExecutionContext:
    """Get the current execution context.

    If no context has been set, returns an empty ExecutionContext with all fields None.

    Returns:
        The current ExecutionContext instance.

    Example:
        >>> ctx = get_context()
        >>> if ctx.correlation_id:
        ...     logger.info("Processing request", correlation_id=str(ctx.correlation_id))
    """
    ctx = _context.get()
    if ctx is None:
        return ExecutionContext()
    return ctx


def set_context(context: ExecutionContext) -> None:
    """Set the current execution context.

    Args:
        context: The ExecutionContext to set.

    Example:
        >>> ctx = ExecutionContext.create()
        >>> set_context(ctx)
    """
    _context.set(context)


def clear_context() -> None:
    """Clear the current execution context.

    This is useful for cleanup or testing.

    Example:
        >>> clear_context()
    """
    _context.set(None)


def get_or_create_context() -> ExecutionContext:
    """Get the current context, or create a new one if not set.

    This is useful at system entry points where a new logical operation begins.
    If a context already exists, it is returned. Otherwise, a new context is
    created with a generated correlation_id and set as the current context.

    Returns:
        The current or newly created ExecutionContext.

    Example:
        >>> # At HTTP entry point
        >>> ctx = get_or_create_context()
        >>> command = MyCommand(
        ...     aggregate_id=...,
        ...     correlation_id=ctx.correlation_id,
        ...     causation_id=ctx.causation_id
        ... )
    """
    ctx = _context.get()
    if ctx is None:
        ctx = ExecutionContext.create()
        set_context(ctx)
    return ctx
