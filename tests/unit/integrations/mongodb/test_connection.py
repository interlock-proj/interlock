"""Unit tests for MongoDBConnectionManager using mocks."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ouroboros.integrations.mongodb import MongoDBConfig, MongoDBConnectionManager


@pytest.fixture
def config():
    """Create test configuration."""
    return MongoDBConfig(uri="mongodb://localhost:27017", database="test_db", max_pool_size=10)


@pytest.fixture
def mock_client():
    """Create a mock AsyncMongoClient."""
    client = MagicMock()
    client.admin = MagicMock()
    client.admin.command = AsyncMock(return_value={"ok": 1})
    client.close = AsyncMock()
    return client


def test_connection_manager_initialization(config):
    """Test connection manager initialization."""
    manager = MongoDBConnectionManager(config)

    assert manager.config == config
    assert manager._client is None


@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
def test_client_property_creates_client(mock_async_mongo_client, config):
    """Test that client property creates AsyncMongoClient on first access."""
    mock_client = MagicMock()
    mock_async_mongo_client.return_value = mock_client

    manager = MongoDBConnectionManager(config)
    client = manager.client

    assert client == mock_client
    mock_async_mongo_client.assert_called_once_with(
        config.uri,
        maxPoolSize=config.max_pool_size,
        minPoolSize=config.min_pool_size,
        serverSelectionTimeoutMS=config.server_selection_timeout_ms,
        connectTimeoutMS=config.connect_timeout_ms,
    )


@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
def test_client_property_reuses_client(mock_async_mongo_client, config):
    """Test that client property reuses existing client."""
    mock_client = MagicMock()
    mock_async_mongo_client.return_value = mock_client

    manager = MongoDBConnectionManager(config)
    client1 = manager.client
    client2 = manager.client

    assert client1 == client2
    mock_async_mongo_client.assert_called_once()  # Only called once


@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
def test_database_property(mock_async_mongo_client, config):
    """Test database property returns correct database."""
    mock_client = MagicMock()
    mock_database = MagicMock()
    mock_client.__getitem__.return_value = mock_database
    mock_async_mongo_client.return_value = mock_client

    manager = MongoDBConnectionManager(config)
    database = manager.database

    mock_client.__getitem__.assert_called_once_with("test_db")
    assert database == mock_database


@pytest.mark.asyncio
@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
async def test_verify_connectivity_success(mock_async_mongo_client, config):
    """Test verify_connectivity returns True when ping succeeds."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    mock_async_mongo_client.return_value = mock_client

    manager = MongoDBConnectionManager(config)
    result = await manager.verify_connectivity()

    assert result is True
    mock_client.admin.command.assert_called_once_with("ping")


@pytest.mark.asyncio
@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
async def test_verify_connectivity_failure(mock_async_mongo_client, config):
    """Test verify_connectivity returns False when ping fails."""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=Exception("Connection failed"))
    mock_async_mongo_client.return_value = mock_client

    manager = MongoDBConnectionManager(config)
    result = await manager.verify_connectivity()

    assert result is False


@pytest.mark.asyncio
@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
async def test_close(mock_async_mongo_client, config):
    """Test close method closes the client."""
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_async_mongo_client.return_value = mock_client

    manager = MongoDBConnectionManager(config)
    _ = manager.client  # Create client
    await manager.close()

    mock_client.close.assert_called_once()
    assert manager._client is None


@pytest.mark.asyncio
async def test_close_without_client(config):
    """Test close method does nothing when client not created."""
    manager = MongoDBConnectionManager(config)
    await manager.close()  # Should not raise


@pytest.mark.asyncio
@patch("ouroboros.integrations.mongodb.connection.AsyncMongoClient")
async def test_async_context_manager(mock_async_mongo_client, config):
    """Test async context manager closes client on exit."""
    mock_client = MagicMock()
    mock_client.close = AsyncMock()
    mock_async_mongo_client.return_value = mock_client

    async with MongoDBConnectionManager(config) as manager:
        _ = manager.client  # Access client

    mock_client.close.assert_called_once()
