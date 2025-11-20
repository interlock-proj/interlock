"""Unit tests for MongoDBConfig."""

import pytest
from pydantic import ValidationError

from ouroboros.integrations.mongodb import MongoDBConfig


def test_config_with_defaults():
    """Test config creation with default values."""
    config = MongoDBConfig(uri="mongodb://localhost:27017")

    assert config.uri == "mongodb://localhost:27017"
    assert config.database == "ouroboros"
    assert config.max_pool_size == 100
    assert config.min_pool_size == 0
    assert config.max_idle_time_ms is None
    assert config.server_selection_timeout_ms == 30000
    assert config.connect_timeout_ms == 20000
    assert config.socket_timeout_ms is None


def test_config_with_custom_values():
    """Test config creation with custom values."""
    config = MongoDBConfig(
        uri="mongodb+srv://user:pass@cluster.mongodb.net/",
        database="production",
        max_pool_size=50,
        min_pool_size=10,
        max_idle_time_ms=60000,
        server_selection_timeout_ms=10000,
        connect_timeout_ms=5000,
        socket_timeout_ms=30000,
    )

    assert config.uri == "mongodb+srv://user:pass@cluster.mongodb.net/"
    assert config.database == "production"
    assert config.max_pool_size == 50
    assert config.min_pool_size == 10
    assert config.max_idle_time_ms == 60000
    assert config.server_selection_timeout_ms == 10000
    assert config.connect_timeout_ms == 5000
    assert config.socket_timeout_ms == 30000


def test_config_validation_max_pool_size():
    """Test that max_pool_size must be at least 1."""
    with pytest.raises(ValidationError):
        MongoDBConfig(uri="mongodb://localhost:27017", max_pool_size=0)


def test_config_validation_min_pool_size():
    """Test that min_pool_size must be non-negative."""
    with pytest.raises(ValidationError):
        MongoDBConfig(uri="mongodb://localhost:27017", min_pool_size=-1)


def test_config_validation_timeouts():
    """Test that timeout values must be non-negative."""
    with pytest.raises(ValidationError):
        MongoDBConfig(uri="mongodb://localhost:27017", connect_timeout_ms=-1)

    with pytest.raises(ValidationError):
        MongoDBConfig(uri="mongodb://localhost:27017", server_selection_timeout_ms=-1)


def test_config_missing_uri():
    """Test that uri is required."""
    with pytest.raises(ValidationError):
        MongoDBConfig()  # type: ignore[call-arg]
