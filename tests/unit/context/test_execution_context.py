"""Tests for ExecutionContext class and context storage."""

from uuid import UUID, uuid4

from interlock.context import (
    ExecutionContext,
    clear_context,
    get_context,
    get_or_create_context,
    set_context,
)


def test_create_context_with_defaults():
    """Context.create() should generate a new correlation_id."""
    ctx = ExecutionContext.create()

    assert ctx.correlation_id is not None
    assert isinstance(ctx.correlation_id, UUID)
    assert ctx.causation_id == ctx.correlation_id  # Self-referencing at entry
    assert ctx.command_id is None


def test_create_context_with_specific_correlation_id():
    """Context.create() should use provided correlation_id."""
    correlation_id = uuid4()
    ctx = ExecutionContext.create(correlation_id=correlation_id)

    assert ctx.correlation_id == correlation_id
    assert ctx.causation_id == correlation_id


def test_for_command():
    """Context.for_command() should set command_id."""
    ctx = ExecutionContext.create()
    command_id = uuid4()
    cmd_ctx = ctx.for_command(command_id)

    assert cmd_ctx.correlation_id == ctx.correlation_id
    assert cmd_ctx.command_id == command_id
    assert cmd_ctx.causation_id == ctx.causation_id


def test_for_event():
    """Context.for_event() should set causation to event_id and clear command_id."""
    ctx = ExecutionContext.create()
    event_id = uuid4()
    evt_ctx = ctx.for_event(event_id)

    assert evt_ctx.correlation_id == ctx.correlation_id
    assert evt_ctx.causation_id == event_id
    assert evt_ctx.command_id is None


def test_with_causation():
    """Context.with_causation() should update causation_id."""
    ctx = ExecutionContext.create()
    new_causation = uuid4()
    updated_ctx = ctx.with_causation(new_causation)

    assert updated_ctx.correlation_id == ctx.correlation_id
    assert updated_ctx.causation_id == new_causation
    assert updated_ctx.command_id == ctx.command_id


def test_context_immutability():
    """ExecutionContext should be immutable."""
    ctx = ExecutionContext.create()
    original_correlation = ctx.correlation_id

    # Create modified context
    command_id = uuid4()
    new_ctx = ctx.for_command(command_id)

    # Original should be unchanged
    assert ctx.correlation_id == original_correlation
    assert ctx.command_id is None

    # New context should have the command_id
    assert new_ctx.correlation_id == original_correlation
    assert new_ctx.command_id == command_id


def test_get_context_when_not_set():
    """get_context() should return empty context when not set."""
    ctx = get_context()

    assert ctx.correlation_id is None
    assert ctx.causation_id is None
    assert ctx.command_id is None


def test_set_and_get_context():
    """set_context() and get_context() should store and retrieve context."""
    expected_ctx = ExecutionContext.create()
    set_context(expected_ctx)

    actual_ctx = get_context()

    assert actual_ctx.correlation_id == expected_ctx.correlation_id
    assert actual_ctx.causation_id == expected_ctx.causation_id
    assert actual_ctx.command_id == expected_ctx.command_id


def test_clear_context():
    """clear_context() should reset context to empty."""
    set_context(ExecutionContext.create())
    clear_context()

    ctx = get_context()

    assert ctx.correlation_id is None
    assert ctx.causation_id is None
    assert ctx.command_id is None


def test_get_or_create_context_when_not_set():
    """get_or_create_context() should create new context if not set."""
    ctx = get_or_create_context()

    assert ctx.correlation_id is not None
    assert isinstance(ctx.correlation_id, UUID)


def test_get_or_create_context_when_already_set():
    """get_or_create_context() should return existing context."""
    original_ctx = ExecutionContext.create()
    set_context(original_ctx)

    ctx = get_or_create_context()

    assert ctx.correlation_id == original_ctx.correlation_id
    assert ctx.causation_id == original_ctx.causation_id
