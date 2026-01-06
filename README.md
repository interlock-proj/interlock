# Interlock

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./docs/assets/images/logo-light.svg">
  <img alt="Interlock Logo" src="./docs/assets/images/logo-dark.svg" width="280" align="right">
</picture>

> CQRS and Event Sourcing made easy in Python 🔗

[![CI](https://github.com/interlock-proj/interlock/actions/workflows/ci.yml/badge.svg)](https://github.com/interlock-proj/interlock/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/interlock-proj/interlock/branch/main/graph/badge.svg)](https://codecov.io/gh/interlock-proj/interlock)
[![PyPI Version](https://badge.fury.io/py/interlock.svg)](https://pypi.org/project/interlock/)
[![Python Versions](https://img.shields.io/pypi/pyversions/interlock.svg)](https://pypi.org/project/interlock/)
[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

**Interlock lets you build event-sourced applications with minimal boilerplate.** Define your domain logic declaratively with aggregates, commands, and events. The framework handles the infrastructure—event storage, state reconstruction, CQRS routing, and more—so you can focus on what matters: your business logic.

#### Highlights

- Define [Aggregates](https://interlock-proj.github.io/interlock/concepts/aggregates/) that emit events and enforce business rules
- Use [Commands](https://interlock-proj.github.io/interlock/concepts/commands/) and [Queries](https://interlock-proj.github.io/interlock/concepts/queries/) for explicit, type-safe messaging
- Build read models with [Projections](https://interlock-proj.github.io/interlock/concepts/projections/) that handle events and serve queries
- Orchestrate complex workflows with [Sagas](https://interlock-proj.github.io/interlock/guides/sagas/)
- Add cross-cutting concerns with [Middleware](https://interlock-proj.github.io/interlock/guides/custom-middleware/)
- Evolve your event schemas over time with [Upcasting](https://interlock-proj.github.io/interlock/guides/event-upcasting/)

> [Documentation](https://interlock-proj.github.io/interlock/) • [Tutorial](https://interlock-proj.github.io/interlock/tutorial/) • [Concepts](https://interlock-proj.github.io/interlock/concepts/) • [API Reference](https://interlock-proj.github.io/interlock/reference/) • [Contributing](#contributing)

## Features

Interlock embraces declarative, annotation-based configuration:

```python
from interlock import Aggregate, Command, ApplicationBuilder, handles_command, applies_event
from pydantic import BaseModel

# Commands express intent
class DepositMoney(Command[None]):
    amount: int

# Events record what happened  
class MoneyDeposited(BaseModel):
    amount: int

# Aggregates contain your business logic
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
```

Build applications with a fluent API:

```python
app = (
    ApplicationBuilder()
    .register_aggregate(BankAccount)
    .register_projection(BalanceProjection)
    .register_middleware(LoggingMiddleware)
    .build()
)

async with app:
    await app.dispatch(DepositMoney(aggregate_id=account_id, amount=100))
    balance = await app.query(GetBalance(aggregate_id=account_id))
```

Test with Given-When-Then scenarios:

```python
async with AggregateScenario(BankAccount) as scenario:
    scenario \
        .given(MoneyDeposited(amount=100)) \
        .when(DepositMoney(aggregate_id=scenario.aggregate_id, amount=50)) \
        .should_emit(MoneyDeposited) \
        .should_have_state(lambda acc: acc.balance == 150)
```

## Getting Started

Install interlock with `pip`:

```bash
pip install interlock
```

For MongoDB support:

```bash
pip install interlock[mongodb]
```

Then follow our [Quick Start Guide](https://interlock-proj.github.io/interlock/getting-started/quickstart/) or dive into the [Tutorial](https://interlock-proj.github.io/interlock/tutorial/).

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Write Side                                │
│  ┌──────────┐    ┌────────────┐    ┌────────────────────────┐   │
│  │ Commands │───▶│ Aggregates │───▶│ Events                 │   │
│  └──────────┘    └────────────┘    └───────────┬────────────┘   │
└────────────────────────────────────────────────┼─────────────────┘
                                                 ▼
                              ┌──────────────────────────────────┐
                              │          Event Store             │
                              └──────────────────────────────────┘
                                                 │
┌────────────────────────────────────────────────┼─────────────────┐
│                        Read Side               ▼                 │
│  ┌───────────┐    ┌─────────────┐    ┌────────────────────────┐ │
│  │  Queries  │───▶│ Projections │◀───│ Event Processors/Sagas │ │
│  └───────────┘    └─────────────┘    └────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

| Component | Purpose |
|-----------|---------|
| **Commands** | Express intent to change state |
| **Aggregates** | Validate business rules, emit events |
| **Events** | Immutable records of what happened |
| **Projections** | Build read models, handle queries |
| **Sagas** | Coordinate multi-step processes |

## Packages

| Package | Description | Version |
|---------|-------------|---------|
| `interlock` | Core framework with CQRS, Event Sourcing, DI | ![PyPI Version](https://badge.fury.io/py/interlock.svg) |
| `interlock[mongodb]` | MongoDB event store, snapshot storage, saga state | — |

## Why Event Sourcing?

| Benefit | How Interlock Delivers It |
|---------|---------------------------|
| **Complete audit trail** | Every change is recorded as an event |
| **Temporal queries** | Query your system at any point in time |
| **Scalability** | Read and write sides scale independently |
| **Debugging** | Replay events to understand how state evolved |
| **Flexibility** | Build multiple read models from the same events |

## Contributors

Interlock is open source. We welcome contributions!

<!-- ALL-CONTRIBUTORS-LIST:START -->
<!-- ALL-CONTRIBUTORS-LIST:END -->

## Contributing

### Getting Setup

Install the project with development dependencies:

```bash
pip install -e ".[dev]"
```

Or use the Makefile:

```bash
make install
```

### Running Tests

Run the full test suite:

```bash
make test
```

Or run specific test categories:

```bash
pytest tests/unit -v        # Unit tests only
pytest tests/integration -v # Integration tests only
```

### Code Quality

```bash
make lint   # Run ruff linter
make format # Format with black
make check  # Run all checks
```

---

<p align="center">
  Built with ❤️ using <a href="https://docs.pydantic.dev/">Pydantic</a> and Python's <a href="https://docs.python.org/3/library/asyncio.html">asyncio</a>
</p>
