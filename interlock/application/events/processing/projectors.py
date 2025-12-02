"""Aggregate projectors for snapshot-based catchup strategies."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

if TYPE_CHECKING:
    from ....domain import Aggregate
    from .processor import EventProcessor

A = TypeVar("A", bound="Aggregate")
P = TypeVar("P", bound="EventProcessor")


class AggregateProjector(ABC, Generic[A, P]):
    """Projects aggregate state into event processor during snapshot-based catchup.

    AggregateProjector is used by FromAggregateSnapshot to initialize processor
    state from fully-hydrated aggregates. This allows processors to "catch up"
    by loading aggregate snapshots rather than replaying all historical events.

    The projector is responsible for translating aggregate domain state into
    the processor's read model representation.

    Type Parameters:
        A: Aggregate type (e.g., User, Order, BankAccount)
        P: Processor type (e.g., UserProfileProcessor, OrderSummaryProcessor)

    This generic design provides:
    - Full type safety - IDE autocomplete for aggregate and processor
    - DI support - projectors can have dependencies injected
    - Testability - projectors can be tested in isolation

    Example:
        >>> class User(Aggregate):
        ...     name: str
        ...     email: str
        ...     created_at: datetime
        >>>
        >>> class UserProfileProcessor(EventProcessor):
        ...     profiles: dict[UUID, dict] = {}
        >>>
        >>> class UserProfileProjector(AggregateProjector[User, UserProfileProcessor]):
        ...     async def project(self, user: User, processor: UserProfileProcessor) -> None:
        ...         # IDE knows user is User, processor is UserProfileProcessor
        ...         processor.profiles[user.id] = {
        ...             "name": user.name,
        ...             "email": user.email,
        ...             "member_since": user.created_at
        ...         }

        Usage with catchup strategy:
        >>> projector = UserProfileProjector()
        >>> strategy = FromAggregateSnapshot(
        ...     repository=user_repository,
        ...     projector=projector,
        ...     checkpoint_backend=checkpoint_backend
        ... )

    See Also:
        - FromAggregateSnapshot: The catchup strategy that uses projectors
        - EventProcessor: Base class for read model processors
        - AggregateRepository: Provides fully-hydrated aggregates
    """

    @abstractmethod
    async def project(self, aggregate: A, processor: P) -> None:
        """Project aggregate state into the processor.

        This method is called once per aggregate during catchup. The aggregate
        is fully hydrated (snapshot + events), representing its current state.

        Implementations should update the processor's internal state to reflect
        the aggregate's state. This typically involves:
        - Populating read model data structures (dicts, sets, etc.)
        - Updating denormalized views
        - Initializing indexes or caches

        Args:
            aggregate: Fully-hydrated aggregate with current state
            processor: The event processor to update

        Note:
            This method can be async to support I/O operations like writing
            to databases, calling external APIs, etc.
        """
        ...
