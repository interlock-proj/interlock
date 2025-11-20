"""Unit tests for Neo4jConnectionManager using mocks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from interlock.integrations.neo4j import Neo4jConfig, Neo4jConnectionManager


@pytest.fixture
def config():
    """Create test configuration."""
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
        database="testdb",
    )


@pytest.fixture
def mock_driver():
    """Create mock Neo4j driver."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_driver_property_lazy_init(config):
    """Test driver is lazily initialized."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)
        assert manager._driver is None

        # Access driver property
        driver = manager.driver

        assert driver == mock_driver
        mock_gdb.driver.assert_called_once_with(
            config.uri,
            auth=(config.username, config.password),
            max_connection_pool_size=config.max_connection_pool_size,
            connection_timeout=config.connection_timeout,
            max_transaction_retry_time=config.max_transaction_retry_time,
            encrypted=config.encrypted,
        )


@pytest.mark.asyncio
async def test_session_context_manager(config):
    """Test session context manager."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = MagicMock()  # Use MagicMock for driver to avoid async issues
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        mock_driver.session = MagicMock(return_value=mock_session)  # Make session() sync
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)

        async with manager.session() as session:
            assert session == mock_session

        mock_session.close.assert_called_once()


@pytest.mark.asyncio
async def test_session_with_custom_database(config):
    """Test session with custom database override."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        mock_driver.session = MagicMock(return_value=mock_session)
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)

        async with manager.session(database="customdb"):
            pass

        mock_driver.session.assert_called_with(database="customdb")


@pytest.mark.asyncio
async def test_transaction_commit(config):
    """Test transaction commits on success."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        mock_tx = AsyncMock()

        mock_driver.session = MagicMock(return_value=mock_session)
        mock_session.begin_transaction = AsyncMock(return_value=mock_tx)
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)

        async with manager.transaction() as tx:
            assert tx == mock_tx

        mock_tx.commit.assert_called_once()
        mock_tx.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_transaction_rollback_on_error(config):
    """Test transaction rolls back on exception."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = MagicMock()
        mock_session = MagicMock()
        mock_session.close = AsyncMock()
        mock_tx = AsyncMock()

        mock_driver.session = MagicMock(return_value=mock_session)
        mock_session.begin_transaction = AsyncMock(return_value=mock_tx)
        mock_driver.verify_connectivity = AsyncMock()
        mock_driver.close = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)

        with pytest.raises(ValueError):
            async with manager.transaction():
                raise ValueError("Test error")

        mock_tx.rollback.assert_called_once()
        mock_tx.commit.assert_not_called()


@pytest.mark.asyncio
async def test_verify_connectivity_success(config):
    """Test connectivity verification succeeds."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_driver.verify_connectivity.return_value = None
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)
        result = await manager.verify_connectivity()

        assert result is True
        mock_driver.verify_connectivity.assert_called_once()


@pytest.mark.asyncio
async def test_verify_connectivity_failure(config):
    """Test connectivity verification fails gracefully."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_driver.verify_connectivity.side_effect = Exception("Connection failed")
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)
        result = await manager.verify_connectivity()

        assert result is False


@pytest.mark.asyncio
async def test_close(config):
    """Test closing the connection manager."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        manager = Neo4jConnectionManager(config)
        _ = manager.driver  # Initialize driver

        await manager.close()

        mock_driver.close.assert_called_once()
        assert manager._driver is None


@pytest.mark.asyncio
async def test_async_context_manager(config):
    """Test async context manager."""
    with patch("interlock.integrations.neo4j.connection.AsyncGraphDatabase") as mock_gdb:
        mock_driver = AsyncMock()
        mock_gdb.driver.return_value = mock_driver

        async with Neo4jConnectionManager(config) as manager:
            _ = manager.driver

        mock_driver.close.assert_called_once()
