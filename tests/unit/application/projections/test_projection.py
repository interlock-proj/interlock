"""Tests for the Projection base class."""

import pytest
from pydantic import BaseModel
from ulid import ULID

from interlock.application.projections import Projection
from interlock.domain import Event, Query
from interlock.routing import handles_event, handles_query


# Test event types (bank account domain)
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


class EmailChanged(BaseModel):
    account_id: ULID
    new_email: str


# Test query types
class GetAccountById(Query[dict]):
    account_id: ULID


class GetAccountByEmail(Query[ULID | None]):
    email: str


class GetAccountBalance(Query[int]):
    account_id: ULID


class CountAccounts(Query[int]):
    pass


# Test projection
class AccountDirectoryProjection(Projection):
    """Test projection that tracks bank accounts."""

    def __init__(self):
        super().__init__()
        self.accounts: dict[ULID, dict] = {}
        self.email_index: dict[str, ULID] = {}

    @handles_event
    async def on_account_opened(self, event: AccountOpened) -> None:
        self.accounts[event.account_id] = {
            "id": event.account_id,
            "owner_name": event.owner_name,
            "email": event.email,
            "balance": event.initial_balance,
        }
        self.email_index[event.email] = event.account_id

    @handles_event
    async def on_money_deposited(self, event: MoneyDeposited) -> None:
        if event.account_id in self.accounts:
            self.accounts[event.account_id]["balance"] += event.amount

    @handles_event
    async def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        if event.account_id in self.accounts:
            self.accounts[event.account_id]["balance"] -= event.amount

    @handles_event
    async def on_email_changed(self, event: EmailChanged) -> None:
        if event.account_id in self.accounts:
            old_email = self.accounts[event.account_id]["email"]
            del self.email_index[old_email]
            self.accounts[event.account_id]["email"] = event.new_email
            self.email_index[event.new_email] = event.account_id

    @handles_query
    async def get_account_by_id(self, query: GetAccountById) -> dict:
        return self.accounts[query.account_id]

    @handles_query
    async def get_account_by_email(self, query: GetAccountByEmail) -> ULID | None:
        return self.email_index.get(query.email)

    @handles_query
    async def get_balance(self, query: GetAccountBalance) -> int:
        return self.accounts[query.account_id]["balance"]

    @handles_query
    async def count_accounts(self, query: CountAccounts) -> int:
        return len(self.accounts)


class TestProjectionEventHandling:
    """Tests for event handling in projections."""

    @pytest.mark.asyncio
    async def test_handles_single_event(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        event = Event(
            aggregate_id=account_id,
            data=AccountOpened(
                account_id=account_id,
                owner_name="Alice",
                email="alice@test.com",
                initial_balance=100,
            ),
            sequence_number=1,
        )

        await projection.handle(event)

        assert account_id in projection.accounts
        assert projection.accounts[account_id]["owner_name"] == "Alice"
        assert projection.accounts[account_id]["balance"] == 100

    @pytest.mark.asyncio
    async def test_handles_multiple_events(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        event1 = Event(
            aggregate_id=account_id,
            data=AccountOpened(
                account_id=account_id,
                owner_name="Alice",
                email="alice@test.com",
                initial_balance=100,
            ),
            sequence_number=1,
        )
        event2 = Event(
            aggregate_id=account_id,
            data=MoneyDeposited(account_id=account_id, amount=50),
            sequence_number=2,
        )

        await projection.handle(event1)
        await projection.handle(event2)

        assert projection.accounts[account_id]["balance"] == 150

    @pytest.mark.asyncio
    async def test_builds_secondary_index(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        event = Event(
            aggregate_id=account_id,
            data=AccountOpened(
                account_id=account_id,
                owner_name="Bob",
                email="bob@test.com",
            ),
            sequence_number=1,
        )

        await projection.handle(event)

        assert projection.email_index["bob@test.com"] == account_id

    @pytest.mark.asyncio
    async def test_updates_secondary_index_on_change(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        event1 = Event(
            aggregate_id=account_id,
            data=AccountOpened(
                account_id=account_id,
                owner_name="Bob",
                email="bob@test.com",
            ),
            sequence_number=1,
        )
        event2 = Event(
            aggregate_id=account_id,
            data=EmailChanged(account_id=account_id, new_email="robert@test.com"),
            sequence_number=2,
        )

        await projection.handle(event1)
        await projection.handle(event2)

        assert "bob@test.com" not in projection.email_index
        assert projection.email_index["robert@test.com"] == account_id


class TestProjectionQueryHandling:
    """Tests for query handling in projections."""

    @pytest.mark.asyncio
    async def test_query_by_id(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        # Set up state
        event = Event(
            aggregate_id=account_id,
            data=AccountOpened(
                account_id=account_id,
                owner_name="Charlie",
                email="charlie@test.com",
                initial_balance=500,
            ),
            sequence_number=1,
        )
        await projection.handle(event)

        # Execute query
        result = await projection.query(GetAccountById(account_id=account_id))

        assert result["owner_name"] == "Charlie"
        assert result["email"] == "charlie@test.com"
        assert result["balance"] == 500

    @pytest.mark.asyncio
    async def test_query_by_email(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        # Set up state
        event = Event(
            aggregate_id=account_id,
            data=AccountOpened(
                account_id=account_id,
                owner_name="Diana",
                email="diana@test.com",
            ),
            sequence_number=1,
        )
        await projection.handle(event)

        # Execute query
        result = await projection.query(GetAccountByEmail(email="diana@test.com"))

        assert result == account_id

    @pytest.mark.asyncio
    async def test_query_returns_none_for_missing(self):
        projection = AccountDirectoryProjection()

        result = await projection.query(GetAccountByEmail(email="unknown@test.com"))

        assert result is None

    @pytest.mark.asyncio
    async def test_query_balance(self):
        projection = AccountDirectoryProjection()
        account_id = ULID()

        # Set up state with deposits and withdrawals
        events = [
            Event(
                aggregate_id=account_id,
                data=AccountOpened(
                    account_id=account_id,
                    owner_name="Eve",
                    email="eve@test.com",
                    initial_balance=1000,
                ),
                sequence_number=1,
            ),
            Event(
                aggregate_id=account_id,
                data=MoneyDeposited(account_id=account_id, amount=500),
                sequence_number=2,
            ),
            Event(
                aggregate_id=account_id,
                data=MoneyWithdrawn(account_id=account_id, amount=200),
                sequence_number=3,
            ),
        ]
        for event in events:
            await projection.handle(event)

        # Execute query
        result = await projection.query(GetAccountBalance(account_id=account_id))

        assert result == 1300  # 1000 + 500 - 200

    @pytest.mark.asyncio
    async def test_aggregate_query(self):
        projection = AccountDirectoryProjection()

        # Add multiple accounts
        for i in range(3):
            account_id = ULID()
            event = Event(
                aggregate_id=account_id,
                data=AccountOpened(
                    account_id=account_id,
                    owner_name=f"User{i}",
                    email=f"user{i}@test.com",
                ),
                sequence_number=1,
            )
            await projection.handle(event)

        result = await projection.query(CountAccounts())

        assert result == 3

    @pytest.mark.asyncio
    async def test_query_raises_for_unknown_query_type(self):
        projection = AccountDirectoryProjection()

        class UnknownQuery(Query[str]):
            pass

        with pytest.raises(NotImplementedError):
            await projection.query(UnknownQuery())
