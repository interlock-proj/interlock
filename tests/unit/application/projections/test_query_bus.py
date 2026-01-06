"""Tests for QueryBus and query routing infrastructure."""

from uuid import UUID, uuid4

import pytest

from interlock.application.middleware import Handler, Middleware
from interlock.application.projections import (
    DelegateToProjection,
    Projection,
    ProjectionRegistry,
    QueryBus,
    QueryToProjectionMap,
)
from interlock.domain import Query
from interlock.routing import handles_query, intercepts


# Test queries (bank account domain)
class GetAccountById(Query[dict]):
    account_id: UUID


class GetAccountBalance(Query[int]):
    account_id: UUID


class GetAccountByEmail(Query[UUID | None]):
    email: str


class CountAccounts(Query[int]):
    pass


# Test projection
class AccountProjection(Projection):
    def __init__(self):
        super().__init__()
        self.accounts: dict[UUID, dict] = {}
        self.email_index: dict[str, UUID] = {}

    def add_account(self, account_id: UUID, owner_name: str, email: str, balance: int = 0) -> None:
        """Helper to add accounts for testing."""
        self.accounts[account_id] = {
            "id": account_id,
            "owner_name": owner_name,
            "email": email,
            "balance": balance,
        }
        self.email_index[email] = account_id

    @handles_query
    async def get_account_by_id(self, query: GetAccountById) -> dict:
        return self.accounts[query.account_id]

    @handles_query
    async def get_balance(self, query: GetAccountBalance) -> int:
        return self.accounts[query.account_id]["balance"]

    @handles_query
    async def get_account_by_email(self, query: GetAccountByEmail) -> UUID | None:
        return self.email_index.get(query.email)

    @handles_query
    async def count_accounts(self, query: CountAccounts) -> int:
        return len(self.accounts)


class TestQueryToProjectionMap:
    """Tests for QueryToProjectionMap."""

    def test_maps_query_to_projection(self):
        query_map = QueryToProjectionMap.from_projections([AccountProjection])

        assert query_map.get(GetAccountById) == AccountProjection
        assert query_map.get(GetAccountBalance) == AccountProjection
        assert query_map.get(GetAccountByEmail) == AccountProjection
        assert query_map.get(CountAccounts) == AccountProjection

    def test_raises_for_unknown_query(self):
        query_map = QueryToProjectionMap()

        with pytest.raises(KeyError):
            query_map.get(GetAccountById)

    def test_from_multiple_projections(self):
        class GetTransactionHistory(Query[list]):
            account_id: UUID

        class TransactionProjection(Projection):
            @handles_query
            async def get_history(self, query: GetTransactionHistory) -> list:
                return []

        query_map = QueryToProjectionMap.from_projections(
            [AccountProjection, TransactionProjection]
        )

        assert query_map.get(GetAccountById) == AccountProjection
        assert query_map.get(GetTransactionHistory) == TransactionProjection


class TestProjectionRegistry:
    """Tests for ProjectionRegistry."""

    def test_registers_and_retrieves_projection(self):
        projection = AccountProjection()
        registry = ProjectionRegistry.from_projections([projection])

        assert registry.get(AccountProjection) is projection

    def test_raises_for_unregistered_projection(self):
        registry = ProjectionRegistry()

        with pytest.raises(KeyError):
            registry.get(AccountProjection)


class TestDelegateToProjection:
    """Tests for DelegateToProjection root handler."""

    @pytest.mark.asyncio
    async def test_delegates_to_correct_projection(self):
        # Set up projection with data
        projection = AccountProjection()
        account_id = uuid4()
        projection.add_account(account_id, "Alice", "alice@test.com", balance=1000)

        # Set up routing
        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        # Execute query
        result = await delegate.handle(GetAccountById(account_id=account_id))

        assert result["owner_name"] == "Alice"
        assert result["balance"] == 1000

    @pytest.mark.asyncio
    async def test_handles_different_query_types(self):
        projection = AccountProjection()
        projection.add_account(uuid4(), "Alice", "alice@test.com", balance=500)
        projection.add_account(uuid4(), "Bob", "bob@test.com", balance=1500)

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        count = await delegate.handle(CountAccounts())

        assert count == 2

    @pytest.mark.asyncio
    async def test_handles_balance_query(self):
        projection = AccountProjection()
        account_id = uuid4()
        projection.add_account(account_id, "Charlie", "charlie@test.com", balance=2500)

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        balance = await delegate.handle(GetAccountBalance(account_id=account_id))

        assert balance == 2500


class TestQueryBus:
    """Tests for QueryBus."""

    @pytest.mark.asyncio
    async def test_dispatches_without_middleware(self):
        projection = AccountProjection()
        account_id = uuid4()
        projection.add_account(account_id, "Alice", "alice@test.com", balance=1000)

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        bus = QueryBus(delegate, middleware=[])

        result = await bus.dispatch(GetAccountById(account_id=account_id))

        assert result["owner_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_dispatches_with_middleware(self):
        calls: list[str] = []

        class TrackingMiddleware(Middleware):
            @intercepts
            async def track_query(self, query: Query, next: Handler):
                calls.append("before")
                result = await next(query)
                calls.append("after")
                return result

        projection = AccountProjection()
        account_id = uuid4()
        projection.add_account(account_id, "Bob", "bob@test.com", balance=500)

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        bus = QueryBus(delegate, middleware=[TrackingMiddleware()])

        result = await bus.dispatch(GetAccountById(account_id=account_id))

        assert result["owner_name"] == "Bob"
        assert calls == ["before", "after"]

    @pytest.mark.asyncio
    async def test_middleware_can_modify_result(self):
        class TransformMiddleware(Middleware):
            @intercepts
            async def transform(self, query: GetAccountById, next: Handler):
                result = await next(query)
                result["transformed"] = True
                return result

        projection = AccountProjection()
        account_id = uuid4()
        projection.add_account(account_id, "Charlie", "charlie@test.com")

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        bus = QueryBus(delegate, middleware=[TransformMiddleware()])

        result = await bus.dispatch(GetAccountById(account_id=account_id))

        assert result["transformed"] is True

    @pytest.mark.asyncio
    async def test_middleware_chain_order(self):
        calls: list[str] = []

        class FirstMiddleware(Middleware):
            @intercepts
            async def first(self, query: Query, next: Handler):
                calls.append("first-before")
                result = await next(query)
                calls.append("first-after")
                return result

        class SecondMiddleware(Middleware):
            @intercepts
            async def second(self, query: Query, next: Handler):
                calls.append("second-before")
                result = await next(query)
                calls.append("second-after")
                return result

        projection = AccountProjection()
        projection.add_account(uuid4(), "Test", "test@test.com")

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        # First registered runs first (outermost)
        bus = QueryBus(delegate, middleware=[FirstMiddleware(), SecondMiddleware()])

        await bus.dispatch(CountAccounts())

        assert calls == [
            "first-before",
            "second-before",
            "second-after",
            "first-after",
        ]

    @pytest.mark.asyncio
    async def test_email_lookup_query(self):
        projection = AccountProjection()
        account_id = uuid4()
        projection.add_account(account_id, "Diana", "diana@test.com", balance=750)

        query_map = QueryToProjectionMap.from_projections([AccountProjection])
        registry = ProjectionRegistry.from_projections([projection])
        delegate = DelegateToProjection(query_map, registry)

        bus = QueryBus(delegate, middleware=[])

        # Find by email
        found_id = await bus.dispatch(GetAccountByEmail(email="diana@test.com"))
        assert found_id == account_id

        # Not found returns None
        missing = await bus.dispatch(GetAccountByEmail(email="unknown@test.com"))
        assert missing is None
