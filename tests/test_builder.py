"""Tests for SceneBuilder end-to-end pipeline."""

import json

from aicore.semantic.builder.scene_builder import SceneBuilder
from aicore.semantic.service.validator import SemanticValidator
from aicore.semantic.service.serializer import SemanticSerializer


class TestSceneBuilder:
    """End-to-end tests for SceneBuilder pipeline."""

    def setup_method(self):
        self.builder = SceneBuilder()
        self.validator = SemanticValidator()
        self.serializer = SemanticSerializer()

    def test_build_minimal(self):
        scene = self.builder.build(
            scene_id="scene_001",
            video_id="ep_01",
            start_time=10.0,
            end_time=30.0,
            start_frame=250,
            end_frame=750,
        )
        assert scene.scene_id == "scene_001"
        assert scene.video_id == "ep_01"
        assert scene.characters == []
        assert scene.actions == []
        assert scene.objects == []
        assert scene.dialogue == ""
        assert scene.ocr_text == ""

        # Validate
        assert self.validator.is_valid(scene)

    def test_build_full(self):
        scene = self.builder.build(
            scene_id="scene_001",
            video_id="ep_01",
            start_time=12.5,
            end_time=45.0,
            start_frame=312,
            end_frame=1125,
            raw_characters=["Naruto", "Sasuke"],
            raw_actions=["running", "punching"],
            raw_objects=["kunai"],
            raw_environments=["forest"],
            raw_emotions=["determined"],
            dialogue="I will never give up!",
            ocr_text="Episode 1: The Beginning",
            motion_intensity=0.7,
            motion_direction="right",
            action_pace="fast",
            episode_id="ep_01",
            num_keyframes=8,
            num_text_regions=1,
        )
        assert scene.scene_id == "scene_001"
        assert len(scene.characters) == 2
        assert scene.characters[0].normalized_name == "naruto"
        assert scene.characters[1].normalized_name == "sasuke"
        assert "I will never give up!" in scene.dialogue
        assert scene.motion_intensity == 0.7
        assert scene.motion_direction == "right"
        assert scene.action_pace == "fast"
        assert scene.num_keyframes == 8
        assert self.validator.is_valid(scene)

    def test_build_dialogue_normalization(self):
        scene = self.builder.build(
            scene_id="scene_002",
            video_id="ep_01",
            start_time=0,
            end_time=10,
            start_frame=0,
            end_frame=250,
            dialogue="  I  am   Naruto!  ",
        )
        assert scene.dialogue == "I am Naruto!"

    def test_build_ocr_normalization(self):
        scene = self.builder.build(
            scene_id="scene_003",
            video_id="ep_01",
            start_time=0,
            end_time=10,
            start_frame=0,
            end_frame=250,
            ocr_text="  EPISODE  1:   THE  BEGINNING  ",
        )
        assert scene.ocr_text == "episode 1: the beginning"

    def test_build_entity_deduplication(self):
        scene = self.builder.build(
            scene_id="scene_004",
            video_id="ep_01",
            start_time=0,
            end_time=10,
            start_frame=0,
            end_frame=250,
            raw_characters=["Naruto", "NARUTO", "naruto  "],
            raw_actions=["running", "running"],
            raw_emotions=["angry", "ANGRY"],
        )
        # Deduplication: only 1 unique character, 1 unique action, 1 emotion
        assert len(scene.characters) == 1
        assert len(scene.actions) == 1
        assert len(scene.emotions) == 1

    def test_build_entity_deterministic_order(self):
        """Entity lists should be sorted alphabetically by normalized_name."""
        scene = self.builder.build(
            scene_id="scene_005",
            video_id="ep_01",
            start_time=0,
            end_time=10,
            start_frame=0,
            end_frame=250,
            raw_characters=["Sasuke", "Naruto"],
        )
        assert scene.characters[0].normalized_name == "naruto"
        assert scene.characters[1].normalized_name == "sasuke"

    def test_build_emoji_dialogue(self):
        """Should handle unicode emoji gracefully."""
        scene = self.builder.build(
            scene_id="scene_006",
            video_id="ep_01",
            start_time=0,
            end_time=10,
            start_frame=0,
            end_frame=250,
            dialogue="I am happy 😊!",
        )
        # Emoji should be preserved (not stripped)
        assert "😊" in scene.dialogue

    def test_build_from_dict(self):
        data = {
            "scene_id": "scene_007",
            "video_id": "ep_01",
            "start_time": "5.0",
            "end_time": "15.0",
            "start_frame": "125",
            "end_frame": "375",
            "dialogue": "Hello!",
            "motion_intensity": "0.5",
            "num_keyframes": "4",
        }
        scene = self.builder.build_from_dict(data)
        assert scene.scene_id == "scene_007"
        assert scene.start_time == 5.0
        assert scene.end_time == 15.0
        assert scene.dialogue == "Hello!"
        assert scene.motion_intensity == 0.5
        assert scene.num_keyframes == 4
        assert self.validator.is_valid(scene)

    def test_roundtrip_serialization(self):
        scene = self.builder.build(
            scene_id="scene_008",
            video_id="ep_01",
            start_time=0,
            end_time=10,
            start_frame=0,
            end_frame=250,
            raw_characters=["Naruto"],
            dialogue="Believe it!",
        )

        # Serialize to JSON
        json_str = self.serializer.serialize_scene(scene)
        parsed = json.loads(json_str)

        # Check fields
        assert parsed["scene_id"] == "scene_008"
        assert parsed["dialogue"] == "Believe it!"
        assert len(parsed["characters"]) == 1
        assert parsed["characters"][0]["normalized_name"] == "naruto"

    def test_serializer_batch(self):
        scenes = []
        for i in range(3):
            scenes.append(
                self.builder.build(
                    scene_id=f"scene_{i:03d}",
                    video_id="ep_01",
                    start_time=float(i * 10),
                    end_time=float((i + 1) * 10),
                    start_frame=i * 250,
                    end_frame=(i + 1) * 250,
                )
            )

        json_str = self.serializer.serialize_scene_batch(scenes)
        parsed = json.loads(json_str)
        assert len(parsed) == 3
        assert parsed[0]["scene_id"] == "scene_000"
        assert parsed[2]["scene_id"] == "scene_002"

    def test_validator_semantic(self):
        import pydantic

        try:
            self.builder.build(
                scene_id="scene_009",
                video_id="ep_02",
                start_time=10.0,
                end_time=5.0,  # Invalid: end < start
                start_frame=100,
                end_frame=50,  # Invalid
            )
            assert False, "Should have raised ValidationError"
        except pydantic.ValidationError as exc:
            errors = exc.errors()
            assert len(errors) >= 2
            # Check that errors reference the relevant fields
            field_names = {e["loc"][0] for e in errors}
            assert "end_time" in field_names or "duration" in field_names
            assert "end_frame" in field_names

    def test_validator_motion_intensity(self):
        import pydantic

        try:
            self.builder.build(
                scene_id="scene_010",
                video_id="ep_02",
                start_time=0,
                end_time=10,
                start_frame=0,
                end_frame=250,
                motion_intensity=1.5,  # Invalid: > 1.0
            )
            assert False, "Should have raised ValidationError"
        except pydantic.ValidationError as exc:
            errors = exc.errors()
            field_names = {e["loc"][0] for e in errors}
            assert "motion_intensity" in field_names
