"""Pytest fixtures for MongoDB integration tests."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Literal

import pytest
import pytest_asyncio

from interlock.integrations.mongodb import MongoConfiguration

# Assumes a MongoDB container is running locally on port 27017
LOCAL_MONGO_URI = "mongodb://localhost:27017"


@asynccontextmanager
async def create_config(
    request: pytest.FixtureRequest,
    prefix: str = "test",
    snapshot_mode: Literal["single", "multiple"] = "single",
) -> AsyncIterator[MongoConfiguration]:
    """Create a MongoConfiguration with cleanup."""
    db_name = f"{prefix}_{request.node.name}"[:63]
    config = MongoConfiguration(
        uri=LOCAL_MONGO_URI,
        database=db_name,
        snapshot_mode=snapshot_mode,
    )
    await config.client.drop_database(config.database)
    try:
        yield config
    finally:
        if "client" in config.__dict__:
            await config.client.close()


@pytest_asyncio.fixture
async def mongo_config(request: pytest.FixtureRequest) -> AsyncIterator[MongoConfiguration]:
    """Create a MongoConfiguration pointing to local MongoDB."""
    async with create_config(request) as config:
        yield config


@pytest_asyncio.fixture
async def mongo_config_single_snapshot(
    request: pytest.FixtureRequest,
) -> AsyncIterator[MongoConfiguration]:
    """Create a MongoConfiguration with single snapshot mode."""
    async with create_config(request, prefix="test_s", snapshot_mode="single") as config:
        yield config


@pytest_asyncio.fixture
async def mongo_config_multiple_snapshot(
    request: pytest.FixtureRequest,
) -> AsyncIterator[MongoConfiguration]:
    """Create a MongoConfiguration with multiple snapshot mode."""
    async with create_config(request, prefix="test_m", snapshot_mode="multiple") as config:
        yield config
