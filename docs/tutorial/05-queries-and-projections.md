# Queries & Projections

In the previous section, we built an event processor that maintains a read model.
Now let's add the ability to **query** that read model with typed queries.

## From Event Processor to Projection

A **Projection** is an event processor that can also serve queries. It combines:

- **Event handling**: Updating state when events occur
- **Query handling**: Returning data in response to queries

Let's upgrade our `AccountBalanceProjection` to serve queries.

## Defining Queries

First, define query types. Queries are like commands but for reading data:

```python
from interlock.domain import Query
from ulid import ULID

class GetAccountBalance(Query[int]):  # (1)!
    account_id: ULID

class GetAccountByEmail(Query[ULID | None]):  # (2)!
    email: str

class CountAccounts(Query[int]):
    pass
```

1. Returns an `int` (the balance)
2. Returns `ULID | None` (the account ID if found)

The type parameter (`Query[int]`) specifies what the query returns, giving you 
type safety and IDE autocomplete.

## Writing Tests First

Let's test our projection's query capabilities using `ProjectionScenario`:

```python
import pytest
from interlock.testing import ProjectionScenario

@pytest.fixture
def projection():
    repository = InMemoryAccountBalanceRepository()
    return AccountBalanceProjection(repository)

async def test_query_returns_balance(projection):
    account_id = ULID()
    
    async with ProjectionScenario(projection) as scenario:
        # Given: money was deposited
        scenario.given(
            MoneyDeposited(account_id=account_id, amount=100)
        )
        
        # When: we query the balance
        balance = await scenario.when(
            GetAccountBalance(account_id=account_id)
        )
        
        # Then: we get the correct balance
        assert balance == 100

async def test_query_returns_zero_for_unknown_account(projection):
    async with ProjectionScenario(projection) as scenario:
        balance = await scenario.when(
            GetAccountBalance(account_id=ULID())
        )
        assert balance == 0
```

## Implementing the Projection

Upgrade from `EventProcessor` to `Projection` and add query handlers:

```python
from interlock.application import Projection
from interlock.routing import handles_event, handles_query

class AccountBalanceProjection(Projection):  # (1)!
    """Projection that maintains account balances and serves queries."""
    
    def __init__(self, repository: AccountBalanceRepository):
        super().__init__()
        self.repository = repository
    
    # Event handlers update state
    @handles_event
    async def on_money_deposited(self, event: MoneyDeposited) -> None:
        current = await self.repository.get_balance(event.account_id)
        await self.repository.set_balance(
            event.account_id, 
            current + event.amount
        )
    
    @handles_event
    async def on_money_withdrawn(self, event: MoneyWithdrawn) -> None:
        current = await self.repository.get_balance(event.account_id)
        await self.repository.set_balance(
            event.account_id, 
            current - event.amount
        )
    
    # Query handlers return data
    @handles_query  # (2)!
    async def get_balance(self, query: GetAccountBalance) -> int:
        return await self.repository.get_balance(query.account_id)
```

1. Changed from `EventProcessor` to `Projection`
2. `@handles_query` marks methods that handle specific query types

## Registering Projections

Register projections with the `ApplicationBuilder`:

```python
from interlock.application import ApplicationBuilder

app = (
    ApplicationBuilder()
    .register_aggregate(BankAccount)
    .register_dependency(AccountBalanceRepository, InMemoryAccountBalanceRepository)
    .register_projection(AccountBalanceProjection)  # (1)!
    .build()
)
```

1. Use `register_projection()` instead of `register_event_processor()`

## Dispatching Queries

Send queries through the application's `query()` method:

```python
async def main():
    async with app:
        account_id = ULID()
        
        # Create account and deposit money
        await app.dispatch(OpenAccount(
            aggregate_id=account_id,
            owner_name="Alice"
        ))
        await app.dispatch(DepositMoney(
            aggregate_id=account_id,
            amount=1000
        ))
        
        # Query the balance
        balance = await app.query(GetAccountBalance(account_id=account_id))
        print(f"Balance: ${balance}")  # Balance: $1000
```

## ID Lookup Pattern

A common use case is looking up an aggregate ID by a natural key (like email).
This lets external systems reference entities by human-readable identifiers.

### Define the Query

```python
class GetAccountIdByEmail(Query[ULID | None]):
    """Find account aggregate ID by email address."""
    email: str
```

### Update the Repository

```python
from abc import ABC, abstractmethod

class AccountLookupRepository(ABC):
    @abstractmethod
    async def save_mapping(self, email: str, account_id: ULID) -> None:
        ...
    
    @abstractmethod
    async def get_account_id(self, email: str) -> ULID | None:
        ...

class InMemoryAccountLookupRepository(AccountLookupRepository):
    def __init__(self):
        self.email_to_id: dict[str, ULID] = {}
    
    async def save_mapping(self, email: str, account_id: ULID) -> None:
        self.email_to_id[email] = account_id
    
    async def get_account_id(self, email: str) -> ULID | None:
        return self.email_to_id.get(email)
```

### Implement the Projection

```python
class AccountLookupProjection(Projection):
    def __init__(self, repository: AccountLookupRepository):
        super().__init__()
        self.repository = repository
    
    @handles_event
    async def on_account_opened(self, event: AccountOpened) -> None:
        await self.repository.save_mapping(event.email, event.account_id)
    
    @handles_query
    async def lookup(self, query: GetAccountIdByEmail) -> ULID | None:
        return await self.repository.get_account_id(query.email)
```

### Use the Lookup

```python
# Find account by email, then dispatch a command
account_id = await app.query(GetAccountIdByEmail(email="alice@example.com"))

if account_id:
    await app.dispatch(DepositMoney(aggregate_id=account_id, amount=500))
else:
    print("Account not found")
```

## Queries vs Commands

| Aspect | Commands | Queries |
|--------|----------|---------|
| **Purpose** | Change state | Read state |
| **Side effects** | Yes (events emitted) | No |
| **Handler** | Aggregate | Projection |
| **Return value** | Optional | Required (typed) |
| **Idempotency** | May need handling | Naturally idempotent |

## Query Middleware

Middleware can intercept queries just like commands. This is useful for:

- **Caching**: Cache expensive query results
- **Authorization**: Check read permissions
- **Logging**: Track query patterns

```python
from interlock.application.middleware import Middleware, Handler
from interlock.routing import intercepts

class QueryLoggingMiddleware(Middleware):
    @intercepts
    async def log_query(self, query: Query, next: Handler):
        print(f"Query: {type(query).__name__}")
        result = await next(query)
        print(f"Result: {result}")
        return result
```

## Summary

| Concept | Description |
|---------|-------------|
| `Query[T]` | Base class for queries with typed responses |
| `Projection` | Event processor that also serves queries |
| `@handles_query` | Decorator for query handler methods |
| `app.query()` | Dispatch a query and get the result |
| `ProjectionScenario` | Test utility for projections |

## Next Steps

Learn how to add cross-cutting concerns with [Middleware](06-middleware.md).

