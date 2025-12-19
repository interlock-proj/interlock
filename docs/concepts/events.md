# Events

An **event** is an immutable record of something that happened in the system. Events are the cornerstone of [Event Sourcing](event-sourcing.md)—they're the source of truth for all aggregate state.

## Events as Facts

Unlike commands (which express intent), events are **facts**. They record what already happened:

```python
# Command: "I want to deposit $100" (might fail)
DepositMoney(aggregate_id=account_id, amount=100)

# Event: "$100 was deposited" (already happened)
MoneyDeposited(amount=100)
```

Events are:

- **Immutable**: Once recorded, they never change
- **Ordered**: They have a sequence within their aggregate
- **Timestamped**: They record when they occurred
- **The source of truth**: State is derived from events

## Defining Events

Event data in Interlock is defined as Pydantic models:

```python
from pydantic import BaseModel

class AccountOpened(BaseModel):
    """A new account was opened."""
    owner_name: str
    initial_deposit: int = 0

class MoneyDeposited(BaseModel):
    """Money was deposited into an account."""
    amount: int

class MoneyWithdrawn(BaseModel):
    """Money was withdrawn from an account."""
    amount: int

class AccountClosed(BaseModel):
    """An account was closed."""
    reason: str
    final_balance: int
```

### The Event Wrapper

When events are stored and transported, Interlock wraps them in an `Event` envelope that adds metadata:

```python
from interlock.domain import Event

# The full event structure
event = Event(
    id=uuid4(),                    # Unique event ID
    aggregate_id=account_id,      # Which aggregate emitted this
    data=MoneyDeposited(amount=100),  # Your event data
    sequence_number=5,            # Position in aggregate's stream
    timestamp=datetime.now(UTC),  # When it occurred
    correlation_id=...,           # Trace ID
    causation_id=...              # What caused this
)

# Access the data
print(event.data.amount)  # 100
```

### Event Metadata

Every event automatically includes:

| Field | Type | Description |
|-------|------|-------------|
| `id` | `UUID` | Unique identifier for this event |
| `aggregate_id` | `UUID` | The aggregate that produced this event |
| `sequence_number` | `int` | Position in the aggregate's event stream |
| `timestamp` | `datetime` | When the event occurred (UTC) |
| `correlation_id` | `UUID \| None` | Links related events across a workflow |
| `causation_id` | `UUID \| None` | The command that caused this event |

### Accessing Event Metadata in Processors

Event processors can receive either just the event payload or the full `Event` wrapper, depending on their type annotation:

```python
class AccountBalanceProjection(EventProcessor):
    # Option 1: Receive just the payload
    @handles_event
    async def on_deposit_payload(self, event: MoneyDeposited) -> None:
        # 'event' is the MoneyDeposited payload only
        # Use this when you don't need aggregate_id or metadata
        await self.log_deposit(event.amount)

    # Option 2: Receive the full Event wrapper (recommended)
    @handles_event
    async def on_withdrawal_with_metadata(self, event: Event[MoneyWithdrawn]) -> None:
        # 'event' is the full Event wrapper with all metadata
        await self.repo.decrement(
            event.aggregate_id,      # Access from wrapper
            event.data.amount,       # Payload is in event.data
            event.timestamp          # Other metadata available too
        )
```

Use the `Event[T]` annotation when you need:

- The `aggregate_id` without duplicating it in the payload
- Event metadata like `timestamp`, `sequence_number`, `correlation_id`
- The full tracing context

Use the plain type annotation (`T`) when:

- You only need the event data itself
- You want simpler code and don't need metadata
- You've already included necessary IDs in the payload

## Naming Conventions

Events should be named in the **past tense**—they describe what happened:

| ✓ Good (Past Tense) | ✗ Bad |
|---------------------|-------|
| `AccountCreated` | `CreateAccount` |
| `MoneyDeposited` | `DepositMoney` |
| `OrderShipped` | `ShipOrder` |
| `PaymentFailed` | `FailPayment` |

## Emitting Events

Aggregates emit events through the `emit()` method:

```python
class BankAccount(Aggregate):
    balance: int = 0

    @handles_command
    async def deposit(self, command: DepositMoney) -> None:
        if command.amount <= 0:
            raise ValueError("Amount must be positive")
        
        # Emit the event - this records what happened
        self.emit(MoneyDeposited(amount=command.amount))

    @applies_event
    def apply_deposit(self, event: MoneyDeposited) -> None:
        # Apply the event to update state
        self.balance += event.amount
```

When `emit()` is called:

1. The event is wrapped with metadata
2. The event is added to `uncommitted_events`
3. The event is immediately applied to the aggregate
4. Later, uncommitted events are persisted to the event store

## Event Immutability

!!! warning "Events Are Forever"
    Once an event is stored, it must **never** be modified or deleted. This is a fundamental principle of event sourcing.

Events represent historical facts. Changing them would be like rewriting history—it breaks the integrity of your system.

### Handling Mistakes

If an event was recorded incorrectly, emit a **compensating event**:

```python
# Original (incorrect) event
MoneyDeposited(amount=50)  # Should have been $500

# DON'T do this
event.amount = 500  # ❌ Never modify events

# DO emit a correction
self.emit(DepositCorrected(
    original_event_id=event.id,
    original_amount=50,
    corrected_amount=500
))
```

This approach:

- Preserves the complete history
- Makes corrections auditable
- Allows replaying events correctly

## Event Ordering

Events within an aggregate are strictly ordered by `sequence_number`:

```
Aggregate: ACC-001
┌─────┬──────────────────────┬─────────────────────────────┐
│ Seq │ Timestamp            │ Event                       │
├─────┼──────────────────────┼─────────────────────────────┤
│ 1   │ 2024-01-01 10:00:00  │ AccountOpened(owner="Alice")│
│ 2   │ 2024-01-05 14:30:00  │ MoneyDeposited(amount=1000) │
│ 3   │ 2024-01-10 09:15:00  │ MoneyWithdrawn(amount=250)  │
│ 4   │ 2024-01-12 16:45:00  │ MoneyDeposited(amount=500)  │
└─────┴──────────────────────┴─────────────────────────────┘
```

Properties:

- Sequence numbers start at 1
- Each new event increments the sequence
- No gaps—sequences are contiguous
- Used for optimistic concurrency control

## Event Schema Evolution

Your domain model evolves, but events are immutable. When you need to change an event's structure, you have two options:

### 1. Backward-Compatible Changes

Pydantic handles simple additions with defaults:

```python
# Original
class MoneyDeposited(BaseModel):
    amount: int

# Extended - old events work automatically
class MoneyDeposited(BaseModel):
    amount: int
    source: str = "unknown"  # Default for old events
```

### 2. Event Upcasting

For more complex changes, use upcasters to transform old events:

```python
from interlock.application.events import EventUpcaster

class MoneyDepositedV1(BaseModel):
    amount: int

class MoneyDepositedV2(BaseModel):
    amount: int
    currency: str

class UpcastMoneyDeposited(EventUpcaster[MoneyDepositedV1, MoneyDepositedV2]):
    async def upcast_payload(self, data: MoneyDepositedV1) -> MoneyDepositedV2:
        return MoneyDepositedV2(
            amount=data.amount,
            currency="USD"  # Assume old events were USD
        )
```

See the [Event Upcasting Guide](../guides/event-upcasting.md) for details.

## Consuming Events

Events flow to multiple consumers:

### Event Appliers (in Aggregates)

Update aggregate state:

```python
@applies_event
def apply_deposit(self, event: MoneyDeposited) -> None:
    self.balance += event.amount
```

### Event Processors

Build read models and trigger side effects:

```python
class MoneyDeposited(BaseModel):
    amount: int

class AccountBalanceProjection(EventProcessor):
    @handles_event
    async def on_deposit(self, event: Event[MoneyDeposited]) -> None:
        await self.repository.increment_balance(
            event.aggregate_id,  # Access from wrapper
            event.data.amount
        )
```

### Sagas

Coordinate multi-aggregate workflows:

```python
class MoneyTransferSaga(Saga[TransferState]):
    @saga_step
    async def on_money_withdrawn(
        self, 
        event: MoneyWithdrawn, 
        state: TransferState
    ) -> TransferState:
        # Source account debited, now credit the target
        await self.command_bus.dispatch(DepositMoney(
            aggregate_id=state.to_account,
            amount=state.amount
        ))
        return state
```

## Event Design Guidelines

### Include Sufficient Context

Events should be self-describing:

```python
# Too sparse - lacks context
class OrderPlaced(BaseModel):
    order_id: str

# Self-describing
class OrderPlaced(BaseModel):
    customer_id: str
    items: list[OrderItem]
    total_amount: int
    shipping_address: Address
    placed_at: datetime
```

### Don't Include Derived Data

Let consumers compute derived values:

```python
# Wrong - includes derived state
class MoneyDeposited(BaseModel):
    amount: int
    new_balance: int  # ❌ Derived, might be wrong on replay

# Right - just the facts
class MoneyDeposited(BaseModel):
    amount: int  # ✓ Consumers can compute balance
```

### Consider Event Granularity

Balance between too many small events and too few large ones:

```python
# Too granular - chatty
class OrderItemAdded(BaseModel): ...
class OrderItemRemoved(BaseModel): ...
class OrderShippingUpdated(BaseModel): ...
class OrderDiscountApplied(BaseModel): ...

# Too coarse - loses information
class OrderUpdated(BaseModel):
    changes: dict  # What changed?

# Good balance
class OrderPlaced(BaseModel): ...
class OrderItemsModified(BaseModel): ...
class OrderShipped(BaseModel): ...
class OrderCancelled(BaseModel): ...
```

## Correlation and Causation

Events include tracing metadata:

```python
# Events from the same logical operation share correlation_id
event1 = Event(
    data=TransferInitiated(...),
    correlation_id="01HXYZ...",  # Trace ID
    causation_id="01HABC..."     # The command that started this
)

event2 = Event(
    data=MoneyWithdrawn(...),
    correlation_id="01HXYZ...",  # Same trace
    causation_id="01HDEF..."     # The previous event
)
```

This enables:

- **Distributed tracing**: Follow operations across services
- **Causal ordering**: Understand event relationships
- **Debugging**: See the chain of events

## Further Reading

- [Tutorial: Events & Sourcing](../tutorial/03-events-and-sourcing.md) — Hands-on guide
- [Event Sourcing](event-sourcing.md) — The pattern that events enable
- [Event Processors](event-processors.md) — Reacting to events
- [Event Upcasting Guide](../guides/event-upcasting.md) — Schema evolution
