"""Tests for semantic entity schemas."""

from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
    SemanticEntity,
)


class TestSemanticEntity:
    """Tests for base SemanticEntity."""

    def test_create_with_required_fields(self):
        entity = SemanticEntity(normalized_name="naruto")
        assert entity.normalized_name == "naruto"
        assert entity.confidence == 1.0
        assert entity.source == "unknown"

    def test_normalized_name_lowercased_and_stripped(self):
        entity = SemanticEntity(normalized_name="  Naruto Uzumaki  ")
        assert entity.normalized_name == "naruto uzumaki"

    def test_empty_name_raises(self):
        import pydantic

        try:
            SemanticEntity(normalized_name="")
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass

    def test_confidence_clamped(self):
        import pydantic

        try:
            SemanticEntity(normalized_name="test", confidence=1.5)
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass

    def test_frozen_immutability(self):
        entity = SemanticEntity(normalized_name="naruto")
        import pydantic

        try:
            entity.confidence = 0.5  # type: ignore
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass

    def test_extra_fields_forbidden(self):
        import pydantic

        try:
            SemanticEntity(
                normalized_name="naruto",
                extra_field="not_allowed",  # type: ignore
            )
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass

    def test_dict_deterministic(self):
        entity = SemanticEntity(
            normalized_name="naruto",
            confidence=0.9,
            source="wd14",
        )
        d = entity.dict_deterministic()
        keys = list(d.keys())
        # Check deterministic: sorted alphabetically
        assert keys == sorted(keys)


class TestCharacterEntity:
    """Tests for CharacterEntity."""

    def test_create_character(self):
        char = CharacterEntity(
            normalized_name="naruto",
            aliases=["naruto uzumaki"],
            appearance_features=["blonde hair", "blue eyes"],
            spoken_lines=5,
        )
        assert char.normalized_name == "naruto"
        assert "naruto uzumaki" in char.aliases
        assert char.spoken_lines == 5

    def test_default_spoken_lines(self):
        char = CharacterEntity(normalized_name="sakura")
        assert char.spoken_lines == 0


class TestObjectEntity:
    """Tests for ObjectEntity."""

    def test_create_object(self):
        obj = ObjectEntity(
            normalized_name="kunai",
            bbox=(10.0, 20.0, 30.0, 40.0),
        )
        assert obj.normalized_name == "kunai"
        assert obj.bbox == (10.0, 20.0, 30.0, 40.0)


class TestActionEntity:
    """Tests for ActionEntity."""

    def test_create_action(self):
        action = ActionEntity(
            normalized_name="running",
            intensity=0.8,
            duration_frames=24,
        )
        assert action.normalized_name == "running"
        assert action.intensity == 0.8
        assert action.duration_frames == 24

    def test_default_intensity(self):
        action = ActionEntity(normalized_name="standing")
        assert action.intensity == 0.0


class TestEmotionEntity:
    """Tests for EmotionEntity."""

    def test_create_emotion(self):
        emotion = EmotionEntity(
            normalized_name="determined",
            aliases=["focused", "resolute"],
        )
        assert emotion.normalized_name == "determined"
        assert "focused" in emotion.aliases


class TestEnvironmentEntity:
    """Tests for EnvironmentEntity."""

    def test_create_environment(self):
        env = EnvironmentEntity(
            normalized_name="forest clearing",
            location="outdoors",
            time_of_day="day",
            weather="clear",
        )
        assert env.normalized_name == "forest clearing"
        assert env.location == "outdoors"
        assert env.time_of_day == "day"

    def test_default_location(self):
        env = EnvironmentEntity(normalized_name="forest")
        assert env.location == "unknown"