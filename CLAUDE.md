# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Interlock is a CQRS (Command Query Responsibility Segregation) and Event Sourcing framework for Python. It provides a clean, type-safe API for building event-sourced applications with support for aggregates, commands, events, projections, and sagas.

## Development Commands

### Package Management
This project uses `uv` for dependency management. All commands should be prefixed with `uv run`.

### Testing
```bash
# Run all tests with coverage
make test
# or
uv run pytest

# Run unit tests only
make test-unit
# or
uv run pytest tests/unit -v

# Run integration tests only
make test-integration
# or
uv run pytest tests/integration -v
```

### Code Quality
```bash
# Auto-fix formatting and linting
make format

# Check linting (without fixing)
make lint
# or
uv run ruff check .

# Type checking
make typecheck
# or
uv run mypy interlock

# Run all quality checks (lint + typecheck)
make quality

# Run everything (quality + tests)
make check
```

### Documentation
```bash
# Build documentation locally
uv run --extra docs mkdocs build

# Serve documentation with live reload
uv run --extra docs mkdocs serve
```

### Demo Application
```bash
# Run the FastAPI demo application
uv run --extra demo fastapi dev app/api.py
```

## Core Architecture

### Message Routing System

The framework uses a **decorator-based routing system** (`interlock/routing.py`) that eliminates the need for `isinstance` checks. All routing uses Python's `singledispatch` for efficient type-based dispatch.

**Key decorators:**
- `@handles_command` - Routes commands to aggregate methods
- `@applies_event` - Routes events to aggregate state appliers
- `@handles_event` - Routes events to event processor methods

**How it works:**
1. Decorators extract type annotations from methods at class definition time
2. `setup_routing()` scans the class hierarchy and builds a `MessageRouter`
3. The router uses `singledispatch` for O(1) type lookup at runtime

### Application Structure

The framework follows a **builder pattern** for application setup:

```python
app = (
    ApplicationBuilder()
    .add_aggregate(MyAggregate)
    .add_command(MyCommand)
    .add_event_processor(MyProcessor)
    .use_synchronous_processing()  # or .use_asynchronous_processing()
    .build()
)
```

**Key components:**
- `Application` - Main application instance that dispatches commands
- `ApplicationBuilder` - Fluent API for configuring the application
- `ApplicationProfile` - Reusable configuration sets
- Convention-based discovery available via `.convention_based("package_name")`

### Event Flow

1. **Command Dispatch** → `CommandBus` → **Middleware Chain** → `CommandHandler`
2. **Command Handler** → Loads aggregate from `AggregateRepository` → Aggregate handles command
3. **Aggregate** → Emits events → Events buffered in aggregate
4. **Repository Save** → Events persisted via `EventStore` → Aggregate version incremented
5. **Event Bus** → Events published via `EventTransport` (sync or async)
6. **Event Processors** → Receive events → Update projections/read models

### Storage Abstraction

The framework provides pluggable storage backends:

**Event Storage:**
- `EventStore` (interface) - Persists aggregate event streams
- `InMemoryEventStore` - Default in-memory implementation
- `Neo4jEventStore` - Neo4j-backed implementation (interlock/integrations/neo4j/)
- `MongoDBEventStore` - MongoDB-backed implementation (interlock/integrations/mongodb/)

**Snapshot Storage:**
- `AggregateSnapshotStorageBackend` - Interface for snapshot persistence
- Snapshots cache aggregate state to avoid replaying large event streams

**Checkpoint Storage:**
- `CheckpointBackend` - Tracks event processor position in event stream
- `InMemoryCheckpointBackend` - Default implementation

**Saga State Storage:**
- Persists saga state for long-running business processes

### Event Processing

**Synchronous vs Asynchronous:**
- **Synchronous**: Event processors run in-process immediately after events are saved
- **Asynchronous**: Events published to transport (e.g., Kafka) for separate worker processing

**Catchup Strategies:**
Event processors can catch up on historical events when added to existing systems:
- `NoCatchup` - Start from current position
- `FromReplayingEvents` - Replay all historical events
- `FromAggregateSnapshot` - Initialize from aggregate snapshots

**Catchup Conditions:**
Control when catchup completes:
- `Never` - Run indefinitely
- `AfterNEvents` - Stop after processing N events
- `AfterNAge` - Stop after reaching events younger than age
- `AnyOf` / `AllOf` - Combine conditions

### Repository Pattern

Aggregates are loaded/saved via repositories that handle:
- Event stream loading
- Event replay to reconstitute state
- Snapshot creation and loading
- Optimistic concurrency control
- Caching strategies

**Configuration:**
```python
.configure_repository_defaults(
    snapshot_strategy=SnapshotEveryN(every=100),
    cache_strategy=CacheForSeconds(seconds=300)
)
```

### Middleware System

Middleware wraps command execution for cross-cutting concerns:
- `ContextPropagationMiddleware` - Propagates correlation/causation IDs
- `LoggingMiddleware` - Logs command execution
- `IdempotencyMiddleware` - Prevents duplicate command execution
- `ConcurrencyRetryMiddleware` - Retries on optimistic concurrency failures

Middleware is applied in registration order.

### Event Upcasting

Supports event schema evolution through upcasting:
- `EventUpcaster` - Base class for transforming old event versions to new
- `LazyUpcastingStrategy` - Upcast on read (default)
- `EagerUpcastingStrategy` - Upcast on write
- Chain multiple upcasters to evolve through multiple versions

## Testing Guidelines

### Test Structure

Tests follow a **function-based** approach (not class-based) with centralized fixtures in `tests/conftest.py`.

**Key fixtures:**
- `base_app_builder` - Pre-configured `ApplicationBuilder` with common infrastructure
- `counter_app`, `bank_account_app` - Ready-to-use test applications
- `event_store`, `event_transport`, `saga_state_store` - Infrastructure components
- `aggregate_id`, `correlation_id` - ID generators

**Test organization:**
- `tests/unit/` - Fast, isolated component tests
- `tests/integration/` - Component interaction tests
- Integration tests may use `testcontainers` for real databases

### Writing Tests

```python
@pytest.mark.asyncio
async def test_something(base_app_builder, aggregate_id):
    """Clear test description."""
    app = (
        base_app_builder
        .add_aggregate(Counter)
        .add_command(IncrementCounter)
        .build()
    )

    await app.dispatch(IncrementCounter(aggregate_id=aggregate_id))
    # assertions
```

**Best practices:**
- Use descriptive test names that explain what is being tested
- Extend `base_app_builder` rather than creating from scratch
- Use fixtures for common test data
- Mark async tests with `@pytest.mark.asyncio`
- Use `@pytest.mark.unit` or `@pytest.mark.integration` markers

### Auto-cleanup

The `clear_execution_context` fixture automatically clears execution context after each test.

## Code Style

### Type Annotations

This project uses **strict mypy** checking. All functions must have type annotations:

```python
def my_function(param: str) -> int:
    return len(param)
```

### Linting

Uses `ruff` for linting and formatting with:
- Line length: 100 characters
- Target: Python 3.10+
- Enabled rules: pycodestyle, pyflakes, isort, pep8-naming, pyupgrade, bugbear, comprehensions, simplify, type-checking

### Import Style

Use absolute imports from the `interlock` package root.

## Common Patterns

### Defining Aggregates

```python
from interlock import Aggregate, handles_command, applies_event
from interlock.commands import Command
from interlock.events import Event

class MyAggregate(Aggregate):
    name: str = ""

    @handles_command
    def handle_create(self, cmd: CreateAggregate) -> None:
        self.emit(AggregateCreated(name=cmd.name))

    @applies_event
    def apply_created(self, evt: AggregateCreated) -> None:
        self.name = evt.name
```

**Key points:**
- Aggregates inherit from `Aggregate`
- Use `@handles_command` for command handlers
- Use `@applies_event` for event appliers
- Call `self.emit()` to emit events (don't modify state directly in handlers)
- Event appliers modify state

### Defining Commands

```python
from interlock.commands import Command
from uuid import UUID

class CreateAggregate(Command):
    name: str
```

Commands must:
- Inherit from `Command`
- Use Pydantic field definitions
- Include `aggregate_id: UUID` (inherited from `Command`)

### Defining Events

```python
from interlock.events import Event

class AggregateCreated(Event):
    name: str
```

Events must:
- Inherit from `Event`
- Use Pydantic field definitions
- Are immutable records of state changes
- Include metadata (aggregate_id, version, timestamp, correlation_id, causation_id)

### Defining Event Processors

```python
from interlock import EventProcessor, handles_event

class MyProjector(EventProcessor):
    @handles_event
    async def on_created(self, evt: AggregateCreated) -> None:
        # Update read model
        pass
```
