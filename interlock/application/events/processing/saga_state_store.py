"""Abstract saga state storage with pluggable backends."""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class SagaStateStore(ABC):
    """Abstract storage backend for saga state.

    Similar to AggregateSnapshotStorageBackend but for saga state.
    Not generic - works with any Pydantic BaseModel state type.

    Sagas are long-running business processes that coordinate multiple
    aggregates and handle compensation (rollback) when things fail.
    This store provides persistent state management for sagas.

    Example:
        >>> from interlock.events.processing import Saga, SagaStateStore
        >>>
        >>> class CheckoutState(BaseModel):
        ...     order_id: str
        ...     status: str
        ...     inventory_reserved: bool = False
        >>>
        >>> class CheckoutSaga(Saga[CheckoutState]):
        ...     def __init__(self, app: Application, state_store: SagaStateStore):
        ...         super().__init__(state_store)
        ...         self.app = app
        >>>
        >>> # Use in-memory store for development
        >>> store = SagaStateStore.in_memory()
        >>> saga = CheckoutSaga(app, store)
    """

    @staticmethod
    def in_memory() -> "SagaStateStore":
        """Create in-memory state store for development/testing."""
        return InMemorySagaStateStore()

    @abstractmethod
    async def load(self, saga_id: str) -> BaseModel | None:
        """Load saga state by ID.

        Args:
            saga_id: Unique identifier for the saga instance

        Returns:
            The saga state if found, None otherwise
        """
        ...

    @abstractmethod
    async def save(self, saga_id: str, state: BaseModel) -> None:
        """Save saga state.

        Args:
            saga_id: Unique identifier for the saga instance
            state: The state to save (any Pydantic BaseModel)
        """
        ...

    @abstractmethod
    async def delete(self, saga_id: str) -> None:
        """Delete saga state (cleanup after completion).

        Args:
            saga_id: Unique identifier for the saga instance
        """
        ...

    @abstractmethod
    async def mark_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Mark a saga step as completed (for idempotency).

        This ensures that saga steps only execute once, even if the
        same event is processed multiple times (e.g., due to retries).

        Args:
            saga_id: Unique identifier for the saga instance
            step_name: Name of the step to mark complete

        Returns:
            True if newly marked, False if already complete
        """
        ...

    @abstractmethod
    async def is_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Check if a saga step has been completed.

        Args:
            saga_id: Unique identifier for the saga instance
            step_name: Name of the step to check

        Returns:
            True if step is complete, False otherwise
        """
        ...


class InMemorySagaStateStore(SagaStateStore):
    """In-memory saga state store for development and testing.

    Mirrors InMemoryAggregateSnapshotStorageBackend pattern.
    Not intended for production use - state is lost on restart.

    Example:
        >>> store = InMemorySagaStateStore()
        >>>
        >>> # Save state
        >>> state = CheckoutState(order_id="order-1", status="started")
        >>> await store.save("order-1", state)
        >>>
        >>> # Load state
        >>> loaded = await store.load("order-1")
        >>> assert loaded.order_id == "order-1"
        >>>
        >>> # Mark step complete
        >>> was_new = await store.mark_step_complete("order-1", "reserve_inventory")
        >>> assert was_new is True
        >>>
        >>> # Check idempotency
        >>> was_new = await store.mark_step_complete("order-1", "reserve_inventory")
        >>> assert was_new is False  # Already complete
    """

    def __init__(self) -> None:
        self._states: dict[str, BaseModel] = {}
        self._completed_steps: dict[str, set[str]] = {}

    async def load(self, saga_id: str) -> BaseModel | None:
        return self._states.get(saga_id)

    async def save(self, saga_id: str, state: BaseModel) -> None:
        self._states[saga_id] = state

    async def delete(self, saga_id: str) -> None:
        self._states.pop(saga_id, None)
        self._completed_steps.pop(saga_id, None)

    async def mark_step_complete(self, saga_id: str, step_name: str) -> bool:
        if saga_id not in self._completed_steps:
            self._completed_steps[saga_id] = set()

        if step_name in self._completed_steps[saga_id]:
            return False  # Already complete

        self._completed_steps[saga_id].add(step_name)
        return True

    async def is_step_complete(self, saga_id: str, step_name: str) -> bool:
        return step_name in self._completed_steps.get(saga_id, set())
