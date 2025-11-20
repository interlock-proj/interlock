"""Configuration models for Neo4j integration.

This module provides Pydantic models for configuring Neo4j connections
and integration behavior.
"""

from pydantic import BaseModel, Field


class Neo4jConfig(BaseModel):
    """Configuration for Neo4j database connection.

    Attributes:
        uri: Neo4j connection URI (e.g., "bolt://localhost:7687" or "neo4j://localhost:7687")
        username: Username for authentication
        password: Password for authentication
        database: Database name to use (default: "neo4j")
        max_connection_pool_size: Maximum number of connections in the pool
        connection_timeout: Connection timeout in seconds
        max_transaction_retry_time: Maximum time to retry failed transactions in seconds

    Examples:
        >>> config = Neo4jConfig(
        ...     uri="bolt://localhost:7687",
        ...     username="neo4j",
        ...     password="password"
        ... )
    """

    uri: str = Field(
        ...,
        description="Neo4j connection URI (e.g., bolt://localhost:7687)",
        examples=["bolt://localhost:7687", "neo4j://localhost:7687"],
    )
    username: str = Field(
        ...,
        description="Username for Neo4j authentication",
    )
    password: str = Field(
        ...,
        description="Password for Neo4j authentication",
    )
    database: str = Field(
        default="neo4j",
        description="Database name to connect to",
    )
    max_connection_pool_size: int = Field(
        default=50,
        description="Maximum number of connections in the connection pool",
        ge=1,
    )
    connection_timeout: float = Field(
        default=30.0,
        description="Connection timeout in seconds",
        ge=0,
    )
    max_transaction_retry_time: float = Field(
        default=30.0,
        description="Maximum time to retry failed transactions in seconds",
        ge=0,
    )
    encrypted: bool = Field(
        default=False,
        description="Whether to use encrypted connection",
    )
    trust: str | None = Field(
        default=None,
        description=(
            "Trust strategy (e.g., TRUST_ALL_CERTIFICATES, TRUST_SYSTEM_CA_SIGNED_CERTIFICATES)"
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "uri": "bolt://localhost:7687",
                    "username": "neo4j",
                    "password": "password",
                    "database": "neo4j",
                    "max_connection_pool_size": 50,
                }
            ]
        }
    }
