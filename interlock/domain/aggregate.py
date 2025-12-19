from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..context import get_context
from ..routing import setup_command_routing, setup_event_applying
from .event import Event

if TYPE_CHECKING:
    from ..routing import MessageRouter


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


T = TypeVar("T", bound=BaseModel)


class Aggregate(BaseModel):
    """Base class for all aggregates in the event sourcing system.

    Aggregates are the core domain objects that maintain consistency boundaries
    and emit domain events when their state changes. Each aggregate has a unique
    identifier and maintains its version through event sequencing.

    The aggregate pattern ensures that all business rules and invariants are
    enforced within a single consistency boundary. State changes are expressed
    as events that are applied to update the aggregate's state.

    Command and event handling is automatically routed based on method decorators.
    Use @handles_command to mark command handler methods and @applies_event to mark
    event applier methods. The framework will automatically route commands and events
    to the appropriate methods based on their type annotations.

    Examples:
        Create a simple bank account aggregate:

        >>> from decimal import Decimal
        >>> from interlock.routing import handles_command, applies_event
        >>>
        >>> class DepositMoney(Command):
        ...     amount: Decimal
        >>>
        >>> class MoneyDeposited(BaseModel):
        ...     amount: Decimal
        >>>
        >>> class BankAccount(Aggregate):
        ...     balance: Decimal = Decimal("0.00")
        ...
        ...     @handles_command
        ...     def handle_deposit(self, cmd: DepositMoney) -> None:
        ...         if cmd.amount <= 0:
        ...             raise ValueError("Amount must be positive")
        ...         self.emit(MoneyDeposited(amount=cmd.amount))
        ...
        ...     @applies_event
        ...     def apply_deposited(self, evt: MoneyDeposited) -> None:
        ...         self.balance += evt.amount
        >>>
        >>> account = BankAccount()
        >>> account.handle(DepositMoney(aggregate_id=account.id, amount=Decimal("100.00")))
        >>> print(account.balance)
        100.00

    Attributes:
        id: Unique identifier for this aggregate instance. Auto-generated if not provided.
        version: Current version number, incremented with each event.
            Used for optimistic concurrency control.
        last_snapshot_time: Timestamp of the last snapshot creation.
            Used for snapshot management.
        last_event_time: Timestamp of the most recent event.
            Used for tracking aggregate activity.
        uncommitted_events: List of events that have been emitted but not yet
            persisted to the event store. This field is excluded from serialization.
    """

    id: UUID = Field(default_factory=uuid4)
    version: int = 0
    last_snapshot_time: datetime = Field(default_factory=utc_now)
    last_event_time: datetime = Field(default_factory=utc_now)
    uncommitted_events: list[Event[Any]] = Field(default_factory=list, exclude=True)

    # Class-level routing tables
    _command_router: ClassVar["MessageRouter"]
    _event_router: ClassVar["MessageRouter"]

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Set up command and event routing when a subclass is defined."""
        super().__init_subclass__(**kwargs)  # type: ignore[arg-type]
        cls._command_router = setup_command_routing(cls)
        cls._event_router = setup_event_applying(cls)

    def handle(self, command: BaseModel) -> object:
        """Route a command to its registered handler method.

        Args:
            command: The command to handle.

        Raises:
            NotImplementedError: If no handler is registered for this command type.
        """
        return self._command_router.route(self, command)

    def apply(self, event: BaseModel) -> object:
        """Route an event to its registered applier method.

        Args:
            event: The event to apply to the aggregate state.
        """
        return self._event_router.route(self, event)

    def emit(self, data: T) -> None:
        """Emit a domain event and apply it to the aggregate state.

        This method should be called by business logic methods when the aggregate's
        state needs to change. It increments the version, creates an event with
        proper metadata, adds it to uncommitted events, and applies the event.

        The emit method automatically populates correlation_id and causation_id from
        the current execution context:
        - correlation_id is inherited from the context (traces the entire operation)
        - causation_id is set to the command_id from context (the command that caused this event)

        Args:
            data: The event data as a Pydantic model representing what happened.

        Examples:
            >>> class AccountOpened(BaseModel):
            ...     owner: str
            >>>
            >>> account = BankAccount()
            >>> account.emit(AccountOpened(owner="Alice"))
            >>> # correlation_id and causation_id are automatically populated from context
        """
        self.version += 1
        current_time = utc_now()

        # Get context for correlation/causation tracking
        ctx = get_context()

        event: Event[T] = Event(
            aggregate_id=self.id,
            sequence_number=self.version,
            data=data,
            timestamp=current_time,
            correlation_id=ctx.correlation_id,
            causation_id=ctx.command_id,  # The command caused this event
        )
        self.last_event_time = current_time
        self.uncommitted_events.append(event)
        self.apply(data)

    def changed_since(self, version: int) -> bool:
        """Check if the aggregate has changed since a specific version.

        Args:
            version: The version number to compare against.

        Returns:
            True if the current version is greater than the provided version,
            False otherwise.

        Examples:
            >>> account = BankAccount()
            >>> account.deposit(Decimal("100"))
            >>> account.changed_since(0)
            True
            >>> account.changed_since(1)
            False
        """
        return self.version > version

    def mark_snapshot(self) -> None:
        """Mark the current time as when a snapshot was taken.

        This method is typically called by the repository after creating
        a snapshot of the aggregate's current state.
        """
        self.last_snapshot_time = utc_now()

    def get_uncommitted_events(self) -> list[Event[Any]]:
        """Get the list of events that haven't been persisted yet.

        Returns:
            List of uncommitted event objects.
        """
        return self.uncommitted_events

    def clear_uncommitted_events(self) -> None:
        """Clear the list of uncommitted events.

        This is typically called after events have been successfully
        persisted to the event store.
        """
        self.uncommitted_events.clear()

    def replay_events(self, events: list[BaseModel]) -> None:
        """Replay a sequence of events to rebuild the aggregate's state.

        This method is called when loading an aggregate from the event store.
        It applies each event in order to reconstruct the current state.

        Args:
            events: List of event data objects to replay.
        """
        for event in events:
            self.apply(event)
