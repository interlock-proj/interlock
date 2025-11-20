"""Connection management for Neo4j integration.

This module provides async connection pooling and session management for Neo4j,
including context managers for transaction handling.
"""

from contextlib import asynccontextmanager

try:
    from neo4j import AsyncDriver, AsyncGraphDatabase
except ImportError as err:
    raise ImportError(
        "neo4j package is required for Neo4j integration. "
        "Install it with: pip install ouroboros[neo4j]"
    ) from err

from .config import Neo4jConfig


class Neo4jConnectionManager:
    """Manages Neo4j database connections and sessions asynchronously.

    This class handles async connection pooling, session creation, and transaction
    management for Neo4j operations. It uses the official Neo4j Python driver's
    async API and provides async context managers for safe resource handling.

    Attributes:
        config: Neo4j configuration object
        driver: Neo4j async driver instance (initialized on first use)

    Examples:
        >>> config = Neo4jConfig(
        ...     uri="bolt://localhost:7687",
        ...     username="neo4j",
        ...     password="password"
        ... )
        >>> manager = Neo4jConnectionManager(config)
        >>> async with manager.session() as session:
        ...     result = await session.run("MATCH (n) RETURN count(n)")
        >>> await manager.close()
    """

    def __init__(self, config: Neo4jConfig):
        """Initialize the connection manager.

        Args:
            config: Neo4j configuration object
        """
        self.config = config
        self._driver: AsyncDriver | None = None

    @property
    def driver(self) -> AsyncDriver:
        """Get or create the Neo4j async driver instance.

        Returns:
            Neo4j async driver instance

        Raises:
            Exception: If driver creation fails
        """
        if self._driver is None:
            # Use None for auth if username is empty (no auth)
            auth = (
                None if not self.config.username else (self.config.username, self.config.password)
            )

            kwargs = {
                "auth": auth,
                "max_connection_pool_size": self.config.max_connection_pool_size,
                "connection_timeout": self.config.connection_timeout,
                "max_transaction_retry_time": self.config.max_transaction_retry_time,
                "encrypted": self.config.encrypted,
            }
            if self.config.trust is not None:
                kwargs["trust"] = self.config.trust

            self._driver = AsyncGraphDatabase.driver(self.config.uri, **kwargs)
        return self._driver

    @asynccontextmanager
    async def session(self, database: str | None = None):
        """Create an async Neo4j session context manager.

        Args:
            database: Optional database name override (defaults to config.database)

        Yields:
            Neo4j async session instance

        Examples:
            >>> async with manager.session() as session:
            ...     await session.run("CREATE (n:Node {name: $name})", name="test")
        """
        db_name = database or self.config.database
        session = self.driver.session(database=db_name)
        try:
            yield session
        finally:
            await session.close()

    @asynccontextmanager
    async def transaction(self, database: str | None = None):
        """Create an async transaction context manager.

        This provides automatic commit/rollback behavior. The transaction
        will be committed if no exception occurs, and rolled back otherwise.

        Args:
            database: Optional database name override (defaults to config.database)

        Yields:
            Neo4j async transaction

        Examples:
            >>> async with manager.transaction() as tx:
            ...     await tx.run("CREATE (n:Node {name: $name})", name="test")
            ...     # Automatically committed on successful exit
        """
        async with self.session(database=database) as session:
            tx = await session.begin_transaction()
            try:
                yield tx
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise

    async def verify_connectivity(self) -> bool:
        """Verify that the database connection is working.

        Returns:
            True if connection is successful, False otherwise

        Examples:
            >>> if await manager.verify_connectivity():
            ...     print("Connected to Neo4j")
        """
        try:
            await self.driver.verify_connectivity()
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """Close the driver and all connections.

        This should be called when the connection manager is no longer needed
        to ensure proper cleanup of resources.

        Examples:
            >>> await manager.close()
        """
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensures driver is closed."""
        await self.close()
        return False
