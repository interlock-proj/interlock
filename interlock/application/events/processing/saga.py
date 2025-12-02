"""Base saga class with state management and step idempotency."""

import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from .processor import EventProcessor
from .saga_state_store import SagaStateStore

TState = TypeVar("TState", bound=BaseModel)
TEvent = TypeVar("TEvent", bound=BaseModel)


class Saga(EventProcessor, Generic[TState]):
    """Base class for stateful sagas with automatic state management.

    Extends EventProcessor with:
    - Automatic state persistence via SagaStateStore
    - Step-level idempotency tracking
    - Type-safe state access through generics

    Sagas coordinate long-running business processes that span multiple
    aggregates. They handle compensation (rollback) when steps fail and
    ensure each step only executes once (idempotency).

    The Saga class is generic over TState for type safety, but the
    underlying SagaStateStore works with any BaseModel (like EventStore).

    Example:
        >>> from interlock.events.processing import Saga, saga_step, SagaStateStore
        >>> from interlock.routing import handles_event
        >>> from pydantic import BaseModel
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
        ...
        ...     @handles_event
        ...     @saga_step("initiate_checkout")
        ...     async def handle(self, event: CheckoutInitiated) -> None:
        ...         # Event must have saga_id field (convention)
        ...         state = CheckoutState(order_id=event.saga_id, status="started")
        ...         await self.set_state(event.saga_id, state)
        ...         await self.app.dispatch(ReserveInventory(...))
        ...
        ...     @handles_event
        ...     @saga_step("reserve_inventory", saga_id=lambda e: e.order_id)
        ...     async def handle(self, event: InventoryReserved) -> None:
        ...         # Custom extractor for events without saga_id field
        ...         # Lambda is type-safe: e is InventoryReserved
        ...         state = await self.get_state(event.order_id)
        ...         state.inventory_reserved = True
        ...         await self.set_state(event.order_id, state)
        ...         await self.app.dispatch(ChargePayment(...))

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
        self.logger = logging.getLogger(self.__class__.__name__)

    async def get_state(self, saga_id: str) -> TState | None:
        """Load saga state from storage.

        Args:
            saga_id: Unique identifier for the saga instance

        Returns:
            The saga state if found, None otherwise
        """
        state = await self.state_store.load(saga_id)
        return state  # type: ignore[return-value]

    async def set_state(self, saga_id: str, state: TState) -> None:
        """Save saga state to storage.

        Args:
            saga_id: Unique identifier for the saga instance
            state: The state to save
        """
        await self.state_store.save(saga_id, state)

    async def delete_state(self, saga_id: str) -> None:
        """Delete saga state (cleanup after completion).

        Args:
            saga_id: Unique identifier for the saga instance
        """
        await self.state_store.delete(saga_id)

    async def is_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Check if a saga step has been completed.

        Args:
            saga_id: Unique identifier for the saga instance
            step_name: Name of the step to check

        Returns:
            True if step is complete, False otherwise
        """
        return await self.state_store.is_step_complete(saga_id, step_name)

    async def mark_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Mark a saga step as complete.

        Args:
            saga_id: Unique identifier for the saga instance
            step_name: Name of the step to mark complete

        Returns:
            True if newly marked, False if already complete
        """
        return await self.state_store.mark_step_complete(saga_id, step_name)


def saga_step(
    step_name: str, saga_id: Callable[[TEvent], str] | None = None
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for saga steps providing automatic idempotency.

    Ensures each step only executes once per saga instance, even if
    the event is processed multiple times (e.g., due to retries or
    message broker redelivery).

    The decorator:
    1. Extracts the saga_id from the event (using extractor or convention)
    2. Checks if the step has already been completed
    3. If complete, skips execution (idempotency)
    4. If not complete, executes the step and marks it complete

    **Saga ID Extraction:**
    - By default, looks for `event.saga_id` (convention)
    - If `saga_id` extractor is provided, uses that instead
    - Extractor is a lambda/function that takes the event and returns saga_id
    - The extractor is fully type-safe - event type is inferred

    Args:
        step_name: Unique name for this step in the saga
        saga_id: Optional function to extract saga_id from event.
                If None, uses event.saga_id (convention)

    Example:
        Convention (event has saga_id field):
        >>> class CheckoutInitiated(BaseModel):
        ...     saga_id: str
        ...     customer_id: str
        >>>
        >>> @handles_event
        ... @saga_step("initiate_checkout")
        ... async def handle(self, event: CheckoutInitiated) -> None:
        ...     # Uses event.saga_id automatically
        ...     await self.app.dispatch(ReserveInventory(...))

        Custom extractor (event uses different field):
        >>> class InventoryReserved(BaseModel):
        ...     order_id: str  # No saga_id field
        >>>
        >>> @handles_event
        ... @saga_step("reserve_inventory", saga_id=lambda e: e.order_id)
        ... async def handle(self, event: InventoryReserved) -> None:
        ...     # Uses event.order_id as saga_id
        ...     # Lambda is type-safe: e is typed as InventoryReserved
        ...     await self.app.dispatch(ChargePayment(...))

        Composite saga_id:
        >>> @handles_event
        ... @saga_step("process_payment", saga_id=lambda e: f"{e.order_id}-{e.payment_id}")
        ... async def handle(self, event: PaymentProcessed) -> None:
        ...     # Full type safety - e is PaymentProcessed
        ...     # Type checker knows about e.order_id and e.payment_id
        ...     pass
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Saga[Any], event: BaseModel) -> Any:
            # Extract saga_id from event
            if saga_id is not None:
                # Use custom extractor (type-safe via TEvent generic)
                extracted_saga_id = saga_id(event)  # type: ignore[arg-type]
            else:
                # Use convention: event.saga_id
                extracted_saga_id = getattr(event, "saga_id", None)
                if extracted_saga_id is None:
                    raise ValueError(
                        f"Event {type(event).__name__} must have 'saga_id' field, "
                        f"or provide a custom extractor: "
                        f"@saga_step('{step_name}', saga_id=lambda e: e.your_field)"
                    )

            # Check if already complete (idempotency)
            if await self.is_step_complete(extracted_saga_id, step_name):
                self.logger.info(
                    f"Step '{step_name}' already complete for saga {extracted_saga_id}, skipping"
                )
                return None

            # Execute step
            try:
                result = await func(self, event)

                # Mark complete
                await self.mark_step_complete(extracted_saga_id, step_name)
                self.logger.info(
                    f"Step '{step_name}' completed for saga {extracted_saga_id}"
                )

                return result
            except Exception as e:
                self.logger.error(
                    f"Step '{step_name}' failed for saga {extracted_saga_id}: {e}"
                )
                raise

        return wrapper

    return decorator
