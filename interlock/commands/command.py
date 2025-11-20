from pydantic import BaseModel, Field
from ulid import ULID


class Command(BaseModel):
    """Base class for all commands in the system.

    Commands represent intentions to change state and are dispatched to command handlers.
    All commands must include an aggregate_id to identify which aggregate instance to operate on.

    Context tracking (optional):
        correlation_id: Traces the entire logical operation across all commands and events.
            At system entry points, this should be set to a new UUID or extracted from
            incoming requests (e.g., HTTP headers). If not provided, middleware can generate it.
        causation_id: Identifies what directly caused this command. For commands triggered
            by events (sagas), this should be the event ID. For entry-point commands, this
            typically equals correlation_id (self-referencing).
        command_id: Unique identifier for this specific command instance. Auto-generated
            if not provided. When this command emits events, they will use this as their
            causation_id.

    Attributes:
        aggregate_id: ULID of the aggregate that should handle this command.
        correlation_id: Optional correlation ID for distributed tracing.
        causation_id: Optional ID of what caused this command.
        command_id: Unique identifier for this command instance.

    Examples:
        Simple command without context:

        >>> cmd = MyCommand(aggregate_id=ULID())

        Command with full context at HTTP entry point:

        >>> correlation_id = ULID()
        >>> cmd = MyCommand(
        ...     aggregate_id=ULID(),
        ...     correlation_id=correlation_id,
        ...     causation_id=correlation_id  # Self-referencing at entry
        ... )

        Command triggered by an event (saga):

        >>> cmd = MyCommand(
        ...     aggregate_id=ULID(),
        ...     correlation_id=event.correlation_id,  # Inherit from event
        ...     causation_id=event.id  # Event caused this command
        ... )
    """

    aggregate_id: ULID
    correlation_id: ULID | None = None
    causation_id: ULID | None = None
    command_id: ULID = Field(default_factory=ULID)
