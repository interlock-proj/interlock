# Database Integrations

Connect Interlock to various databases and message brokers for production deployments.

## Goal

Configure Interlock to persist events, state, and caches using your infrastructure of choice.

## Prerequisites

- Understanding of [Event Sourcing](../concepts/event-sourcing.md)
- Basic knowledge of your target technology

## Pluggable Backends

Interlock uses abstract base classes for all IO-related components. You can swap 
implementations to match your infrastructure:

| Component | Purpose |
|-----------|---------|
| `EventStore` | Persist and load domain events |
| `EventTransport` | Publish events to subscribers (messaging) |
| `SagaStateStore` | Persist saga state across steps |
| `AggregateSnapshotStorageBackend` | Store aggregate snapshots |
| `AggregateCacheBackend` | Cache aggregates in memory or distributed cache |
| `IdempotencyStorageBackend` | Track processed commands for idempotency |

## Support Matrix

| Component | [MongoDB](#mongodb) | [Neo4j](#neo4j) | [Kafka](#kafka) | [Redis](#redis) | [SQLite](#sqlite) |
|-----------|:-------------------:|:---------------:|:---------------:|:---------------:|:-----------------:|
| `EventStore` | 🟡 | 🟡 | ❌ | ❌ | 🟡 |
| `EventTransport` | ❌ | ❌ | 🟡 | ❌ | ❌ |
| `SagaStateStore` | 🟡 | 🟡 | ❌ | 🟡 | 🟡 |
| `AggregateSnapshotStorageBackend` | 🟡 | 🟡 | ❌ | 🟡 | 🟡 |
| `AggregateCacheBackend` | ❌ | ❌ | ❌ | 🟡 | ❌ |
| `IdempotencyStorageBackend` | 🟡 | ❌ | ❌ | 🟡 | 🟡 |

**Legend:** ✅ Supported | 🟡 Planned | ❌ Not Applicable

## Configuration

Each integration provides a `*Configuration` class (e.g., `MongoConfiguration`, 
`RedisConfiguration`) that uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) 
to read connection details from environment variables. Register the configuration 
class and the backends will receive it via dependency injection—no hardcoded 
values needed.

---

## In-Memory (Default)

All components default to in-memory implementations for development and testing:

```python
app = (
    ApplicationBuilder()
    .register_aggregate(BankAccount)
    .build()  # Uses in-memory backends by default
)
```

!!! warning "Not for Production"
    In-memory backends lose all data when the application stops. Use persistent 
    backends for production.

---

## MongoDB

A document database well-suited for storing events and state.

### Interlock Roles

| Component | Fit |
|-----------|-----|
| `EventStore` | ✅ **Excellent** — High write throughput, flexible event payloads |
| `SagaStateStore` | ✅ **Excellent** — Document model matches saga state well |
| `AggregateSnapshotStorageBackend` | ✅ **Good** — Efficient storage and retrieval |
| `IdempotencyStorageBackend` | ✅ **Good** — TTL indexes for automatic cleanup |

### When to Use

- Your **primary event store** in most production deployments
- **Saga state** when you need durability across restarts
- **Snapshots** for aggregates with long event histories

### Status

| Component | Status |
|-----------|--------|
| `EventStore` | 🟡 Planned |
| `SagaStateStore` | 🟡 Planned |
| `AggregateSnapshotStorageBackend` | 🟡 Planned |
| `IdempotencyStorageBackend` | 🟡 Planned |

```python
# Coming soon
from interlock.integrations.mongodb import (
    MongoConfiguration,
    MongoEventStore,
    MongoSagaStateStore,
    MongoSnapshotStorage,
    MongoIdempotencyStorage,
)

app = (
    ApplicationBuilder()
    .register_dependency(MongoConfiguration)  # Reads from environment
    .register_dependency(EventStore, MongoEventStore)
    .register_dependency(SagaStateStore, MongoSagaStateStore)
    .register_dependency(AggregateSnapshotStorageBackend, MongoSnapshotStorage)
    .register_dependency(IdempotencyStorageBackend, MongoIdempotencyStorage)
    .build()
)
```

---

## Neo4j

A graph database suited for relationship-heavy state and projections.

### Interlock Roles

| Component | Fit |
|-----------|-----|
| `EventStore` | ⚠️ **Possible** — Works, but not optimized for append-heavy writes |
| `SagaStateStore` | ✅ **Good** — Useful when saga state involves relationships |
| `AggregateSnapshotStorageBackend` | ✅ **Good** — Snapshots with graph structure |

### When to Use

- **Saga state** that tracks relationships between entities
- **Snapshots** for aggregates with complex relationship graphs
- As a **secondary event store** when you need graph traversal queries

!!! note "Consider Your Primary Store"
    Neo4j works best alongside a primary `EventStore` like MongoDB or SQLite. 
    Use Neo4j for components where graph relationships matter.

### Status

| Component | Status |
|-----------|--------|
| `EventStore` | 🟡 Planned |
| `SagaStateStore` | 🟡 Planned |
| `AggregateSnapshotStorageBackend` | 🟡 Planned |

```python
# Coming soon
from interlock.integrations.neo4j import (
    Neo4jConfiguration,
    Neo4jEventStore,
    Neo4jSagaStateStore,
    Neo4jSnapshotStorage,
)

app = (
    ApplicationBuilder()
    .register_dependency(Neo4jConfiguration)
    .register_dependency(EventStore, Neo4jEventStore)
    .register_dependency(SagaStateStore, Neo4jSagaStateStore)
    .register_dependency(AggregateSnapshotStorageBackend, Neo4jSnapshotStorage)
    .build()
)
```

---

## Kafka

A distributed streaming platform for event transport between services.

### Interlock Roles

| Component | Fit |
|-----------|-----|
| `EventTransport` | ✅ **Excellent** — The standard for inter-service messaging |

Kafka is **only** applicable to `EventTransport`. It's designed for publishing 
events to other services, not for storing or querying events by aggregate ID.

### When to Use

- **Microservices architectures** where events flow between services
- **Event broadcasting** to multiple consumers (projections, notifications, etc.)
- **Cross-service sagas** that need reliable event delivery

### When NOT to Use

- **Single-service applications** — The in-memory transport is simpler
- As your `EventStore` — Use MongoDB or SQLite for that

### Architecture

```
┌─────────────────┐         ┌─────────────────┐
│   Service A     │         │   Service B     │
│                 │         │                 │
│ EventStore ─────┼──Kafka──┼─▶ Projections   │
│   (MongoDB)     │         │    (MongoDB)    │
└─────────────────┘         └─────────────────┘
```

### Status

| Component | Status |
|-----------|--------|
| `EventTransport` | 🟡 Planned |

```python
# Coming soon
from interlock.integrations.kafka import (
    KafkaConfiguration,
    KafkaEventTransport,
)

app = (
    ApplicationBuilder()
    .register_dependency(KafkaConfiguration)
    .register_dependency(EventTransport, KafkaEventTransport)
    .build()
)
```

---

## Redis

An in-memory data store ideal for caching and fast ephemeral state.

### Interlock Roles

| Component | Fit |
|-----------|-----|
| `AggregateCacheBackend` | ✅ **Excellent** — Sub-millisecond aggregate lookups |
| `SagaStateStore` | ✅ **Good** — Fast access for active sagas |
| `IdempotencyStorageBackend` | ✅ **Excellent** — TTL-based automatic cleanup |
| `AggregateSnapshotStorageBackend` | ⚠️ **Possible** — Consider durability needs |

### When to Use

- **Aggregate caching** to reduce load on your primary event store
- **Idempotency tracking** with automatic expiration of old entries
- **Saga state** for high-throughput, short-lived workflows

### When NOT to Use

- As your `EventStore` — Redis is memory-based; events need durable storage
- **Long-term snapshots** — Consider whether you need data to survive restarts

!!! note "Cache, Not Primary Storage"
    Redis complements your primary storage. Use it to cache aggregates and 
    track idempotency, with MongoDB or SQLite as your `EventStore`.

### Status

| Component | Status |
|-----------|--------|
| `AggregateCacheBackend` | 🟡 Planned |
| `SagaStateStore` | 🟡 Planned |
| `IdempotencyStorageBackend` | 🟡 Planned |
| `AggregateSnapshotStorageBackend` | 🟡 Planned |

```python
# Coming soon
from interlock.integrations.redis import (
    RedisConfiguration,
    RedisAggregateCache,
    RedisSagaStateStore,
    RedisIdempotencyStorage,
    RedisSnapshotStorage,
)

app = (
    ApplicationBuilder()
    .register_dependency(RedisConfiguration)
    .register_dependency(AggregateCacheBackend, RedisAggregateCache)
    .register_dependency(SagaStateStore, RedisSagaStateStore)
    .register_dependency(IdempotencyStorageBackend, RedisIdempotencyStorage)
    .build()
)
```

---

## SQLite

An embedded SQL database—zero configuration, single file, surprisingly capable.

### Interlock Roles

| Component | Fit |
|-----------|-----|
| `EventStore` | ✅ **Excellent** — Simple, durable, fast for single-node |
| `SagaStateStore` | ✅ **Excellent** — ACID transactions for saga state |
| `AggregateSnapshotStorageBackend` | ✅ **Good** — Reliable snapshot storage |
| `IdempotencyStorageBackend` | ✅ **Good** — SQL queries for cleanup |

### When to Use

- **Local development** with persistence (unlike in-memory)
- **Single-node production** for small-to-medium applications
- **Desktop/mobile apps** where you need an embedded event store
- **CI/CD testing** with isolated, fast databases

### When NOT to Use

- **Multi-node deployments** — SQLite doesn't replicate; use MongoDB
- **High write concurrency** — Single-writer lock can be a bottleneck

### Choosing Between SQLite and MongoDB

| Scenario | Recommendation |
|----------|----------------|
| Single server, low-to-medium traffic | SQLite |
| Multiple servers or high traffic | MongoDB |
| Local development with persistence | SQLite |
| Need horizontal scaling | MongoDB |

### Status

| Component | Status |
|-----------|--------|
| `EventStore` | 🟡 Planned |
| `SagaStateStore` | 🟡 Planned |
| `AggregateSnapshotStorageBackend` | 🟡 Planned |
| `IdempotencyStorageBackend` | 🟡 Planned |

```python
# Coming soon
from interlock.integrations.sqlite import (
    SqliteConfiguration,
    SqliteEventStore,
    SqliteSagaStateStore,
    SqliteSnapshotStorage,
    SqliteIdempotencyStorage,
)

app = (
    ApplicationBuilder()
    .register_dependency(SqliteConfiguration)
    .register_dependency(EventStore, SqliteEventStore)
    .register_dependency(SagaStateStore, SqliteSagaStateStore)
    .register_dependency(AggregateSnapshotStorageBackend, SqliteSnapshotStorage)
    .register_dependency(IdempotencyStorageBackend, SqliteIdempotencyStorage)
    .build()
)
```

---

## Implementing Custom Backends

All backends are abstract base classes. Implement the required methods for your 
infrastructure:

```python
from interlock.application.events import EventStore
from interlock.domain import Event
from ulid import ULID

class MyCustomEventStore(EventStore):
    async def save_events(
        self, 
        events: list[Event], 
        expected_version: int
    ) -> None:
        # Persist events to your storage
        # Use events[0].aggregate_id to get the aggregate
        ...

    async def load_events(
        self, 
        aggregate_id: ULID, 
        min_version: int
    ) -> list[Event]:
        # Load events from your storage
        ...

    async def rewrite_events(self, events: list[Event]) -> None:
        # Update existing events in place (for schema migration)
        ...
```

Register your implementation:

```python
app = (
    ApplicationBuilder()
    .register_dependency(EventStore, MyCustomEventStore)
    .build()
)
```

## Next Steps

- [Event Sourcing Concept](../concepts/event-sourcing.md)
- [Sagas Guide](sagas.md) — Uses `SagaStateStore`
- [API Reference](../reference/index.md)
