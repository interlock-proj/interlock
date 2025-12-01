from pydantic import BaseModel, Field
from ulid import ULID


class Command(BaseModel):
    """Base class for all commands in the system.

    Commands represent intentions to change state and are dispatched to
    command handlers. All commands must include an aggregate_id to identify
    which aggregate instance to operate on.

    Attributes:
        aggregate_id: ULID of the aggregate that should handle this command.
        correlation_id: Optional correlation ID for distributed tracing.
        causation_id: Optional ID of what caused this command.
        command_id: Unique identifier for this command instance.
    """

    aggregate_id: ULID
    correlation_id: ULID | None = None
    causation_id: ULID | None = None
    command_id: ULID = Field(default_factory=ULID)
