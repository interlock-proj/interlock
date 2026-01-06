"""Unit tests for type_loader utilities."""

import pytest

from interlock.domain import Aggregate, Event
from interlock.integrations.mongodb.type_loader import get_qualified_name, load_type


class TestGetQualifiedName:
    """Tests for get_qualified_name."""

    def test_returns_module_and_class_name(self):
        """Should return module.ClassName format."""
        result = get_qualified_name(Event)
        assert result == "interlock.domain.event.Event"

    def test_aggregate_qualified_name(self):
        """Should work with Aggregate base class."""
        result = get_qualified_name(Aggregate)
        assert result == "interlock.domain.aggregate.Aggregate"

    def test_builtin_types(self):
        """Should work with builtin types."""
        result = get_qualified_name(str)
        assert result == "builtins.str"


class TestLoadType:
    """Tests for load_type."""

    def test_load_event_type(self):
        """Should load Event class from qualified name."""
        cls = load_type("interlock.domain.event.Event")
        assert cls is Event

    def test_load_aggregate_type(self):
        """Should load Aggregate class from qualified name."""
        cls = load_type("interlock.domain.aggregate.Aggregate")
        assert cls is Aggregate

    def test_roundtrip(self):
        """get_qualified_name and load_type should roundtrip."""
        qualified = get_qualified_name(Event)
        loaded = load_type(qualified)
        assert loaded is Event

    def test_invalid_name_no_module(self):
        """Should raise ImportError for name without module."""
        with pytest.raises(ImportError, match="Invalid qualified name"):
            load_type("JustAClassName")

    def test_nonexistent_module(self):
        """Should raise ImportError for nonexistent module."""
        with pytest.raises(ImportError):
            load_type("nonexistent.module.SomeClass")

    def test_nonexistent_class(self):
        """Should raise ImportError for nonexistent class in valid module."""
        with pytest.raises(ImportError, match="has no attribute"):
            load_type("interlock.domain.event.NonexistentClass")

    def test_caching(self):
        """Results should be cached."""
        # Call twice, should return same object
        cls1 = load_type("interlock.domain.event.Event")
        cls2 = load_type("interlock.domain.event.Event")
        assert cls1 is cls2
