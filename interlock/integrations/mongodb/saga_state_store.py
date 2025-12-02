"""MongoDB implementation of SagaStateStore for saga state persistence.

This module provides a MongoDB-backed saga state store implementation using
PyMongo's async API for managing saga state and step completion tracking.
"""

import importlib
from datetime import datetime

from pydantic import BaseModel

from interlock.application.events.processing.saga_state_store import SagaStateStore

from .connection import MongoDBConnectionManager


class MongoDBSagaStateStore(SagaStateStore):
    """MongoDB implementation of the SagaStateStore interface.

    This implementation uses MongoDB to store saga states with:
    - State serialized as JSON with type metadata for deserialization
    - Embedded array for completed steps tracking
    - Atomic updates for state transitions

    Collections:
        - saga_states: Stores saga state documents

    Document structure:
        {
            "_id": "saga_id",
            "state_type": "StateClassName",
            "state_module": "module.path",
            "state_json": "{...}",
            "completed_steps": ["step1", "step2"],
            "updated_at": ISODate(...)
        }

    Examples:
        >>> config = MongoDBConfig(uri="mongodb://localhost:27017")
        >>> manager = MongoDBConnectionManager(config)
        >>> store = MongoDBSagaStateStore(manager)
        >>> await store.initialize_schema()
        >>>
        >>> # Save saga state
        >>> await store.save("saga_123", my_state)
        >>>
        >>> # Load saga state
        >>> state = await store.load("saga_123")
        >>>
        >>> # Mark step complete
        >>> newly_marked = await store.mark_step_complete("saga_123", "reserve_inventory")
    """

    def __init__(self, connection_manager: MongoDBConnectionManager):
        """Initialize the MongoDB saga state store.

        Args:
            connection_manager: MongoDB connection manager
        """
        self.connection_manager = connection_manager

    @property
    def _saga_states_collection(self):
        """Get the saga states collection."""
        return self.connection_manager.database["saga_states"]

    async def initialize_schema(self) -> None:
        """Create necessary indexes for saga state storage.

        Creates:
            - Index on _id (saga_id) - automatically created by MongoDB

        Examples:
            >>> await store.initialize_schema()
        """
        # MongoDB automatically creates an index on _id, so no additional indexes needed
        # for basic saga state operations. If we need to query by state type or other
        # fields in the future, we can add indexes here.
        pass

    async def load(self, saga_id: str) -> BaseModel | None:
        """Load saga state by ID.

        Args:
            saga_id: Unique identifier for the saga instance

        Returns:
            The saga state if found, None otherwise

        Examples:
            >>> state = await store.load("checkout_saga_123")
            >>> if state:
            ...     print(f"Order ID: {state.order_id}")
        """
        doc = await self._saga_states_collection.find_one({"_id": saga_id})

        if not doc:
            return None

        return self._deserialize_state(doc)

    async def save(self, saga_id: str, state: BaseModel) -> None:
        """Save saga state.

        Args:
            saga_id: Unique identifier for the saga instance
            state: The state to save (any Pydantic BaseModel)

        Examples:
            >>> state = CheckoutState(order_id="123", status="pending")
            >>> await store.save("checkout_saga_123", state)
        """
        state_class = type(state)

        doc = {
            "_id": saga_id,
            "state_type": state_class.__name__,
            "state_module": state_class.__module__,
            "state_json": state.model_dump_json(),
            "updated_at": datetime.utcnow(),
        }

        # Preserve completed_steps if they exist
        existing = await self._saga_states_collection.find_one({"_id": saga_id})
        if existing and "completed_steps" in existing:
            doc["completed_steps"] = existing["completed_steps"]
        else:
            doc["completed_steps"] = []

        await self._saga_states_collection.replace_one({"_id": saga_id}, doc, upsert=True)

    async def delete(self, saga_id: str) -> None:
        """Delete saga state (cleanup after completion).

        Args:
            saga_id: Unique identifier for the saga instance

        Examples:
            >>> await store.delete("checkout_saga_123")
        """
        await self._saga_states_collection.delete_one({"_id": saga_id})

    async def mark_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Mark a saga step as completed (for idempotency).

        Args:
            saga_id: Unique identifier for the saga instance
            step_name: Name of the step to mark as complete

        Returns:
            True if newly marked (step was not already complete), False if already complete

        Examples:
            >>> newly_marked = await store.mark_step_complete(
            ...     "checkout_saga_123", "reserve_inventory"
            ... )
            >>> if newly_marked:
            ...     print("Step executed for the first time")
            >>> else:
            ...     print("Step already completed (idempotent retry)")
        """
        # Check if step is already complete
        existing = await self._saga_states_collection.find_one({"_id": saga_id})

        if not existing:
            # Saga state doesn't exist, create it with this step
            await self._saga_states_collection.insert_one(
                {
                    "_id": saga_id,
                    "completed_steps": [step_name],
                    "updated_at": datetime.utcnow(),
                }
            )
            return True

        completed_steps = existing.get("completed_steps", [])

        if step_name in completed_steps:
            # Step already complete
            return False

        # Add step to completed steps
        await self._saga_states_collection.update_one(
            {"_id": saga_id},
            {
                "$addToSet": {"completed_steps": step_name},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )
        return True

    async def is_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Check if a saga step has been completed.

        Args:
            saga_id: Unique identifier for the saga instance
            step_name: Name of the step to check

        Returns:
            True if step is complete, False otherwise

        Examples:
            >>> is_complete = await store.is_step_complete(
            ...     "checkout_saga_123", "reserve_inventory"
            ... )
            >>> if not is_complete:
            ...     # Execute step
            ...     await reserve_inventory()
        """
        doc = await self._saga_states_collection.find_one({"_id": saga_id})

        if not doc:
            return False

        completed_steps = doc.get("completed_steps", [])
        return step_name in completed_steps

    def _deserialize_state(self, doc: dict) -> BaseModel:
        """Deserialize saga state from MongoDB document.

        Args:
            doc: MongoDB document containing state data

        Returns:
            Reconstructed state instance
        """
        state_module = doc["state_module"]
        state_type = doc["state_type"]
        state_json = doc["state_json"]

        state_class = self._load_class(state_module, state_type)
        return state_class.model_validate_json(state_json)  # type: ignore[no-any-return]

    def _load_class(self, module_name: str, class_name: str) -> type:
        """Dynamically load a class from its module path.

        Args:
            module_name: Fully qualified module name
            class_name: Class name to load

        Returns:
            The loaded class

        Raises:
            ModuleNotFoundError: If module cannot be imported
            AttributeError: If class not found in module
        """
        module = importlib.import_module(module_name)
        return getattr(module, class_name)  # type: ignore[no-any-return]
