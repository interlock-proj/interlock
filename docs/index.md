# Interlock

**CQRS and Event Sourcing made easy in Python.**

---

## What is Interlock?

Interlock is a Python framework for building applications using **Command Query Responsibility Segregation (CQRS)** and **Event Sourcing** patterns. It provides:

- **Aggregates**: Domain objects that encapsulate business logic and emit events
- **Commands**: Explicit intent-driven messages that trigger state changes
- **Events**: Immutable records of what happened in your system
- **Event Processors**: React to events to build read models or trigger side effects
- **Middleware**: Cross-cutting concerns like logging, idempotency, and concurrency

## Installation

```bash
pip install interlock
```

## Quick Example

```python
from pydantic import BaseModel
from ulid import ULID

from interlock.application import ApplicationBuilder
from interlock.domain import Aggregate, Command
from interlock.routing import handles_command, applies_event


# 1. Define a command (intent to change state)
class DepositMoney(Command):
    amount: int


# 2. Define event data (what happened)
class MoneyDeposited(BaseModel):
    amount: int


# 3. Define an aggregate (business logic + state)
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


# 4. Build and run the application
async def main():
    app = (
        ApplicationBuilder()
        .register_aggregate(BankAccount)
        .build()
    )

    async with app:  # Manages startup/shutdown lifecycle
        account_id = ULID()
        await app.dispatch(DepositMoney(
            aggregate_id=account_id,
            amount=100
        ))
        print(f"Deposited $100 to account {account_id}")


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
