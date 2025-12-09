"""Tests for aggregate cache backends and strategies."""

import pytest
from ulid import ULID

from interlock.application.aggregates.repository.cache import (
    AggregateCacheBackend,
    AlwaysCache,
    CacheStrategy,
    NeverCache,
    NullAggregateCacheBackend,
)
from tests.fixtures.test_app.aggregates.bank_account import BankAccount


@pytest.mark.asyncio
async def test_null_cache_get_returns_none():
    """Verify NullAggregateCacheBackend.get_aggregate always returns None."""
    cache = NullAggregateCacheBackend()
    result = await cache.get_aggregate(ULID())
    assert result is None


@pytest.mark.asyncio
async def test_null_cache_set_does_nothing():
    """Verify NullAggregateCacheBackend.set_aggregate is a no-op."""
    cache = NullAggregateCacheBackend()
    account = BankAccount()
    await cache.set_aggregate(account)
    # Verify it's still not cached
    assert await cache.get_aggregate(account.id) is None


@pytest.mark.asyncio
async def test_null_cache_remove_does_nothing():
    """Verify NullAggregateCacheBackend.remove_aggregate is a no-op."""
    cache = NullAggregateCacheBackend()
    await cache.remove_aggregate(ULID())
    # No error should occur


def test_always_cache_strategy():
    """Verify AlwaysCache returns True for any aggregate."""
    strategy = AlwaysCache()
    account = BankAccount()
    assert strategy.should_cache(account) is True


def test_never_cache_strategy():
    """Verify NeverCache returns False for any aggregate."""
    strategy = NeverCache()
    account = BankAccount()
    assert strategy.should_cache(account) is False


def test_cache_strategy_factory_methods():
    """Verify cache strategy factory methods work correctly."""
    strategy = CacheStrategy.never()
    assert isinstance(strategy, NeverCache)
    account = BankAccount()
    assert strategy.should_cache(account) is False


@pytest.mark.asyncio
async def test_aggregate_cache_backend_factory_methods():
    """Verify cache backend factory methods work correctly."""
    backend = AggregateCacheBackend.null()
    assert isinstance(backend, NullAggregateCacheBackend)
    assert await backend.get_aggregate(ULID()) is None
