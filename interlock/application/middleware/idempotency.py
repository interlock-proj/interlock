"""Idempotency middleware for preventing duplicate command processing."""

from abc import ABC, abstractmethod
from logging import getLogger
from typing import Any, Protocol, runtime_checkable

from ...domain import Command
from ...routing import intercepts
from .base import Handler, Middleware

LOGGER = getLogger(__name__)


@runtime_checkable
class HasIdempotencyKey(Protocol):
    """Protocol for commands that have an idempotency key.

    Commands can provide idempotency tracking by having an `idempotency_key`
    attribute (field or property). The idempotency middleware will detect
    this and use it to prevent duplicate processing.

    Examples:
        Field-based idempotency key:

        >>> class DepositMoney(Command[None]):
        ...     amount: int
        ...     idempotency_key: str

        Property-based idempotency key (computed):

        >>> class TransferMoney(Command[None]):
        ...     from_account_id: ULID
        ...     to_account_id: ULID
        ...     amount: int
        ...
        ...     @property
        ...     def idempotency_key(self) -> str:
        ...         return f"{self.from_account_id}-{self.to_account_id}-{self.amount}"
    """

    @property
    def idempotency_key(self) -> str:
        """The idempotency key for this command."""
        ...


# Backward compatibility alias
IdempotencyTrackedCommand = HasIdempotencyKey


class IdempotencyStorageBackend(ABC):
    """Abstract base class for idempotency storage backends.

    This backend is used to store idempotency keys for commands.
    It will store the idempotency key for a command and return it
    when the command is dispatched.
    """

    @staticmethod
    def in_memory() -> "IdempotencyStorageBackend":
        return InMemoryIdempotencyStorageBackend()

    @staticmethod
    def null() -> "IdempotencyStorageBackend":
        return NullIdempotencyStorageBackend()

    @abstractmethod
    async def store_idempotency_key(self, key: str) -> None:
        """Store an idempotency key as processed."""
        ...

    @abstractmethod
    async def has_idempotency_key(self, key: str) -> bool:
        """Check if an idempotency key has been processed."""
        ...


class IdempotencyMiddleware(Middleware):
    """Middleware that ensures commands are idempotent.

    This middleware intercepts commands that have an `idempotency_key`
    attribute (field or property) and ensures they are only processed once.

    Commands without an idempotency_key are passed through unchanged.

    Examples:
        >>> app = (
        ...     ApplicationBuilder()
        ...     .register_dependency(IdempotencyStorageBackend, InMemoryIdempotencyStorageBackend)
        ...     .register_middleware(IdempotencyMiddleware)
        ...     .build()
        ... )

        Field-based key:

        >>> class DepositMoney(Command[None]):
        ...     amount: int
        ...     idempotency_key: str
        ...
        >>> await app.dispatch(DepositMoney(aggregate_id=id, amount=100, idempotency_key="dep-123"))

        Property-based key:

        >>> class TransferMoney(Command[None]):
        ...     from_account: ULID
        ...     to_account: ULID
        ...     amount: int
        ...
        ...     @property
        ...     def idempotency_key(self) -> str:
        ...         return f"{self.from_account}-{self.to_account}-{self.amount}"
    """

    __slots__ = ("idempotency_storage_backend",)

    def __init__(self, idempotency_storage_backend: IdempotencyStorageBackend):
        self.idempotency_storage_backend = idempotency_storage_backend

    @intercepts
    async def ensure_idempotency(self, command: Command, next: Handler) -> Any:
        """Check idempotency and process command if not processed.

        Commands with an `idempotency_key` attribute are checked against
        the storage backend. Commands without this attribute are passed
        through unchanged.

        Args:
            command: The command to check.
            next: The next handler in the chain.

        Returns:
            The result from the command handler, or None if skipped.
        """
        # Check if command has idempotency tracking
        if not isinstance(command, HasIdempotencyKey):
            return await next(command)

        idempotency_key = command.idempotency_key

        if await self.idempotency_storage_backend.has_idempotency_key(idempotency_key):
            LOGGER.warning(
                "Skipping previously processed command",
                extra={"idempotency_key": idempotency_key},
            )
            return None

        result = await next(command)
        await self.idempotency_storage_backend.store_idempotency_key(idempotency_key)
        return result


class InMemoryIdempotencyStorageBackend(IdempotencyStorageBackend):
    """In-memory implementation of the idempotency storage backend.

    This backend stores idempotency keys in memory. Suitable for
    single-process applications and testing.

    Note:
        Keys are lost on application restart. For production use,
        implement a persistent backend (Redis, database, etc.).
    """

    __slots__ = ("idempotency_keys",)

    def __init__(self):
        self.idempotency_keys: set[str] = set()

    async def store_idempotency_key(self, key: str) -> None:
        self.idempotency_keys.add(key)

    async def has_idempotency_key(self, key: str) -> bool:
        return key in self.idempotency_keys


class NullIdempotencyStorageBackend(IdempotencyStorageBackend):
    """A null implementation that never detects duplicates.

    Use this to effectively disable idempotency checking.
    """

    async def store_idempotency_key(self, key: str) -> None:
        pass

    async def has_idempotency_key(self, key: str) -> bool:
        return False

