"""MongoDB implementation of SagaStateStore."""

from typing import Any

from pydantic import BaseModel, Field

from interlock.application.events.processing.saga import SagaStateStore
from interlock.integrations.mongodb.collection import IndexedCollection
from interlock.integrations.mongodb.config import MongoConfiguration
from interlock.integrations.mongodb.type_loader import get_qualified_name, load_type


class SagaStateDocument(BaseModel):
    """Saga state document representation for MongoDB storage."""

    state_type: str = Field(description="Fully qualified type name of the state")
    state: dict[str, Any] = Field(description="Serialized state payload")
    completed_steps: list[str] = Field(
        default_factory=list,
        description="List of completed step names for idempotency",
    )

    @classmethod
    def from_value(cls, state: BaseModel) -> "SagaStateDocument":
        """Create a document from saga state."""
        return cls(
            state_type=get_qualified_name(type(state)),
            state=state.model_dump(mode="json"),
        )

    def to_value(self) -> BaseModel:
        """Convert the document back to saga state."""
        state_type = load_type(self.state_type)
        result: BaseModel = state_type(**self.state)
        return result


class MongoSagaStateStore(SagaStateStore):
    """MongoDB-backed saga state store.

    Stores saga state and completed step tracking in a MongoDB collection.
    Each saga instance is stored as a single document with its state and
    a list of completed steps for idempotency.

    Document schema:
        {
            "_id": "saga_id",
            "state_type": "module.ClassName",
            "state": { ... serialized state ... },
            "completed_steps": ["step1", "step2", ...]
        }

    State types are automatically resolved via dynamic import from
    the stored qualified type name - no manual registration required.

    Example:
        >>> from interlock.integrations.mongodb import (
        ...     MongoConfiguration, MongoSagaStateStore
        ... )
        >>>
        >>> config = MongoConfiguration()
        >>> store = MongoSagaStateStore(config)
        >>>
        >>> # Save saga state
        >>> await store.save("order-123", CheckoutState(status="started"))
        >>>
        >>> # Mark steps complete for idempotency
        >>> was_new = await store.mark_step_complete("order-123", "reserve_inventory")
    """

    def __init__(self, config: MongoConfiguration) -> None:
        """Initialize the MongoDB saga state store.

        Args:
            config: MongoDB configuration providing connection and collections.
        """
        # No indexes needed - _id is indexed by default
        self._collection = IndexedCollection(config.saga_states)

    async def load(self, saga_id: str) -> BaseModel | None:
        """Load saga state by ID.

        Args:
            saga_id: Unique identifier for the saga instance.

        Returns:
            The saga state if found, None otherwise.
        """
        doc = await self._collection.find_one({"_id": saga_id})

        if doc is None:
            return None

        state_doc = SagaStateDocument.model_validate(doc)
        return state_doc.to_value()

    async def save(self, saga_id: str, state: BaseModel) -> None:
        """Save saga state.

        Args:
            saga_id: Unique identifier for the saga instance.
            state: The state to save.
        """
        state_doc = SagaStateDocument.from_value(state)

        await self._collection.update_one(
            {"_id": saga_id},
            {
                "$set": {
                    "state_type": state_doc.state_type,
                    "state": state_doc.state,
                },
                "$setOnInsert": {
                    "completed_steps": [],
                },
            },
            upsert=True,
        )

    async def delete(self, saga_id: str) -> None:
        """Delete saga state (cleanup after completion).

        Args:
            saga_id: Unique identifier for the saga instance.
        """
        await self._collection.delete_one({"_id": saga_id})

    async def mark_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Mark a saga step as completed (for idempotency).

        Uses MongoDB's $addToSet to atomically add the step name to the
        completed_steps array if it doesn't already exist.

        Args:
            saga_id: Unique identifier for the saga instance.
            step_name: Name of the step to mark complete.

        Returns:
            True if newly marked, False if already complete.
        """
        # First check if already complete
        if await self.is_step_complete(saga_id, step_name):
            return False

        # Add to completed steps (upsert in case saga doesn't exist yet)
        result = await self._collection.update_one(
            {"_id": saga_id},
            {"$addToSet": {"completed_steps": step_name}},
            upsert=True,
        )

        # If modified_count > 0, the step was newly added
        # If upserted_id is set, it was a new document
        return result.modified_count > 0 or result.upserted_id is not None

    async def is_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Check if a saga step has been completed.

        Args:
            saga_id: Unique identifier for the saga instance.
            step_name: Name of the step to check.

        Returns:
            True if step is complete, False otherwise.
        """
        doc = await self._collection.find_one(
            {"_id": saga_id, "completed_steps": step_name},
            projection={"_id": 1},
        )
        return doc is not None
