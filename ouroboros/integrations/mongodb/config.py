"""Configuration models for MongoDB integration.

This module provides Pydantic models for configuring MongoDB connections
and integration behavior.
"""

from pydantic import BaseModel, Field


class MongoDBConfig(BaseModel):
    """Configuration for MongoDB database connection.

    Attributes:
        uri: MongoDB connection URI (e.g., "mongodb://localhost:27017" or MongoDB Atlas URI)
        database: Database name to use (default: "ouroboros")
        max_pool_size: Maximum number of connections in the pool
        min_pool_size: Minimum number of connections in the pool
        max_idle_time_ms: Maximum idle time for connections in milliseconds
        server_selection_timeout_ms: Server selection timeout in milliseconds
        connect_timeout_ms: Connection timeout in milliseconds
        socket_timeout_ms: Socket timeout in milliseconds

    Examples:
        >>> config = MongoDBConfig(
        ...     uri="mongodb://localhost:27017",
        ...     database="myapp"
        ... )
        >>> # MongoDB Atlas
        >>> config = MongoDBConfig(
        ...     uri="mongodb+srv://user:pass@cluster.mongodb.net/",
        ...     database="production"
        ... )
    """

    uri: str = Field(
        ...,
        description="MongoDB connection URI (e.g., mongodb://localhost:27017)",
        examples=[
            "mongodb://localhost:27017",
            "mongodb+srv://user:pass@cluster.mongodb.net/",
        ],
    )
    database: str = Field(
        default="ouroboros",
        description="Database name to connect to",
    )
    max_pool_size: int = Field(
        default=100,
        description="Maximum number of connections in the connection pool",
        ge=1,
    )
    min_pool_size: int = Field(
        default=0,
        description="Minimum number of connections in the connection pool",
        ge=0,
    )
    max_idle_time_ms: int | None = Field(
        default=None,
        description="Maximum idle time for pooled connections in milliseconds",
        ge=0,
    )
    server_selection_timeout_ms: int = Field(
        default=30000,
        description="Server selection timeout in milliseconds",
        ge=0,
    )
    connect_timeout_ms: int = Field(
        default=20000,
        description="Connection timeout in milliseconds",
        ge=0,
    )
    socket_timeout_ms: int | None = Field(
        default=None,
        description="Socket timeout in milliseconds (None for no timeout)",
        ge=0,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "uri": "mongodb://localhost:27017",
                    "database": "ouroboros",
                    "max_pool_size": 100,
                },
                {
                    "uri": "mongodb+srv://user:pass@cluster.mongodb.net/",
                    "database": "production",
                    "max_pool_size": 50,
                    "min_pool_size": 10,
                },
            ]
        }
    }
