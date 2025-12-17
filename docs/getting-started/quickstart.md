# Quick Start

Build your first event-sourced application in 5 minutes.

!!! tip "Prerequisites"
    Make sure you have [installed Interlock](index.md) before continuing.

## Step 1: Define Your Domain

```python
from pydantic import BaseModel
from ulid import ULID

from interlock.domain import Aggregate, Command
from interlock.routing import handles_command, applies_event

# Define a command
class CreateTodo(Command):
    title: str

# Define event data
class TodoCreated(BaseModel):
    title: str

class TodoCompleted(BaseModel):
    pass

# Define an aggregate
class Todo(Aggregate):
    title: str = ""
    completed: bool = False

    @handles_command
    async def create(self, command: CreateTodo) -> None:
        self.emit(TodoCreated(title=command.title))

    @applies_event
    def apply_created(self, event: TodoCreated) -> None:
        self.title = event.title
```

## Step 2: Create an Application

```python
from interlock.application import ApplicationBuilder

app = (
    ApplicationBuilder()
    .register_aggregate(Todo)
    .build()
)
```

## Step 3: Send Commands

```python
async def main():
    async with app:
        # Create a new todo
        todo_id = ULID()
        await app.dispatch(CreateTodo(
            aggregate_id=todo_id,
            title="Learn Interlock"
        ))
        
        print(f"Created todo: {todo_id}")

# Run it
import asyncio
asyncio.run(main())
```

## What Just Happened?

1. **Command dispatched**: `CreateTodo` was sent to the application
2. **Aggregate loaded**: The `Todo` aggregate was created (or loaded from events)
3. **Handler executed**: `@handles_command` method validated and emitted an event
4. **Event applied**: `@applies_event` method updated the aggregate's state
5. **Event persisted**: The event was stored (in-memory by default)

## Next Steps

- [:octicons-arrow-right-24: Follow the full tutorial](../tutorial/index.md)
- [:octicons-arrow-right-24: Learn about concepts](../concepts/index.md)
- [:octicons-arrow-right-24: Explore the API reference](../reference/index.md)
