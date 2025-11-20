from abc import ABC, abstractmethod
from logging import getLogger

from ..bus import CommandHandler, CommandMiddleware
from ..command import Command

LOGGER = getLogger(__name__)


class IdempotencyTrackedCommand(Command):
    """Command that is tracked for idempotency.

    This command is used to track commands that have been processed.
    It will store the command in the idempotency storage backend.
    """

    idempotency_key: str


class IdempotencyStorageBackend(ABC):
    """Abstract base class for idempotency storage backends.

    This backend is used to store idempotency keys for commands.
    It will store the idempotency key for a command and return it when the command is dispatched.
    """

    @staticmethod
    def in_memory() -> "IdempotencyStorageBackend":
        return InMemoryIdempotencyStorageBackend()

    @staticmethod
    def null() -> "IdempotencyStorageBackend":
        return NullIdempotencyStorageBackend()

    @abstractmethod
    async def store_processed_command(self, command: IdempotencyTrackedCommand) -> None:
        """Store the command as processed."""
        ...

    @abstractmethod
    async def has_processed_command(self, command: IdempotencyTrackedCommand) -> bool:
        """Check if the command has been processed."""
        ...


class IdempotencyMiddleware(CommandMiddleware[IdempotencyTrackedCommand]):
    """Middleware that ensures commands are idempotent.

    This middleware is used to ensure commands are idempotent.
    It will store the command in the idempotency storage backend and check if the
    command has been processed.
    """

    __slots__ = ("idempotency_storage_backend",)

    def __init__(self, idempotency_storage_backend: IdempotencyStorageBackend):
        self.idempotency_storage_backend = idempotency_storage_backend

    async def handle(
        self,
        command: IdempotencyTrackedCommand,
        next: CommandHandler[IdempotencyTrackedCommand],
    ) -> None:
        if await self.idempotency_storage_backend.has_processed_command(command):
            LOGGER.warning(
                "Skipping previously processed command",
                extra={"idempotency_key": command.idempotency_key},
            )
            return
        await next.handle(command)
        await self.idempotency_storage_backend.store_processed_command(command)


class InMemoryIdempotencyStorageBackend(IdempotencyStorageBackend):
    """In-memory implementation of the idempotency storage backend.

    This backend is used to store idempotency keys for commands in memory.
    It will store the idempotency key for a command and return it when the command is dispatched.
    """

    __slots__ = ("idempotency_keys",)

    def __init__(self):
        self.idempotency_keys: set[str] = set()

    async def store_processed_command(self, command: IdempotencyTrackedCommand) -> None:
        self.idempotency_keys.add(command.idempotency_key)

    async def has_processed_command(self, command: IdempotencyTrackedCommand) -> bool:
        return command.idempotency_key in self.idempotency_keys


class NullIdempotencyStorageBackend(IdempotencyStorageBackend):
    """A null implementation of the idempotency storage backend.

    This backend is used to do nothing.
    """

    async def store_processed_command(self, command: IdempotencyTrackedCommand) -> None:
        pass

    async def has_processed_command(self, command: IdempotencyTrackedCommand) -> bool:
        return False
