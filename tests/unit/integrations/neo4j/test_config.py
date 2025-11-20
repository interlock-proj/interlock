"""Unit tests for Neo4jConfig."""

import pytest
from pydantic import ValidationError

from interlock.integrations.neo4j import Neo4jConfig


def test_config_minimal():
    """Test creating config with minimal required fields."""
    config = Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
    )

    assert config.uri == "bolt://localhost:7687"
    assert config.username == "neo4j"
    assert config.password == "password"
    assert config.database == "neo4j"  # Default
    assert config.max_connection_pool_size == 50  # Default


def test_config_with_all_fields():
    """Test creating config with all fields specified."""
    config = Neo4jConfig(
        uri="neo4j://localhost:7687",
        username="admin",
        password="secret",
        database="mydb",
        max_connection_pool_size=100,
        connection_timeout=60.0,
        max_transaction_retry_time=45.0,
        encrypted=True,
        trust="TRUST_ALL_CERTIFICATES",
    )

    assert config.uri == "neo4j://localhost:7687"
    assert config.username == "admin"
    assert config.database == "mydb"
    assert config.max_connection_pool_size == 100
    assert config.connection_timeout == 60.0
    assert config.encrypted is True


def test_config_missing_required_fields():
    """Test that missing required fields raise validation error."""
    with pytest.raises(ValidationError):
        Neo4jConfig(uri="bolt://localhost:7687")  # Missing username and password


def test_config_invalid_pool_size():
    """Test that invalid pool size raises validation error."""
    with pytest.raises(ValidationError):
        Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="password",
            max_connection_pool_size=0,  # Must be >= 1
        )


def test_config_negative_timeout():
    """Test that negative timeout raises validation error."""
    with pytest.raises(ValidationError):
        Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="password",
            connection_timeout=-1.0,  # Must be >= 0
        )


def test_config_serialization():
    """Test config can be serialized to dict."""
    config = Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="password",
    )

    config_dict = config.model_dump()
    assert config_dict["uri"] == "bolt://localhost:7687"
    assert config_dict["username"] == "neo4j"
    assert config_dict["password"] == "password"


def test_config_from_dict():
    """Test creating config from dictionary."""
    config_dict = {
        "uri": "bolt://localhost:7687",
        "username": "neo4j",
        "password": "password",
        "database": "testdb",
    }

    config = Neo4jConfig(**config_dict)
    assert config.uri == "bolt://localhost:7687"
    assert config.database == "testdb"
