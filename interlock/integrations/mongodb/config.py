"""MongoDB configuration using pydantic-settings."""

from functools import cached_property
from typing import Any, Literal

from pydantic_settings import BaseSettings
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient


class MongoConfiguration(BaseSettings):
    """Configuration and factory for MongoDB resources.

    Implements the HasLifecycle protocol for integration with Interlock's
    application lifecycle management. The client is closed on shutdown.

    All settings can be configured via environment variables with the
    INTERLOCK_ prefix. For example:
    - INTERLOCK_MONGO_URI=mongodb://localhost:27017
    - INTERLOCK_MONGO_DATABASE=myapp
    - INTERLOCK_MONGO_EVENTS_COLLECTION=domain_events

    The configuration also acts as a factory, providing lazy-initialized
    properties for the MongoDB client, database, and collections.

    Attributes:
        uri: MongoDB connection URI.
        database: Database name to use.
        events_collection: Collection name for event storage.
        saga_states_collection: Collection name for saga state storage.
        snapshots_collection: Collection name for aggregate snapshots.
        idempotency_keys_collection: Collection name for idempotency keys.
        snapshot_mode: Storage mode for snapshots - "single" overwrites,
            "multiple" keeps version history.
        idempotency_ttl_seconds: TTL for idempotency keys in seconds.

    Example:
        >>> config = MongoConfiguration()
        >>>
        >>> # Access the database
        >>> db = config.db
        >>>
        >>> # Access collections
        >>> events = config.events
        >>> sagas = config.saga_states
        >>>
        >>> # With ApplicationBuilder (lifecycle managed automatically)
        >>> app = (
        ...     ApplicationBuilder()
        ...     .register_dependency(MongoConfiguration)
        ...     .build()
        ... )
        >>> async with app:  # calls on_startup/on_shutdown
        ...     ...
    """

    # Connection settings
    uri: str = "mongodb://localhost:27017"
    database: str = "interlock"

    # Collection names (configurable with sensible defaults)
    events_collection: str = "events"
    saga_states_collection: str = "saga_states"
    snapshots_collection: str = "snapshots"
    idempotency_keys_collection: str = "idempotency_keys"

    # Snapshot storage mode
    snapshot_mode: Literal["single", "multiple"] = "single"

    # Idempotency TTL (seconds) - default 24 hours
    idempotency_ttl_seconds: int = 86400

    model_config = {"env_prefix": "INTERLOCK_MONGO_"}

    @cached_property
    def client(self) -> AsyncMongoClient[dict[str, Any]]:
        """Get the MongoDB async client.

        The client is lazily created and cached for reuse.
        """
        return AsyncMongoClient(self.uri)

    @cached_property
    def db(self) -> AsyncDatabase[dict[str, Any]]:
        """Get the MongoDB async database.

        Uses the database name from configuration.
        """
        return self.client[self.database]

    @cached_property
    def events(self) -> AsyncCollection[dict[str, Any]]:
        """Get the events collection."""
        return self.db[self.events_collection]

    @cached_property
    def saga_states(self) -> AsyncCollection[dict[str, Any]]:
        """Get the saga states collection."""
        return self.db[self.saga_states_collection]

    @cached_property
    def snapshots(self) -> AsyncCollection[dict[str, Any]]:
        """Get the snapshots collection."""
        return self.db[self.snapshots_collection]

    @cached_property
    def idempotency_keys(self) -> AsyncCollection[dict[str, Any]]:
        """Get the idempotency keys collection."""
        return self.db[self.idempotency_keys_collection]

    # HasLifecycle protocol implementation

    async def on_startup(self) -> None:
        """Called when the application starts.

        No-op for MongoDB - connections are established lazily.
        """
        pass

    async def on_shutdown(self) -> None:
        """Called when the application shuts down.

        Closes the MongoDB client connection if it was created.
        """
        if "client" in self.__dict__:
            self.client.close()
