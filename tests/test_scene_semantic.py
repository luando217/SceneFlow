"""Tests for SceneSemantic schema."""

from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class TestSceneSemantic:
    """Tests for SceneSemantic — the core semantic structure."""

    def _make_minimal(self) -> SceneSemantic:
        return SceneSemantic(
            scene_id="scene_001",
            video_id="ep_01",
            start_time=10.0,
            end_time=30.0,
            duration=20.0,
            start_frame=250,
            end_frame=750,
        )

    def test_create_minimal(self):
        scene = self._make_minimal()
        assert scene.scene_id == "scene_001"
        assert scene.video_id == "ep_01"
        assert scene.start_time == 10.0
        assert scene.end_time == 30.0
        assert scene.duration == 20.0
        assert scene.start_frame == 250
        assert scene.end_frame == 750
        # Defaults
        assert scene.characters == []
        assert scene.actions == []
        assert scene.objects == []
        assert scene.dialogue == ""
        assert scene.ocr_text == ""
        assert scene.motion_intensity == 0.0
        assert scene.motion_direction == "static"
        assert scene.action_pace == "slow"
        assert scene.schema_version == "Phase2.1"

    def test_create_with_entities(self):
        scene = SceneSemantic(
            scene_id="scene_001",
            video_id="ep_01",
            start_time=10.0,
            end_time=30.0,
            duration=20.0,
            start_frame=250,
            end_frame=750,
            characters=[
                CharacterEntity(normalized_name="naruto"),
                CharacterEntity(normalized_name="sasuke"),
            ],
            actions=[ActionEntity(normalized_name="running")],
            objects=[ObjectEntity(normalized_name="kunai")],
            environments=[
                EnvironmentEntity(normalized_name="forest")
            ],
            emotions=[EmotionEntity(normalized_name="angry")],
            dialogue="I hate you!",
        )
        assert len(scene.characters) == 2
        assert scene.characters[0].normalized_name == "naruto"
        assert scene.characters[1].normalized_name == "sasuke"
        assert scene.actions[0].normalized_name == "running"
        assert scene.objects[0].normalized_name == "kunai"
        assert scene.environments[0].normalized_name == "forest"
        assert scene.emotions[0].normalized_name == "angry"
        assert scene.dialogue == "I hate you!"

    def test_to_dict_deterministic(self):
        scene = self._make_minimal()
        d = scene.to_dict_deterministic()
        # Check deterministic key ordering (stable, not necessarily sorted)
        keys = list(d.keys())
        # First key should be schema_version (our defined order)
        assert keys[0] == "schema_version"
        # Second key should be scene_id
        assert keys[1] == "scene_id"
        # Check scene_id is present
        assert d["scene_id"] == "scene_001"

    def test_to_json(self):
        scene = self._make_minimal()
        json_str = scene.to_json()
        assert isinstance(json_str, str)
        # Verify it's valid JSON by round-trip
        import json
        d = json.loads(json_str)
        assert d["scene_id"] == "scene_001"
        assert d["video_id"] == "ep_01"

    def test_immutable(self):
        scene = self._make_minimal()
        import pydantic

        try:
            scene.scene_id = "changed"  # type: ignore
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass

    def test_empty_scene_id_raises(self):
        import pydantic

        try:
            SceneSemantic(
                scene_id="",
                video_id="ep_01",
                start_time=0,
                end_time=10,
                duration=10,
                start_frame=0,
                end_frame=250,
            )
            assert False, "Should have raised"
        except pydantic.ValidationError:
            pass