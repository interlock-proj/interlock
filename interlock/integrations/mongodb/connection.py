"""Connection management for MongoDB integration.

This module provides async connection pooling and database access for MongoDB,
using PyMongo's native async support with AsyncMongoClient.
"""

try:
    from pymongo import AsyncMongoClient
except ImportError as err:
    raise ImportError(
        "pymongo package is required for MongoDB integration. "
        "Install it with: pip install interlock[mongodb]"
    ) from err

from .config import MongoDBConfig


class MongoDBConnectionManager:
    """Manages MongoDB database connections asynchronously.

    This class handles async connection pooling and database access for MongoDB
    operations. It uses the official PyMongo async API (AsyncMongoClient) which
    provides native asyncio support without the need for Motor.

    Attributes:
        config: MongoDB configuration object
        client: MongoDB async client instance (initialized on first use)

    Examples:
        >>> config = MongoDBConfig(
        ...     uri="mongodb://localhost:27017",
        ...     database="myapp"
        ... )
        >>> manager = MongoDBConnectionManager(config)
        >>> db = manager.database
        >>> collection = db["users"]
        >>> await collection.insert_one({"name": "Alice"})
        >>> await manager.close()

        >>> # Using async context manager
        >>> async with MongoDBConnectionManager(config) as manager:
        ...     db = manager.database
        ...     await db["users"].find_one({"name": "Alice"})
    """

    def __init__(self, config: MongoDBConfig):
        """Initialize the connection manager.

        Args:
            config: MongoDB configuration object
        """
        self.config = config
        self._client: AsyncMongoClient | None = None

    @property
    def client(self) -> AsyncMongoClient:
        """Get or create the MongoDB async client instance.

        Returns:
            MongoDB async client instance

        Raises:
            Exception: If client creation fails
        """
        if self._client is None:
            kwargs = {
                "maxPoolSize": self.config.max_pool_size,
                "minPoolSize": self.config.min_pool_size,
                "serverSelectionTimeoutMS": self.config.server_selection_timeout_ms,
                "connectTimeoutMS": self.config.connect_timeout_ms,
            }

            if self.config.max_idle_time_ms is not None:
                kwargs["maxIdleTimeMS"] = self.config.max_idle_time_ms

            if self.config.socket_timeout_ms is not None:
                kwargs["socketTimeoutMS"] = self.config.socket_timeout_ms

            self._client = AsyncMongoClient(self.config.uri, **kwargs)
        return self._client

    @property
    def database(self):
        """Get the configured database.

        Returns:
            MongoDB async database instance

        Examples:
            >>> manager = MongoDBConnectionManager(config)
            >>> db = manager.database
            >>> await db.list_collection_names()
        """
        return self.client[self.config.database]

    async def verify_connectivity(self) -> bool:
        """Verify that the database connection is working.

        Returns:
            True if connection is successful, False otherwise

        Examples:
            >>> if await manager.verify_connectivity():
            ...     print("Connected to MongoDB")
        """
        try:
            # Ping the database to verify connectivity
            await self.client.admin.command("ping")
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the client and all connections.

        This should be called when the connection manager is no longer needed
        to ensure proper cleanup of resources.

        Examples:
            >>> await manager.close()
        """
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures client is closed."""
        await self.close()
        return False
