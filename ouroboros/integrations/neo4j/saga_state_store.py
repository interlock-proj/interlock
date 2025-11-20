"""Neo4j implementation of SagaStateStore."""

import importlib

from pydantic import BaseModel

from ...events.processing.saga_state_store import SagaStateStore
from .connection import Neo4jConnectionManager

# Cypher queries as constants (following Neo4j event store pattern)
CREATE_SAGA_INDEX = "CREATE INDEX saga_lookup IF NOT EXISTS FOR (s:Saga) ON (s.saga_id)"

CREATE_STEP_INDEX = (
    "CREATE INDEX step_lookup IF NOT EXISTS FOR (cs:CompletedStep) ON (cs.saga_id, cs.step_name)"
)

SAVE_STATE = """
MERGE (s:Saga {saga_id: $saga_id})
SET s.state_type = $state_type,
    s.state_module = $state_module,
    s.state_json = $state_json,
    s.updated_at = datetime()
ON CREATE SET s.created_at = datetime()
"""

LOAD_STATE = """
MATCH (s:Saga {saga_id: $saga_id})
RETURN s.state_type as state_type,
       s.state_module as state_module,
       s.state_json as state_json
"""

DELETE_STATE = """
MATCH (s:Saga {saga_id: $saga_id})
OPTIONAL MATCH (s)-[:COMPLETED_STEP]->(cs:CompletedStep)
DETACH DELETE s, cs
"""

MARK_STEP_COMPLETE = """
MERGE (s:Saga {saga_id: $saga_id})
MERGE (s)-[:COMPLETED_STEP]->(cs:CompletedStep {saga_id: $saga_id, step_name: $step_name})
ON CREATE SET cs.completed_at = datetime()
RETURN cs.completed_at as was_created
"""

IS_STEP_COMPLETE = """
MATCH (s:Saga {saga_id: $saga_id})-[:COMPLETED_STEP]->(cs:CompletedStep {step_name: $step_name})
RETURN cs
"""


class Neo4jSagaStateStore(SagaStateStore):
    """Neo4j-backed saga state store.

    Mirrors Neo4jSnapshotBackend pattern:
    - Stores state as JSON with module/type metadata for deserialization
    - Uses dynamic class loading like event store
    - Separate nodes for completed steps (idempotency tracking)

    Graph model:
    - (Saga {saga_id, state_json, state_type, state_module})
    - (Saga)-[:COMPLETED_STEP]->(CompletedStep {step_name})

    Example:
        >>> from ouroboros.integrations.neo4j import Neo4jConnectionManager, Neo4jSagaStateStore
        >>>
        >>> connection_manager = Neo4jConnectionManager(config)
        >>> state_store = Neo4jSagaStateStore(connection_manager)
        >>> await state_store.initialize_schema()
        >>>
        >>> app = (ApplicationBuilder()
        ...     .add_dependency(SagaStateStore, state_store)
        ...     .add_event_processor(CheckoutSaga)
        ...     .build())
    """

    def __init__(self, connection_manager: Neo4jConnectionManager):
        """Initialize Neo4j saga state store.

        Args:
            connection_manager: Neo4j connection manager
        """
        self.connection_manager = connection_manager

    async def initialize_schema(self) -> None:
        """Create required indexes."""
        async with self.connection_manager.session() as session:
            await session.run(CREATE_SAGA_INDEX)
            await session.run(CREATE_STEP_INDEX)

    async def save(self, saga_id: str, state: BaseModel) -> None:
        """Save saga state with type metadata for deserialization.

        Follows Neo4jSnapshotBackend pattern - stores module/type for
        dynamic class loading on deserialization.
        """
        state_class = type(state)

        async with self.connection_manager.session() as session:
            await session.run(
                SAVE_STATE,
                saga_id=saga_id,
                state_type=state_class.__name__,
                state_module=state_class.__module__,
                state_json=state.model_dump_json(),
            )

    async def load(self, saga_id: str) -> BaseModel | None:
        """Load saga state and deserialize using stored type metadata.

        Follows Neo4jEventStore deserialization pattern.
        """
        async with self.connection_manager.session() as session:
            result = await session.run(LOAD_STATE, saga_id=saga_id)
            record = await result.single()

            if not record:
                return None

            return self._deserialize_state(
                record["state_module"], record["state_type"], record["state_json"]
            )

    async def delete(self, saga_id: str) -> None:
        """Delete saga state and all completed steps."""
        async with self.connection_manager.session() as session:
            await session.run(DELETE_STATE, saga_id=saga_id)

    async def mark_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Mark step as complete using MERGE for idempotency.

        Uses Cypher's MERGE to atomically check-and-set, similar to
        how Neo4jEventStore handles concurrency.

        Returns:
            True if newly created, False if already existed
        """
        async with self.connection_manager.session() as session:
            result = await session.run(MARK_STEP_COMPLETE, saga_id=saga_id, step_name=step_name)
            record = await result.single()
            # If was_created exists, it was just created (ON CREATE)
            return record["was_created"] is not None

    async def is_step_complete(self, saga_id: str, step_name: str) -> bool:
        """Check if step is complete."""
        async with self.connection_manager.session() as session:
            result = await session.run(IS_STEP_COMPLETE, saga_id=saga_id, step_name=step_name)
            record = await result.single()
            return record is not None

    def _deserialize_state(self, module_name: str, class_name: str, state_json: str) -> BaseModel:
        """Deserialize state from JSON using stored type metadata.

        Follows the exact pattern from Neo4jSnapshotBackend and Neo4jEventStore.
        """
        state_class = self._load_class(module_name, class_name)
        return state_class.model_validate_json(state_json)  # type: ignore[no-any-return]

    def _load_class(self, module_name: str, class_name: str) -> type:
        """Dynamically load a class from its module path.

        Reuses the exact pattern from Neo4j event store and snapshot backend.
        """
        module = importlib.import_module(module_name)
        return getattr(module, class_name)  # type: ignore[no-any-return]
