"""Base saga class with state management and step idempotency."""

import inspect
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from functools import wraps
from typing import Any, Generic, Type, TypeVar

from pydantic import BaseModel

from .processor import EventProcessor
from ....routing import handles_event

TState = TypeVar("TState", bound=BaseModel)
TEvent = TypeVar("TEvent", bound=BaseModel)


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



class Saga(EventProcessor, Generic[TState]):
    """Base class for stateful sagas with automatic state management.

    Extends EventProcessor with:
    - Automatic state persistence via SagaStateStore
    - Step-level idempotency tracking
    - Type-safe state access through generics
    - Automatic event routing via @saga_step decorator

    Sagas coordinate long-running business processes that span multiple
    aggregates. They handle compensation (rollback) when steps fail and
    ensure each step only executes once (idempotency).

    The Saga class is generic over TState for type safety, but the
    underlying SagaStateStore works with any BaseModel (like EventStore).

    **Handler Patterns:**
    - First step: Returns initial state
    - Subsequent steps: Receives and returns modified state
    - Cleanup steps: Returns None to delete state

    Example:
        >>> from interlock.application.events import (
        ...     Saga, saga_step, SagaStateStore
        ... )
        >>> from pydantic import BaseModel
        >>>
        >>> class CheckoutState(BaseModel):
        ...     order_id: str
        ...     status: str
        ...     inventory_reserved: bool = False
        ...     payment_charged: bool = False
        >>>
        >>> class CheckoutSaga(Saga[CheckoutState]):
        ...     def __init__(self, state_store: SagaStateStore):
        ...         super().__init__(state_store)
        ...
        ...     @saga_step  # Step name auto-inferred from function name
        ...     async def on_checkout_initiated(
        ...         self, event: CheckoutInitiated
        ...     ) -> CheckoutState:
        ...         # First step - return initial state
        ...         return CheckoutState(
        ...             order_id=event.saga_id, status="started"
        ...         )
        ...
        ...     @saga_step(saga_id=lambda e: e.order_id)
        ...     async def on_inventory_reserved(
        ...         self, event: InventoryReserved, state: CheckoutState
        ...     ) -> CheckoutState:
        ...         # Subsequent step - modify and return state
        ...         state.inventory_reserved = True
        ...         state.status = "inventory_reserved"
        ...         return state
        ...
        ...     @saga_step(saga_id=lambda e: e.order_id)
        ...     async def on_payment_charged(
        ...         self, event: PaymentCharged, state: CheckoutState
        ...     ) -> CheckoutState:
        ...         state.payment_charged = True
        ...         state.status = "completed"
        ...         return state
        ...
        ...     @saga_step
        ...     async def on_order_cancelled(
        ...         self, event: OrderCancelled, state: CheckoutState
        ...     ) -> None:
        ...         # Cleanup - return None to delete state
        ...         return None

    Usage with ApplicationBuilder:
        >>> # Saga is just an EventProcessor - no special handling needed!
        >>> app = (ApplicationBuilder()
        ...     .add_dependency(SagaStateStore, InMemorySagaStateStore())
        ...     .add_event_processor(CheckoutSaga)
        ...     .build())
    """

    def __init__(self, state_store: SagaStateStore):
        """Initialize saga with state store.

        Args:
            state_store: Storage backend for saga state
        """
        super().__init__()
        self.state_store = state_store


class SagaStepExecutor(ABC):
    """Base class for executing saga steps with idempotency."""

    @staticmethod
    def executor_from_function(
        function: Callable[..., Any],
    ) -> Type["SagaStepExecutor"]:
        params = list(inspect.signature(function).parameters.values())
        expects_state = len(params) >= 3  # self, event, state
        return SubsequentStepExecutor if expects_state else InitialStepExecutor

    def __init__(
        self,
        step_name: str,
        saga_id_extractor: Callable[[BaseModel], str] | None,
        handler_func: Callable[..., Any],
    ):
        self.step_name = step_name
        self.saga_id_extractor = saga_id_extractor
        self.handler_func = handler_func
        self.logger = logging.getLogger(self.__class__.__name__)

    def extract_saga_id(self, event: BaseModel) -> str:
        """Extract saga_id from event using extractor or convention."""
        if self.saga_id_extractor is not None:
            return self.saga_id_extractor(event)  # type: ignore

        saga_id = getattr(event, "saga_id", None)
        if saga_id is None:
            raise ValueError(
                f"Event {type(event).__name__} must have "
                f"'saga_id' field, or provide a custom extractor: "
                f"@saga_step(saga_id=lambda e: e.your_field)"
            )
        return saga_id

    async def check_idempotency(self, saga: Saga[Any], saga_id: str) -> bool:
        """Check if step is already complete. Returns True if should skip."""
        if await saga.state_store.is_step_complete(saga_id, self.step_name):
            self.logger.info(
                f"Step '{self.step_name}' already complete for saga "
                f"{saga_id}, skipping"
            )
            return True
        return False

    async def persist_state(self, saga: Saga[Any], saga_id: str, result: Any) -> None:
        """Persist state based on handler return value."""
        if result is None:
            await saga.state_store.delete(saga_id)
        elif isinstance(result, BaseModel):
            await saga.state_store.save(saga_id, result)
        # else: void return, no state change

    async def mark_step_completed(self, saga: Saga[Any], saga_id: str) -> None:
        """Mark step as complete and log."""
        await saga.state_store.mark_step_complete(saga_id, self.step_name)
        self.logger.info(f"Step '{self.step_name}' completed for saga {saga_id}")

    @abstractmethod
    async def execute_handler(
        self, saga: Saga[Any], event: BaseModel, saga_id: str
    ) -> Any:
        """Execute the handler function with appropriate parameters."""
        ...

    async def execute(self, saga: Saga[Any], event: BaseModel) -> Any:
        """Execute complete saga step with idempotency and state management."""
        saga_id = self.extract_saga_id(event)
        try:
            if await self.check_idempotency(saga, saga_id):
                return None
            result = await self.execute_handler(saga, event, saga_id)
            await self.mark_step_completed(saga, saga_id)
            await self.persist_state(saga, saga_id, result)
            return result
        except Exception as e:
            self.logger.error(f"Step '{self.step_name}' failed for saga {saga_id}: {e}")
            raise e


class InitialStepExecutor(SagaStepExecutor):
    """Executor for initial saga steps that don't expect existing state."""

    async def execute_handler(
        self, saga: Saga[Any], event: BaseModel, saga_id: str
    ) -> Any:
        """Execute handler without state parameter."""
        return await self.handler_func(saga, event)


class SubsequentStepExecutor(SagaStepExecutor):
    """Executor for subsequent saga steps that expect existing state."""

    async def execute_handler(
        self, saga: Saga[Any], event: BaseModel, saga_id: str
    ) -> Any:
        """Execute handler with state parameter."""
        state = await saga.state_store.load(saga_id)
        if state is None:
            raise ValueError(
                f"State not found for saga {saga_id}. "
                f"Handler {self.handler_func.__name__} expects state "
                f"parameter but no state exists."
            )
        return await self.handler_func(saga, event, state)


def saga_step(
    f: Callable[..., Any] | None = None,
    *,
    step_name: str | None = None,
    saga_id: Callable[[TEvent], str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for saga steps providing automatic idempotency
    and state management.

    This decorator automatically:
    1. Applies @handles_event for event routing
    2. Infers step name from function name if not provided
    3. Extracts saga_id from event (using extractor or convention)
    4. Checks if the step has already been completed (idempotency)
    5. Loads and passes state to handler if it expects a state parameter
    6. Persists state changes based on return value
    7. Marks step as complete

    **Handler Signatures:**
    - First step (no existing state):
      `async def handler(self, event: Event) -> State`
      Returns the initial state to be persisted.
    - Subsequent steps:
      `async def handler(self, event: Event, state: State) -> State | None`
      Receives current state, returns updated state or None to delete.

    **State Management:**
    - Return a BaseModel: State is automatically saved
    - Return None: State is automatically deleted
    - No return (void): State is not modified

    **Saga ID Extraction:**
    - By default, looks for `event.saga_id` (convention)
    - If `saga_id` extractor is provided, uses that instead
    - Extractor is a lambda/function that takes the event and returns
      saga_id

    Args:
        f: Function being decorated (provided when used as @saga_step)
        step_name: Unique name for this step. If None, inferred from
            function name.
        saga_id: Optional function to extract saga_id from event.
            If None, uses event.saga_id (convention)

    Example:
        No parameters (step name inferred from function name):
        >>> @saga_step
        ... async def on_checkout_initiated(
        ...     self, event: CheckoutInitiated
        ... ) -> CheckoutState:
        ...     # Step name is "on_checkout_initiated"
        ...     return CheckoutState(
        ...         order_id=event.saga_id, status="started"
        ...     )

        With step name:
        >>> @saga_step(step_name="reserve_inventory")
        ... async def handle_reservation(
        ...     self, event: InventoryReserved, state: CheckoutState
        ... ) -> CheckoutState:
        ...     state.inventory_reserved = True
        ...     return state

        Custom saga_id extractor:
        >>> @saga_step(saga_id=lambda e: e.order_id)
        ... async def on_inventory_reserved(
        ...     self, event: InventoryReserved, state: CheckoutState
        ... ) -> CheckoutState:
        ...     state.inventory_reserved = True
        ...     return state

        Delete state by returning None:
        >>> @saga_step
        ... async def on_order_cancelled(
        ...     self, event: OrderCancelled, state: CheckoutState
        ... ) -> None:
        ...     # Cleanup logic here
        ...     return None  # State is deleted
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        resolved_step_name = step_name or func.__name__
        variant = SagaStepExecutor.executor_from_function(func)
        executor = variant(resolved_step_name, saga_id, func)

        @handles_event
        @wraps(func)
        async def wrapper(self: Saga[Any], event: BaseModel) -> Any:
            return await executor.execute(self, event)

        return wrapper

    # If no function is provided, that means we were called like
    # @saga_step(step_name="...") which means we need to return a decorator.
    # If the function _is_ provided, that means we were called like @saga_step.
    # So we need to return a decorated function.
    return decorator if f is None else decorator(f)
