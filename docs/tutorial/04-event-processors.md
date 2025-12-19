# Event Processors

Event processors react to events and perform side effects.
Use them to build read models (projections), send notifications, or trigger workflows.

## What is an Event Processor?

In CQRS, the **read side** is separate from the write side.
Event processors subscribe to events and use them to:

- Build **read-optimized projections** of the data
- Send **notifications** to users
- Trigger **external API calls** to update other systems
- Start **sagas/workflows** for complex business processes

## Building a Projection

Let's build a projection that tracks account balances for quick lookups.
First, we'll define a repository interface and an in-memory implementation:

```python
from abc import ABC, abstractmethod
from uuid import UUID, uuid4

class AccountBalanceRepository(ABC):
    """Repository for account balance projections."""
    
    @abstractmethod
    def get_balance(self, account_id: UUID) -> int:
        """Get the current balance for an account."""
        ...
    
    @abstractmethod
    def set_balance(self, account_id: UUID, balance: int) -> None:
        """Set the balance for an account."""
        ...

class InMemoryAccountBalanceRepository(AccountBalanceRepository):
    """In-memory implementation for testing and development."""
    
    def __init__(self):
        self._balances: dict[UUID, int] = {}
    
    def get_balance(self, account_id: UUID) -> int:
        return self._balances.get(account_id, 0)
    
    def set_balance(self, account_id: UUID, balance: int) -> None:
        self._balances[account_id] = balance
```

This pattern lets you swap implementations—use `InMemoryAccountBalanceRepository` for 
tests and development, then switch to `PostgresAccountBalanceRepository` in production.

## Writing Tests First

Following TDD, let's write tests for our projection using `app.processor_scenario()`.
First, we'll create a pytest fixture that builds the application with our test dependencies:

```python
import pytest
from interlock.application import ApplicationBuilder

@pytest.fixture
def app():
    return (
        ApplicationBuilder()
        .register_dependency(AccountBalanceRepository, InMemoryAccountBalanceRepository)
        .register_event_processor(AccountBalanceProjection)
        .build()
    )
```

Now our tests are clean and focused on behavior:

```python
async def test_tracks_balance_after_deposit(app):
    async with app.processor_scenario(AccountBalanceProjection) as scenario:  # (1)!
        scenario \
            .given(MoneyDeposited(amount=100)) \
            .should_have_state(
                lambda p: p.repository.get_balance(scenario.aggregate_id) == 100
            )

async def test_accumulates_multiple_deposits(app):
    async with app.processor_scenario(AccountBalanceProjection) as scenario:
        scenario \
            .given(
                MoneyDeposited(amount=100),
                MoneyDeposited(amount=50),
            ) \
            .should_have_state(
                lambda p: p.repository.get_balance(scenario.aggregate_id) == 150
            )
```

1. The processor is resolved from the DI container with all dependencies injected

## Implementing the Projection

Now let's implement the processor to make our tests pass:

```python
from interlock.application.events import EventProcessor
from interlock.domain import Event
from interlock.routing import handles_event

class AccountBalanceProjection(EventProcessor):
    """Projection that maintains account balances for quick lookups."""
    
    def __init__(self, repository: AccountBalanceRepository):
        self.repository = repository
    
    @handles_event
    async def on_money_deposited(self, event: Event[MoneyDeposited]) -> None:  # (1)!
        current = self.repository.get_balance(event.aggregate_id)  # (2)!
        self.repository.set_balance(
            event.aggregate_id, 
            current + event.data.amount  # (3)!
        )
```

1. Use `Event[MoneyDeposited]` to receive the full event wrapper with metadata
2. Access `aggregate_id` from the event wrapper—no need to duplicate it in the payload
3. The actual event data is in `event.data`

## Registering Event Processors

Register processors imperatively with the `ApplicationBuilder`:

```python
from interlock.application import ApplicationBuilder

app = (
    ApplicationBuilder()
    .register_aggregate(BankAccount)
    .register_dependency(
        AccountBalanceRepository,  # (1)!
        InMemoryAccountBalanceRepository
    )
    .register_event_processor(AccountBalanceProjection)
    .build()
)
```

1. Register the interface with its concrete implementation—swap to `PostgresAccountBalanceRepository` in production

## Projections vs Side Effects

There are two main patterns for event processors:

| Pattern | Purpose | Example |
|---------|---------|---------|
| **Projection** | Build read models | `AccountBalanceProjection` |
| **Side Effect** | External actions | `EmailNotificationProcessor` |

For side effects, you typically inject services:

```python
class EmailNotificationProcessor(EventProcessor):
    def __init__(self, email_service: EmailService):
        self.email_service = email_service
    
    @handles_event
    async def on_money_deposited(self, event: MoneyDeposited) -> None:
        await self.email_service.send(
            subject="Deposit Received",
            body=f"You deposited ${event.amount}"
        )
```

## Next Steps

Learn how to serve typed queries from your projections in [Queries & Projections](05-queries-and-projections.md).
