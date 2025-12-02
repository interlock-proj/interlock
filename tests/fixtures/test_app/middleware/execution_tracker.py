"""Execution tracking middleware for testing."""

from interlock.application.commands import CommandHandler, CommandMiddleware
from interlock.domain import Command
from interlock.routing import intercepts


class ExecutionTracker(CommandMiddleware):
    def __init__(self) -> None:
        self.executions: list[tuple[str, str]] = []

    @intercepts
    async def track_execution(self, command: Command, next: CommandHandler) -> None:
        self.executions.append(("start", type(command).__name__))
        result = await next(command)
        self.executions.append(("end", type(command).__name__))
        return result

