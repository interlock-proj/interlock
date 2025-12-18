# Interlock

**CQRS and Event Sourcing made easy in Python.**

---

## What is Interlock?

Interlock is a Python framework for building applications using **Command Query Responsibility Segregation (CQRS)** and **Event Sourcing** patterns. It provides:

- **Aggregates**: Domain objects that encapsulate business logic and emit events
- **Commands**: Explicit intent-driven messages that trigger state changes
- **Queries**: Typed messages that request data from read models
- **Events**: Immutable records of what happened in your system
- **Projections**: Build read models from events and serve queries
- **Middleware**: Cross-cutting concerns like logging, caching, and authorization

## Installation

```bash
pip install interlock
```

## Quick Example

```python
from pydantic import BaseModel
from ulid import ULID

from interlock.application import ApplicationBuilder, Projection
from interlock.domain import Aggregate, Command, Query
from interlock.routing import handles_command, applies_event, handles_event, handles_query


# 1. Define commands (intent to change) and queries (request data)
class DepositMoney(Command[None]):
    amount: int

class GetBalance(Query[int]):
    pass


# 2. Define event data (what happened)
class MoneyDeposited(BaseModel):
    amount: int


# 3. Define an aggregate (write side - business logic)
class BankAccount(Aggregate):
    balance: int = 0

    @handles_command
    async def deposit(self, command: DepositMoney) -> None:
        if command.amount <= 0:
            raise ValueError("Amount must be positive")
        self.emit(MoneyDeposited(amount=command.amount))

    @applies_event
    def apply_deposit(self, event: MoneyDeposited) -> None:
        self.balance += event.amount


# 4. Define a projection (read side - query handling)
class BalanceProjection(Projection):
    def __init__(self):
        super().__init__()
        self.balances: dict[ULID, int] = {}

    @handles_event
    async def on_deposit(self, event: MoneyDeposited, aggregate_id: ULID) -> None:
        self.balances[aggregate_id] = self.balances.get(aggregate_id, 0) + event.amount

    @handles_query
    async def get_balance(self, query: GetBalance, aggregate_id: ULID) -> int:
        return self.balances.get(aggregate_id, 0)


# 5. Build and run the application
async def main():
    app = (
        ApplicationBuilder()
        .register_aggregate(BankAccount)
        .register_projection(BalanceProjection)
        .build()
    )

    async with app:
        account_id = ULID()
        
        # Write: dispatch commands
        await app.dispatch(DepositMoney(aggregate_id=account_id, amount=100))
        
        # Read: dispatch queries
        balance = await app.query(GetBalance(account_id=account_id))
        print(f"Balance: ${balance}")  # Balance: $100


# Run with: asyncio.run(main())
```

---

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __Quick to set up__

    ---

    Install with pip and get started in minutes with intuitive APIs

    [:octicons-arrow-right-24: Getting started](getting-started/index.md)

-   :material-book-open-variant:{ .lg .middle } __Learn step by step__

    ---

    Follow our FastAPI-style tutorial to build your first event-sourced app

    [:octicons-arrow-right-24: Tutorial](tutorial/index.md)

-   :material-lightbulb:{ .lg .middle } __Understand the concepts__

    ---

    Deep dive into CQRS, Event Sourcing, and domain-driven design

    [:octicons-arrow-right-24: Concepts](concepts/index.md)

-   :material-api:{ .lg .middle } __API Reference__

    ---

    Auto-generated documentation for all modules and classes

    [:octicons-arrow-right-24: Reference](reference/index.md)

</div>
