from datetime import datetime, timezone
from typing import Generic, TypeVar

from pydantic import BaseModel, Field
from ulid import ULID

T = TypeVar("T", bound=BaseModel)


def utc_now() -> datetime:
    """Get the current UTC timestamp.

    Returns:
        Current datetime with UTC timezone information

    Note:
        Used as default_factory for Event.timestamp to ensure all
        events are timestamped in UTC regardless of system timezone.
    """
    return datetime.now(tz=timezone.utc)


class Event(BaseModel, Generic[T]):
    """Immutable record of a state change in an aggregate.

    Event is the core data structure in event sourcing. Each event represents
    a fact that occurred in the past - a state transition in an aggregate's
    lifecycle. Events are:

    - **Immutable**: Once created, events cannot be modified
    - **Ordered**: Events have sequence numbers for ordering within an aggregate
    - **Typed**: Generic type parameter T specifies the event data schema
    - **Timestamped**: All events record when they occurred (UTC)
    - **Identifiable**: Each event has a unique ID and belongs to an aggregate
    - **Traceable**: Events can include correlation/causation IDs for distributed tracing

    The Event class is a generic wrapper that combines event metadata (id,
    aggregate_id, sequence_number, timestamp) with strongly-typed event data.

    Type Parameters:
        T: Pydantic BaseModel subclass defining the event data schema

    Attributes:
        id: Unique identifier for this specific event instance
        aggregate_id: ID of the aggregate that produced this event
        data: Typed event data (e.g., AccountCreated, MoneyDeposited)
        sequence_number: Position in the aggregate's event stream (1-indexed)
        timestamp: When the event occurred (UTC timezone)
        correlation_id: Optional correlation ID for tracing the entire logical operation
        causation_id: Optional ID of what caused this event (typically the command_id)

    Note:
        Events are typically created by aggregates via the `emit()` method,
        not constructed directly. The EventBus handles persistence and delivery.
        The Aggregate.emit() method automatically populates correlation_id and
        causation_id from the current execution context.

    Examples:
        Event created by aggregate (context auto-populated):

        >>> # Inside aggregate command handler
        >>> self.emit(AccountCreated(owner="Alice"))
        >>> # correlation_id and causation_id are automatically set from context

        Event created manually with full context:

        >>> event = Event(
        ...     aggregate_id=account_id,
        ...     data=MoneyDeposited(amount=100),
        ...     sequence_number=5,
        ...     correlation_id=correlation_id,
        ...     causation_id=command_id
        ... )
    """

    id: ULID = Field(
        default_factory=ULID,
        description="Unique identifier for this event instance",
    )
    aggregate_id: ULID = Field(description="ID of the aggregate that produced this event")
    data: T = Field(description="Typed event data conforming to schema T")
    sequence_number: int = Field(
        description="Position in aggregate's event stream (1-indexed, monotonically increasing)"
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="When the event occurred (UTC timezone)",
    )
    correlation_id: ULID | None = Field(
        default=None,
        description="Correlation ID for tracing the entire logical operation across services",
    )
    causation_id: ULID | None = Field(
        default=None,
        description="ID of what directly caused this event (typically the command_id)",
    )
