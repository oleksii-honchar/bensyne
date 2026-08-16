"""Unit tests for FileRelation domain entity, enums, and domain events."""

from datetime import datetime

import pytest

from src.domain.file_relation_entity import (
    Direction,
    FileRelation,
    RelationType,
)
from src.domain.events.file_relation_events import (
    FileRelationCreatedEvent,
    FileRelationUpdatedEvent,
)
from src.utils.result import DomainEvent, ErrorWithDetails, Result


class TestFileRelationOfValidData:
    """FileRelation.of accepts valid data and returns Result.ok."""

    def test_of_returns_ok_with_minimal_required_fields(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ok is True
        rel = result.value
        assert rel.id == "fr1"
        assert rel.source_file_id == "f1"
        assert rel.target_file_id == "f2"
        assert rel.relation_type == RelationType.SIBLING
        assert rel.strength == 1.0
        assert rel.direction == Direction.UNIDIRECTIONAL
        assert rel.description is None
        assert rel.created_at is not None
        assert rel.updated_at is not None

    def test_of_returns_ok_with_all_fields(self):
        now = datetime.now()
        result = FileRelation.of({
            "id": "fr2",
            "source_file_id": "f3",
            "target_file_id": "f4",
            "relation_type": RelationType.PARENT_CHILD,
            "strength": 0.85,
            "direction": Direction.BIDIRECTIONAL,
            "description": "Parent config and child config",
            "created_at": now,
            "updated_at": now,
        })
        assert result.is_ok is True
        rel = result.value
        assert rel.id == "fr2"
        assert rel.source_file_id == "f3"
        assert rel.target_file_id == "f4"
        assert rel.relation_type == RelationType.PARENT_CHILD
        assert rel.strength == 0.85
        assert rel.direction == Direction.BIDIRECTIONAL
        assert rel.description == "Parent config and child config"
        assert rel.created_at == now
        assert rel.updated_at == now

    def test_of_sets_timestamps_when_not_provided(self):
        result = FileRelation.of({
            "id": "fr3",
            "source_file_id": "f5",
            "target_file_id": "f6",
            "relation_type": RelationType.BACKLINK,
        })
        assert result.is_ok is True
        rel = result.value
        assert isinstance(rel.created_at, datetime)
        assert isinstance(rel.updated_at, datetime)

    def test_of_returns_frozen_instance(self):
        result = FileRelation.of({
            "id": "fr4",
            "source_file_id": "f7",
            "target_file_id": "f8",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ok is True
        rel = result.value
        with pytest.raises(Exception):
            rel.source_file_id = "f9"  # type: ignore

    def test_of_accepts_all_relation_types(self):
        for rt in RelationType:
            result = FileRelation.of({
                "id": f"fr_rt_{rt.value}",
                "source_file_id": "f_rt",
                "target_file_id": "f_rt2",
                "relation_type": rt,
            })
            assert result.is_ok is True
            assert result.value.relation_type == rt

    def test_of_accepts_all_directions(self):
        for d in Direction:
            result = FileRelation.of({
                "id": f"fr_d_{d.value}",
                "source_file_id": "f_d",
                "target_file_id": "f_d2",
                "relation_type": RelationType.SIBLING,
                "direction": d,
            })
            assert result.is_ok is True
            assert result.value.direction == d

    def test_of_with_zero_strength(self):
        result = FileRelation.of({
            "id": "fr5",
            "source_file_id": "f10",
            "target_file_id": "f11",
            "relation_type": RelationType.SIBLING,
            "strength": 0.0,
        })
        assert result.is_ok is True
        assert result.value.strength == 0.0

    def test_of_with_max_strength(self):
        result = FileRelation.of({
            "id": "fr6",
            "source_file_id": "f12",
            "target_file_id": "f13",
            "relation_type": RelationType.SIBLING,
            "strength": 1.0,
        })
        assert result.is_ok is True
        assert result.value.strength == 1.0

    def test_of_with_default_strength(self):
        result = FileRelation.of({
            "id": "fr7",
            "source_file_id": "f14",
            "target_file_id": "f15",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ok is True
        assert result.value.strength == 1.0

    def test_of_with_default_direction(self):
        result = FileRelation.of({
            "id": "fr8",
            "source_file_id": "f16",
            "target_file_id": "f17",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ok is True
        assert result.value.direction == Direction.UNIDIRECTIONAL

    def test_of_with_none_description(self):
        result = FileRelation.of({
            "id": "fr9",
            "source_file_id": "f18",
            "target_file_id": "f19",
            "relation_type": RelationType.SIBLING,
            "description": None,
        })
        assert result.is_ok is True
        assert result.value.description is None

    def test_of_emits_created_event(self):
        result = FileRelation.of({
            "id": "fr10",
            "source_file_id": "f20",
            "target_file_id": "f21",
            "relation_type": RelationType.DEPENDENCY,
        })
        assert result.is_ok is True
        assert result.has_events() is True
        events = result.get_events()
        assert len(events) == 1
        assert isinstance(events[0], FileRelationCreatedEvent)
        event = events[0]
        assert event.relation_id == "fr10"
        assert event.source_file_id == "f20"
        assert event.target_file_id == "f21"

    def test_of_is_domain_event(self):
        result = FileRelation.of({
            "id": "fr11",
            "source_file_id": "f22",
            "target_file_id": "f23",
            "relation_type": RelationType.SIBLING,
        })
        event = result.get_events()[0]
        assert isinstance(event, DomainEvent)


class TestFileRelationOfRejectsInvalidData:
    """FileRelation.of rejects invalid data and returns Result.ko."""

    def test_of_rejects_missing_id(self):
        result = FileRelation.of({
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ko is True

    def test_of_rejects_missing_source_file_id(self):
        result = FileRelation.of({
            "id": "fr1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ko is True

    def test_of_rejects_missing_target_file_id(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ko is True

    def test_of_rejects_missing_relation_type(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f2",
        })
        assert result.is_ko is True

    def test_of_rejects_empty_source_file_id(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"

    def test_of_rejects_empty_target_file_id(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"

    def test_of_rejects_strength_below_zero(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
            "strength": -0.1,
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"

    def test_of_rejects_strength_above_one(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
            "strength": 1.5,
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"

    def test_of_rejects_invalid_relation_type(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": "INVALID_TYPE",
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"

    def test_of_rejects_invalid_direction(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
            "direction": "INVALID_DIRECTION",
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"

    def test_of_rejects_self_relation(self):
        result = FileRelation.of({
            "id": "fr1",
            "source_file_id": "f1",
            "target_file_id": "f1",
            "relation_type": RelationType.SIBLING,
        })
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION"


class TestFileRelationStrengthValidation:
    """FileRelation strength boundary and precision tests."""

    def _create_relation(self, **overrides) -> FileRelation:
        props = {
            "id": "fr_str",
            "source_file_id": "f_str",
            "target_file_id": "f_str2",
            "relation_type": RelationType.SIBLING,
        }
        props.update(overrides)
        return FileRelation.of(props).value

    def test_strength_at_exact_zero(self):
        rel = self._create_relation(strength=0.0)
        assert rel.strength == 0.0

    def test_strength_at_exact_one(self):
        rel = self._create_relation(strength=1.0)
        assert rel.strength == 1.0

    def test_strength_fractions(self):
        rel = self._create_relation(strength=0.5)
        assert rel.strength == 0.5

    def test_strength_small_positive(self):
        rel = self._create_relation(strength=0.001)
        assert rel.strength == 0.001

    def test_strength_near_one(self):
        rel = self._create_relation(strength=0.999)
        assert rel.strength == 0.999

    def test_strength_rejected_for_negative(self):
        result = FileRelation.of({
            "id": "fr_neg",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
            "strength": -0.001,
        })
        assert result.is_ko is True

    def test_strength_rejected_over_one(self):
        result = FileRelation.of({
            "id": "fr_over",
            "source_file_id": "f1",
            "target_file_id": "f2",
            "relation_type": RelationType.SIBLING,
            "strength": 1.001,
        })
        assert result.is_ko is True


class TestFileRelationDirection:
    """FileRelation direction enum and behavior."""

    def _create_relation(self, **overrides) -> FileRelation:
        props = {
            "id": "fr_dir",
            "source_file_id": "f_dir",
            "target_file_id": "f_dir2",
            "relation_type": RelationType.SIBLING,
        }
        props.update(overrides)
        return FileRelation.of(props).value

    def test_default_direction_is_unidirectional(self):
        rel = self._create_relation()
        assert rel.direction == Direction.UNIDIRECTIONAL

    def test_unidirectional_direction(self):
        rel = self._create_relation(direction=Direction.UNIDIRECTIONAL)
        assert rel.direction == Direction.UNIDIRECTIONAL

    def test_bidirectional_direction(self):
        rel = self._create_relation(direction=Direction.BIDIRECTIONAL)
        assert rel.direction == Direction.BIDIRECTIONAL

    def test_direction_enum_values(self):
        assert Direction.UNIDIRECTIONAL.value == "unidirectional"
        assert Direction.BIDIRECTIONAL.value == "bidirectional"

    def test_direction_enum_iteration(self):
        directions = list(Direction)
        assert Direction.UNIDIRECTIONAL in directions
        assert Direction.BIDIRECTIONAL in directions
        assert len(directions) == 2


class TestFileRelationRelationType:
    """FileRelation relation_type enum values."""

    def _create_relation(self, **overrides) -> FileRelation:
        props = {
            "id": "fr_rt",
            "source_file_id": "f_rt",
            "target_file_id": "f_rt2",
            "relation_type": RelationType.SIBLING,
        }
        props.update(overrides)
        return FileRelation.of(props).value

    def test_all_relation_type_values(self):
        expected = {
            "PARENT_CHILD": "parent_child",
            "SIBLING": "sibling",
            "BACKLINK": "backlink",
            "FOLDER_HIERARCHY": "folder_hierarchy",
            "CROSS_REFERENCE": "cross_reference",
            "VERSION": "version",
            "OVERRIDE": "override",
            "DEPENDENCY": "dependency",
            "RECOMMENDATION": "recommendation",
        }
        for name, value in expected.items():
            assert getattr(RelationType, name).value == value

    def test_parent_child_relation(self):
        rel = self._create_relation(relation_type=RelationType.PARENT_CHILD)
        assert rel.relation_type == RelationType.PARENT_CHILD

    def test_sibling_relation(self):
        rel = self._create_relation(relation_type=RelationType.SIBLING)
        assert rel.relation_type == RelationType.SIBLING

    def test_backlink_relation(self):
        rel = self._create_relation(relation_type=RelationType.BACKLINK)
        assert rel.relation_type == RelationType.BACKLINK

    def test_folder_hierarchy_relation(self):
        rel = self._create_relation(relation_type=RelationType.FOLDER_HIERARCHY)
        assert rel.relation_type == RelationType.FOLDER_HIERARCHY

    def test_cross_reference_relation(self):
        rel = self._create_relation(relation_type=RelationType.CROSS_REFERENCE)
        assert rel.relation_type == RelationType.CROSS_REFERENCE

    def test_version_relation(self):
        rel = self._create_relation(relation_type=RelationType.VERSION)
        assert rel.relation_type == RelationType.VERSION

    def test_override_relation(self):
        rel = self._create_relation(relation_type=RelationType.OVERRIDE)
        assert rel.relation_type == RelationType.OVERRIDE

    def test_dependency_relation(self):
        rel = self._create_relation(relation_type=RelationType.DEPENDENCY)
        assert rel.relation_type == RelationType.DEPENDENCY

    def test_recommendation_relation(self):
        rel = self._create_relation(relation_type=RelationType.RECOMMENDATION)
        assert rel.relation_type == RelationType.RECOMMENDATION


class TestFileRelationUpdateStrength:
    """FileRelation.update_strength method with event emission."""

    def _create_relation(self, **overrides) -> FileRelation:
        props = {
            "id": "fr_upd",
            "source_file_id": "f_upd",
            "target_file_id": "f_upd2",
            "relation_type": RelationType.SIBLING,
        }
        props.update(overrides)
        return FileRelation.of(props).value

    def test_update_strength_success(self):
        rel = self._create_relation(strength=0.5)
        result = rel.update_strength(0.8)
        assert result.is_ok is True
        updated = result.value
        assert updated.strength == 0.8
        assert result.has_events() is True
        assert isinstance(result.get_events()[0], FileRelationUpdatedEvent)

    def test_update_strength_to_zero(self):
        rel = self._create_relation(strength=0.5)
        result = rel.update_strength(0.0)
        assert result.is_ok is True
        assert result.value.strength == 0.0

    def test_update_strength_to_one(self):
        rel = self._create_relation(strength=0.5)
        result = rel.update_strength(1.0)
        assert result.is_ok is True
        assert result.value.strength == 1.0

    def test_update_strength_rejected_negative(self):
        rel = self._create_relation()
        result = rel.update_strength(-0.1)
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_STRENGTH"

    def test_update_strength_rejected_above_one(self):
        rel = self._create_relation()
        result = rel.update_strength(1.5)
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_STRENGTH"

    def test_update_strength_no_change_returns_same(self):
        rel = self._create_relation(strength=0.5)
        result = rel.update_strength(0.5)
        assert result.is_ok is True
        assert result.value is rel
        assert result.has_events() is False

    def test_update_strength_changed_field_in_event(self):
        rel = self._create_relation(strength=0.5)
        result = rel.update_strength(0.8)
        assert result.is_ok is True
        events = result.get_events()
        assert len(events) == 1
        event = events[0]
        assert isinstance(event, FileRelationUpdatedEvent)
        assert "strength" in event.changed_fields

    def test_update_strength_preserves_other_fields(self):
        rel = self._create_relation(
            relation_type=RelationType.PARENT_CHILD,
            direction=Direction.BIDIRECTIONAL,
            description="test",
        )
        result = rel.update_strength(0.7)
        assert result.is_ok is True
        updated = result.value
        assert updated.relation_type == RelationType.PARENT_CHILD
        assert updated.direction == Direction.BIDIRECTIONAL
        assert updated.description == "test"
        assert updated.strength == 0.7

    def test_update_strength_updates_timestamp(self):
        rel = self._create_relation()
        result = rel.update_strength(0.7)
        assert result.is_ok is True
        updated = result.value
        assert updated.updated_at is not None
        assert updated.updated_at >= rel.created_at


class TestFileRelationUpdateDescription:
    """FileRelation.update_description method with event emission."""

    def _create_relation(self, **overrides) -> FileRelation:
        props = {
            "id": "fr_desc",
            "source_file_id": "f_desc",
            "target_file_id": "f_desc2",
            "relation_type": RelationType.SIBLING,
        }
        props.update(overrides)
        return FileRelation.of(props).value

    def test_update_description_from_none(self):
        rel = self._create_relation()
        result = rel.update_description("New description")
        assert result.is_ok is True
        assert result.value.description == "New description"
        assert result.has_events() is True

    def test_update_description_replace(self):
        rel = self._create_relation(description="Old")
        result = rel.update_description("New")
        assert result.is_ok is True
        assert result.value.description == "New"
        assert result.has_events() is True

    def test_update_description_to_none(self):
        rel = self._create_relation(description="Old")
        result = rel.update_description(None)
        assert result.is_ok is True
        assert result.value.description is None
        assert result.has_events() is True

    def test_update_description_no_change_returns_same(self):
        rel = self._create_relation(description="Same")
        result = rel.update_description("Same")
        assert result.is_ok is True
        assert result.value is rel
        assert result.has_events() is False

    def test_update_description_event_has_changed_field(self):
        rel = self._create_relation()
        result = rel.update_description("New")
        assert result.is_ok is True
        event = result.get_events()[0]
        assert isinstance(event, FileRelationUpdatedEvent)
        assert "description" in event.changed_fields


class TestFileRelationCreatedEvent:
    """FileRelationCreatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileRelationCreatedEvent.of(
            relation_id="fr1",
            source_file_id="f1",
            target_file_id="f2",
        )
        assert result.is_ok is True
        event = result.value
        assert event.relation_id == "fr1"
        assert event.source_file_id == "f1"
        assert event.target_file_id == "f2"

    def test_factory_rejects_empty_relation_id(self):
        result = FileRelationCreatedEvent.of(
            relation_id="",
            source_file_id="f1",
            target_file_id="f2",
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION_CREATED_EVENT"

    def test_factory_rejects_empty_source_file_id(self):
        result = FileRelationCreatedEvent.of(
            relation_id="fr1",
            source_file_id="",
            target_file_id="f2",
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION_CREATED_EVENT"

    def test_factory_rejects_empty_target_file_id(self):
        result = FileRelationCreatedEvent.of(
            relation_id="fr1",
            source_file_id="f1",
            target_file_id="",
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION_CREATED_EVENT"

    def test_event_type(self):
        event = FileRelationCreatedEvent.of("fr1", "f1", "f2").value
        assert event.event_type == "file_relation.created"

    def test_get_name(self):
        event = FileRelationCreatedEvent.of("fr1", "f1", "f2").value
        assert event.get_name() == "file_relation.created"

    def test_timestamp_is_datetime(self):
        event = FileRelationCreatedEvent.of("fr1", "f1", "f2").value
        assert isinstance(event.timestamp, datetime)

    def test_is_domain_event(self):
        event = FileRelationCreatedEvent.of("fr1", "f1", "f2").value
        assert isinstance(event, DomainEvent)


class TestFileRelationUpdatedEvent:
    """FileRelationUpdatedEvent creation, validation, and serialization."""

    def test_factory_accepts_valid_inputs(self):
        result = FileRelationUpdatedEvent.of(
            relation_id="fr1",
            changed_fields=["strength", "description"],
        )
        assert result.is_ok is True
        event = result.value
        assert event.relation_id == "fr1"
        assert event.changed_fields == ["strength", "description"]

    def test_factory_rejects_empty_relation_id(self):
        result = FileRelationUpdatedEvent.of(
            relation_id="",
            changed_fields=["strength"],
        )
        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_FILE_RELATION_UPDATED_EVENT"

    def test_factory_accepts_empty_changed_fields(self):
        result = FileRelationUpdatedEvent.of(
            relation_id="fr1",
            changed_fields=[],
        )
        assert result.is_ok is True

    def test_event_type(self):
        event = FileRelationUpdatedEvent.of("fr1", ["strength"]).value
        assert event.event_type == "file_relation.updated"

    def test_get_name(self):
        event = FileRelationUpdatedEvent.of("fr1", ["strength"]).value
        assert event.get_name() == "file_relation.updated"

    def test_is_domain_event(self):
        event = FileRelationUpdatedEvent.of("fr1", ["strength"]).value
        assert isinstance(event, DomainEvent)
