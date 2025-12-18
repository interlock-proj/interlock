"""Tests for ProjectionScenario testing utility."""

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.application.projections import Projection
from interlock.domain import Query
from interlock.routing import handles_event, handles_query
from interlock.testing import ProjectionScenario


# Test events (bank account domain)
class AccountOpened(BaseModel):
    account_id: ULID
    owner_name: str
    email: str
    initial_balance: int = 0


class MoneyDeposited(BaseModel):
    account_id: ULID
    amount: int


class MoneyWithdrawn(BaseModel):
    account_id: ULID
    amount: int


# Test queries
class GetAccountById(Query[dict]):
    account_id: ULID


class GetAccountBalance(Query[int]):
    account_id: ULID


class CountAccounts(Query[int]):
    pass


class GetTotalBalance(Query[int]):
    """Sum of all account balances."""

    pass


# Test projection
class AccountSummaryProjection(Projection):
    def __init__(self):
        super().__init__()
        self.accounts: dict[ULID, dict] = {}

    @handles_event
    async def on_account_opened(self, event: AccountOpened) -> None:
        self.accounts[event.account_id] = {
            "id": event.account_id,
            "owner_name": event.owner_name,
            "email": event.email,
            "balance": event.initial_balance,
        }

    @handles_event
    async def on_money_deposited(self, event: MoneyDeposited) -> None:
        if event.account_id in self.accounts:
            self.accounts[event.account_id]["balance"] += event.amount

    @handles_event
    async def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        if event.account_id in self.accounts:
            self.accounts[event.account_id]["balance"] -= event.amount

    @handles_query
    async def get_account_by_id(self, query: GetAccountById) -> dict:
        return self.accounts[query.account_id]

    @handles_query
    async def get_balance(self, query: GetAccountBalance) -> int:
        return self.accounts[query.account_id]["balance"]

    @handles_query
    async def count_accounts(self, query: CountAccounts) -> int:
        return len(self.accounts)

    @handles_query
    async def get_total_balance(self, query: GetTotalBalance) -> int:
        return sum(acc["balance"] for acc in self.accounts.values())


class TestProjectionScenarioEventHandling:
    """Tests for event handling in ProjectionScenario."""

    @pytest.mark.asyncio
    async def test_given_processes_events(self):
        projection = AccountSummaryProjection()
        account_id = ULID()

        async with ProjectionScenario(projection) as scenario:
            scenario.given(
                AccountOpened(
                    account_id=account_id,
                    owner_name="Alice",
                    email="alice@test.com",
                    initial_balance=1000,
                )
            )
            scenario.should_have_state(lambda p: len(p.accounts) == 1)

    @pytest.mark.asyncio
    async def test_given_multiple_events(self):
        projection = AccountSummaryProjection()
        id1 = ULID()
        id2 = ULID()

        async with ProjectionScenario(projection) as scenario:
            scenario.given(
                AccountOpened(
                    account_id=id1,
                    owner_name="Alice",
                    email="alice@test.com",
                    initial_balance=500,
                ),
                AccountOpened(
                    account_id=id2,
                    owner_name="Bob",
                    email="bob@test.com",
                    initial_balance=1500,
                ),
            )
            scenario.should_have_state(lambda p: len(p.accounts) == 2)


class TestProjectionScenarioQueryHandling:
    """Tests for query handling in ProjectionScenario."""

    @pytest.mark.asyncio
    async def test_when_executes_query(self):
        projection = AccountSummaryProjection()
        account_id = ULID()

        async with ProjectionScenario(projection) as scenario:
            scenario.given(
                AccountOpened(
                    account_id=account_id,
                    owner_name="Charlie",
                    email="charlie@test.com",
                    initial_balance=2500,
                )
            )
            result = await scenario.when(GetAccountById(account_id=account_id))

            assert result["owner_name"] == "Charlie"
            assert result["balance"] == 2500

    @pytest.mark.asyncio
    async def test_when_returns_typed_result(self):
        projection = AccountSummaryProjection()

        async with ProjectionScenario(projection) as scenario:
            scenario.given(
                AccountOpened(
                    account_id=ULID(),
                    owner_name="A",
                    email="a@test.com",
                    initial_balance=100,
                ),
                AccountOpened(
                    account_id=ULID(),
                    owner_name="B",
                    email="b@test.com",
                    initial_balance=200,
                ),
            )
            count: int = await scenario.when(CountAccounts())

            assert count == 2

    @pytest.mark.asyncio
    async def test_when_multiple_queries(self):
        projection = AccountSummaryProjection()
        id1, id2 = ULID(), ULID()

        async with ProjectionScenario(projection) as scenario:
            scenario.given(
                AccountOpened(
                    account_id=id1,
                    owner_name="A",
                    email="a@test.com",
                    initial_balance=1000,
                ),
                AccountOpened(
                    account_id=id2,
                    owner_name="B",
                    email="b@test.com",
                    initial_balance=3000,
                ),
            )

            count = await scenario.when(CountAccounts())
            total = await scenario.when(GetTotalBalance())

            assert count == 2
            assert total == 4000


class TestProjectionScenarioStateAssertions:
    """Tests for state assertions in ProjectionScenario."""

    @pytest.mark.asyncio
    async def test_should_have_state_passes(self):
        projection = AccountSummaryProjection()

        async with ProjectionScenario(projection) as scenario:
            scenario.given(
                AccountOpened(
                    account_id=ULID(),
                    owner_name="Test",
                    email="test@test.com",
                    initial_balance=999,
                )
            )
            scenario.should_have_state(
                lambda p: "Test"
                in [acc["owner_name"] for acc in p.accounts.values()]
            )

    @pytest.mark.asyncio
    async def test_should_have_state_fails(self):
        projection = AccountSummaryProjection()

        with pytest.raises(AssertionError):
            async with ProjectionScenario(projection) as scenario:
                scenario.given(
                    AccountOpened(
                        account_id=ULID(),
                        owner_name="Test",
                        email="test@test.com",
                    )
                )
                scenario.should_have_state(lambda p: len(p.accounts) == 5)


class TestProjectionScenarioCombined:
    """Tests combining events, queries, and state assertions."""

    @pytest.mark.asyncio
    async def test_full_scenario(self):
        projection = AccountSummaryProjection()
        account_id = ULID()

        async with ProjectionScenario(projection) as scenario:
            # Given: Account is opened with initial balance
            scenario.given(
                AccountOpened(
                    account_id=account_id,
                    owner_name="Diana",
                    email="diana@test.com",
                    initial_balance=1000,
                )
            )

            # When: Query for the balance
            balance = await scenario.when(GetAccountBalance(account_id=account_id))
            assert balance == 1000

            # Given more events (deposit and withdrawal)
            scenario.given(
                MoneyDeposited(account_id=account_id, amount=500),
                MoneyWithdrawn(account_id=account_id, amount=200),
            )

            # When: Query balance again
            updated_balance = await scenario.when(
                GetAccountBalance(account_id=account_id)
            )
            assert updated_balance == 1300  # 1000 + 500 - 200

            # Then: Final state assertion
            scenario.should_have_state(
                lambda p: p.accounts[account_id]["balance"] == 1300
            )
