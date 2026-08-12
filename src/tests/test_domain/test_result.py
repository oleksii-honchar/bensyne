"""Unit tests for Result pattern, ErrorWithDetails, and DomainEvent."""

from datetime import datetime
from typing import List

import pytest

from src.utils.result import DomainEvent, ErrorWithDetails, Result


class TestErrorWithDetails:
    """ErrorWithDetails dataclass behavior."""

    def test_error_with_details_has_error_code_and_details(self):
        err = ErrorWithDetails(error_code="INVALID_INPUT", details={"field": "name"})
        assert err.error_code == "INVALID_INPUT"
        assert err.details == {"field": "name"}

    def test_error_with_details_empty_details(self):
        err = ErrorWithDetails(error_code="SOME_ERROR", details={})
        assert err.error_code == "SOME_ERROR"
        assert err.details == {}

    def test_error_with_details_equality(self):
        err1 = ErrorWithDetails(error_code="ERR", details={"a": 1})
        err2 = ErrorWithDetails(error_code="ERR", details={"a": 1})
        err3 = ErrorWithDetails(error_code="ERR", details={"b": 2})
        assert err1 == err2
        assert err1 != err3


class TestResultOk:
    """Result.ok factory method behavior."""

    def test_ok_returns_value_with_empty_errors(self):
        result = Result.ok("hello")
        assert result.value == "hello"
        assert result.errors == []
        assert result.is_ok is True
        assert result.is_ko is False

    def test_ok_with_none_value(self):
        result = Result.ok(None)
        assert result.value is None
        assert result.errors == []
        assert result.is_ok is True

    def test_ok_with_events(self):
        event = _make_event("test.event")
        result = Result.ok("data", events=[event])
        assert result.value == "data"
        assert result.errors == []
        assert result.events == [event]
        assert result.is_ok is True

    def test_ok_without_events_has_empty_events(self):
        result = Result.ok("data")
        assert result.events == []

    def test_ok_no_exceptions_thrown(self):
        """No exceptions thrown — all errors returned via Result.ko."""
        result = Result.ok(42)
        assert result.value == 42
        assert result.is_ok is True


class TestResultKo:
    """Result.ko factory method behavior."""

    def test_ko_returns_none_value_with_errors(self):
        err = ErrorWithDetails(error_code="FAIL", details={})
        result = Result.ko(errors=[err])
        assert result.value is None
        assert result.errors == [err]
        assert result.is_ok is False
        assert result.is_ko is True

    def test_ko_with_multiple_errors(self):
        err1 = ErrorWithDetails(error_code="E1", details={})
        err2 = ErrorWithDetails(error_code="E2", details={})
        result = Result.ko(errors=[err1, err2])
        assert result.value is None
        assert len(result.errors) == 2
        assert result.errors[0].error_code == "E1"
        assert result.errors[1].error_code == "E2"

    def test_ko_with_events(self):
        err = ErrorWithDetails(error_code="FAIL", details={})
        event = _make_event("test.event")
        result = Result.ko(errors=[err], events=[event])
        assert result.value is None
        assert result.errors == [err]
        assert result.events == [event]
        assert result.is_ko is True

    def test_ko_without_events_has_empty_events(self):
        err = ErrorWithDetails(error_code="FAIL", details={})
        result = Result.ko(errors=[err])
        assert result.events == []

    def test_ko_no_exceptions_thrown(self):
        """No exceptions thrown — all errors returned via Result.ko."""
        err = ErrorWithDetails(error_code="ERR", details={"msg": "bad"})
        result = Result.ko(errors=[err])
        assert result.is_ko is True
        assert result.errors[0].error_code == "ERR"


class TestResultProperties:
    """Result property accessors."""

    def test_is_ok_true_when_no_errors(self):
        result = Result.ok(1)
        assert result.is_ok is True

    def test_is_ko_true_when_has_errors(self):
        err = ErrorWithDetails(error_code="X", details={})
        result = Result.ko(errors=[err])
        assert result.is_ko is True

    def test_is_ok_and_is_ko_are_opposites(self):
        result_ok = Result.ok(1)
        assert result_ok.is_ok is True
        assert result_ok.is_ko is False

        err = ErrorWithDetails(error_code="X", details={})
        result_ko = Result.ko(errors=[err])
        assert result_ko.is_ok is False
        assert result_ko.is_ko is True

    def test_has_events_true_when_events_present(self):
        event = _make_event("test.event")
        result = Result.ok(1, events=[event])
        assert result.has_events() is True

    def test_has_events_false_when_no_events(self):
        result = Result.ok(1)
        assert result.has_events() is False

    def test_get_events_returns_events_list(self):
        event = _make_event("test.event")
        result = Result.ok(1, events=[event])
        assert result.get_events() == [event]

    def test_get_errors_returns_errors_list(self):
        err = ErrorWithDetails(error_code="X", details={})
        result = Result.ko(errors=[err])
        assert result.get_errors() == [err]


class TestResultGetFormattedErrors:
    """Result.get_formatted_errors formatting behavior."""

    def test_single_error_formatted(self):
        err = ErrorWithDetails(error_code="NOT_FOUND", details={"id": "1"})
        result = Result.ko(errors=[err])
        assert result.get_formatted_errors() == 'NOT_FOUND: {"id": "1"}'

    def test_multiple_errors_joined_with_comma(self):
        err1 = ErrorWithDetails(error_code="NOT_FOUND", details={"id": "1"})
        err2 = ErrorWithDetails(error_code="VALIDATION", details={"field": "name"})
        result = Result.ko(errors=[err1, err2])
        assert result.get_formatted_errors() == 'NOT_FOUND: {"id": "1"}, VALIDATION: {"field": "name"}'

    def test_empty_errors_returns_empty_string(self):
        result = Result.ok("value")
        assert result.get_formatted_errors() == ""

    def test_empty_details_formatted(self):
        err = ErrorWithDetails(error_code="SOME_ERROR", details={})
        result = Result.ko(errors=[err])
        assert result.get_formatted_errors() == "SOME_ERROR: {}"

    def test_details_with_nested_values(self):
        err = ErrorWithDetails(error_code="COMPLEX", details={"a": {"b": 2}, "c": [1, 2]})
        result = Result.ko(errors=[err])
        expected = 'COMPLEX: {"a": {"b": 2}, "c": [1, 2]}'
        assert result.get_formatted_errors() == expected


class TestDomainEvent:
    """DomainEvent abstract base class behavior."""

    def test_cannot_instantiate_abstract_DomainEvent(self):
        with pytest.raises(TypeError):
            DomainEvent()  # type: ignore[misc]

    def test_concrete_event_implements_abstract_members(self):
        event = _make_event("my.event")
        assert event.event_type == "my.event"
        assert isinstance(event.timestamp, datetime)
        assert event.get_name() == "my.event"

    def test_concrete_event_event_type_matches_get_name(self):
        event = _make_event("test.event.type")
        assert event.event_type == event.get_name()

    def test_concrete_event_timestamp_is_datetime(self):
        event = _make_event("test.event")
        assert isinstance(event.timestamp, datetime)


# --- Helpers ---

class _ConcreteEvent(DomainEvent):
    """Minimal concrete DomainEvent for testing."""

    def __init__(self, event_type: str) -> None:
        self._event_type = event_type
        self._timestamp = datetime.now()

    @property
    def event_type(self) -> str:
        return self._event_type

    @property
    def timestamp(self) -> datetime:
        return self._timestamp

    def get_name(self) -> str:
        return self._event_type


def _make_event(event_type: str) -> DomainEvent:
    return _ConcreteEvent(event_type)
