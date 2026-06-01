"""Tests for SemanticRetrievalIndex — Phase 3.1b deterministic index builder.

Tests verify:
- Deterministic build behavior
- Replay stability (same input → same output)
- Ordering stability (sorted keys, sorted scene_ids)
- Serialization stability
- Aggregation correctness
- Empty input handling
- Scene order invariance
"""

import pytest
from typing import List

from aicore.semantic.retrieval.index_builder import (
    SemanticRetrievalIndex,
)
from aicore.semantic.schemas.scene_semantic import (
    SceneSemantic,
    CharacterEntity,
    ActionEntity,
    EnvironmentEntity,
    ObjectEntity,
    EmotionEntity,
)


# ============================================================================
# Test fixtures
# ============================================================================


def make_scene(
    scene_id: str,
    video_id: str = "vid_001",
    episode_id: str = None,
    start_time: float = 0.0,
    end_time: float = 1.0,
    characters: List[str] = None,
    actions: List[str] = None,
    environments: List[str] = None,
    objects: List[str] = None,
    emotions: List[str] = None,
    dialogue: str = "",
    ocr_text: str = "",
) -> SceneSemantic:
    """Create a test scene with minimal required fields."""
    char_entities = [
        CharacterEntity(
            normalized_name=name.lower(),
            confidence=0.9,
        )
        for name in (characters or [])
    ]
    action_entities = [
        ActionEntity(
            normalized_name=name.lower(),
            intensity=0.5,
            confidence=0.9,
        )
        for name in (actions or [])
    ]
    env_entities = [
        EnvironmentEntity(
            normalized_name=name.lower(),
            confidence=0.9,
        )
        for name in (environments or [])
    ]
    obj_entities = [
        ObjectEntity(
            normalized_name=name.lower(),
            confidence=0.9,
        )
        for name in (objects or [])
    ]
    emotion_entities = [
        EmotionEntity(
            normalized_name=name.lower(),
            confidence=0.9,
        )
        for name in (emotions or [])
    ]

    return SceneSemantic(
        scene_id=scene_id,
        video_id=video_id,
        episode_id=episode_id,
        start_time=start_time,
        end_time=end_time,
        start_frame=int(start_time * 30),
        end_frame=int(end_time * 30),
        duration=end_time - start_time,
        characters=char_entities,
        actions=action_entities,
        environments=env_entities,
        objects=obj_entities,
        emotions=emotion_entities,
        dialogue=dialogue,
        ocr_text=ocr_text,
    )


def make_scene_shuffled(
    scene_id: str,
    video_id: str = "vid_001",
    start_time: float = 0.0,
    end_time: float = 1.0,
) -> SceneSemantic:
    """Create a basic scene with random ordering potential."""
    return make_scene(
        scene_id=scene_id,
        video_id=video_id,
        start_time=start_time,
        end_time=end_time,
        characters=["CharacterA"],
        actions=["walking"],
        environments=["forest"],
        objects=["tree"],
    )


# ============================================================================
# Test: Empty input handling
# ============================================================================


class TestEmptyInput:
    """Tests for empty scene input handling."""

    def test_build_from_empty_list(self):
        """Empty scene list produces empty index."""
        index = SemanticRetrievalIndex.build_from_scenes([])

        assert index.scene_count == 0
        assert index.segment_count == 0
        assert index.continuity_count == 0
        assert index.character_count == 0
        assert index.environment_count == 0
        assert index.action_count == 0
        assert index.total_indexes == 0

    def test_empty_index_hash_deterministic(self):
        """Empty index has consistent hash."""
        index1 = SemanticRetrievalIndex.build_from_scenes([])
        index2 = SemanticRetrievalIndex.build_from_scenes([])

        assert index1.index_hash == index2.index_hash

    def test_empty_index_serialization(self):
        """Empty index serializes deterministically."""
        index = SemanticRetrievalIndex.build_from_scenes([])

        json1 = index.to_json()
        json2 = index.to_json()

        assert json1 == json2

        # Verify empty structure
        import json
        data = json.loads(json1)
        assert data["scene_indexes"] == {}
        assert data["segment_indexes"] == {}
        assert data["continuity_indexes"] == {}


# ============================================================================
# Test: Deterministic build behavior
# ============================================================================


class TestDeterministicBuild:
    """Tests for deterministic build consistency."""

    def test_same_input_produces_same_index(self):
        """Same scenes always produce identical index."""
        scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0),
            make_scene("scene_2", start_time=1.0, end_time=2.0),
            make_scene("scene_3", start_time=2.0, end_time=3.0),
        ]

        index1 = SemanticRetrievalIndex.build_from_scenes(scenes)
        index2 = SemanticRetrievalIndex.build_from_scenes(scenes)

        assert index1.index_hash == index2.index_hash
        assert index1.scene_count == index2.scene_count
        assert index1.segment_count == index2.segment_count

    def test_scene_ids_sorted_in_indexes(self):
        """Scene IDs are sorted in all index entries."""
        scenes = [
            make_scene("scene_z", start_time=0.0, end_time=1.0),
            make_scene("scene_a", start_time=1.0, end_time=2.0),
            make_scene("scene_m", start_time=2.0, end_time=3.0),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        # Scene indexes maintain deterministic order
        scene_ids = list(index.scene_indexes.keys())
        assert scene_ids == sorted(scene_ids)

        # All scene_ids lists within entries should be sorted
        for scene_id, scene_idx in index.scene_indexes.items():
            # Characters, actions, environments should be sorted
            assert scene_idx.characters == sorted(scene_idx.characters)
            assert scene_idx.actions == sorted(scene_idx.actions)
            assert scene_idx.environments == sorted(scene_idx.environments)


# ============================================================================
# Test: Scene order invariance
# ============================================================================


class TestSceneOrderInvariance:
    """Tests for scene ordering invariance."""

    def test_shuffled_scenes_produce_same_result(self):
        """Scene order doesn't affect final index state."""
        base_scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0, characters=["Char"]),
            make_scene("scene_2", start_time=1.0, end_time=2.0, characters=["Char"]),
            make_scene("scene_3", start_time=2.0, end_time=3.0, characters=["Char"]),
        ]

        # Original order
        index1 = SemanticRetrievalIndex.build_from_scenes(base_scenes)

        # Reversed order
        reversed_scenes = list(reversed(base_scenes))
        index2 = SemanticRetrievalIndex.build_from_scenes(reversed_scenes)

        # Hash should match since sorting is deterministic
        assert index1.index_hash == index2.index_hash
        assert index1.scene_count == index2.scene_count

    def test_scene_ids_keyed_properly(self):
        """Scene indexes are keyed by scene_id regardless of input order."""
        scenes = [
            make_scene("scene_3", start_time=2.0, end_time=3.0, characters=["X"]),
            make_scene("scene_1", start_time=0.0, end_time=1.0, characters=["X"]),
            make_scene("scene_2", start_time=1.0, end_time=2.0, characters=["X"]),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        # All scene IDs should be present
        assert "scene_1" in index.scene_indexes
        assert "scene_2" in index.scene_indexes
        assert "scene_3" in index.scene_indexes
        assert index.scene_count == 3


# ============================================================================
# Test: Character aggregation
# ============================================================================


class TestCharacterAggregation:
    """Tests for character index aggregation."""

    def test_character_aggregation_basic(self):
        """Characters are aggregated correctly across scenes."""
        scenes = [
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                characters=["Naruto", "Sasuke"],
            ),
            make_scene(
                "scene_2",
                start_time=1.0,
                end_time=2.0,
                characters=["Naruto", "Sakura"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        # Naruto appears in 2 scenes
        naruto = index.get_character("naruto")
        assert naruto is not None
        assert naruto.appearance_count == 2
        assert "scene_1" in naruto.scene_ids
        assert "scene_2" in naruto.scene_ids

        # Sasuke appears in 1 scene
        sasuke = index.get_character("sasuke")
        assert sasuke is not None
        assert sasuke.appearance_count == 1

    def test_character_first_last_appearance(self):
        """First and last appearance times are tracked."""
        scenes = [
            make_scene(
                "scene_1",
                start_time=10.0,
                end_time=11.0,
                characters=["Goku"],
            ),
            make_scene(
                "scene_2",
                start_time=20.0,
                end_time=21.0,
                characters=["Goku"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        goku = index.get_character("goku")
        assert goku is not None
        assert goku.first_appearance == 10.0
        assert goku.last_appearance == 21.0  # end_time of last scene

    def test_character_scene_ids_sorted(self):
        """Character scene_ids are sorted."""
        scenes = [
            make_scene(
                "scene_3",
                start_time=2.0,
                end_time=3.0,
                characters=["Character"],
            ),
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                characters=["Character"],
            ),
            make_scene(
                "scene_2",
                start_time=1.0,
                end_time=2.0,
                characters=["Character"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)
        char_idx = index.get_character("character")
        assert char_idx is not None
        assert char_idx.scene_ids == ["scene_1", "scene_2", "scene_3"]


# ============================================================================
# Test: Environment aggregation
# ============================================================================


class TestEnvironmentAggregation:
    """Tests for environment index aggregation."""

    def test_environment_aggregation_basic(self):
        """Environments are aggregated correctly across scenes."""
        scenes = [
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                environments=["Forest", "BattleArena"],
            ),
            make_scene(
                "scene_2",
                start_time=1.0,
                end_time=2.0,
                environments=["Forest"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        forest = index.get_environment("forest")
        assert forest is not None
        assert forest.appearance_count == 2
        assert "scene_1" in forest.scene_ids
        assert "scene_2" in forest.scene_ids

        arena = index.get_environment("battlearena")
        assert arena is not None
        assert arena.appearance_count == 1

    def test_environment_scene_ids_sorted(self):
        """Environment scene_ids are sorted."""
        scenes = [
            make_scene(
                "scene_3",
                start_time=2.0,
                end_time=3.0,
                environments=["Location"],
            ),
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                environments=["Location"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)
        env_idx = index.get_environment("location")
        assert env_idx is not None
        assert env_idx.scene_ids == ["scene_1", "scene_3"]


# ============================================================================
# Test: Action aggregation
# ============================================================================


class TestActionAggregation:
    """Tests for action index aggregation."""

    def test_action_aggregation_basic(self):
        """Actions are aggregated correctly across scenes."""
        scenes = [
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                actions=["Running", "Jumping"],
            ),
            make_scene(
                "scene_2",
                start_time=1.0,
                end_time=2.0,
                actions=["Running"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        running = index.get_action("running")
        assert running is not None
        assert running.appearance_count == 2

        jumping = index.get_action("jumping")
        assert jumping is not None
        assert jumping.appearance_count == 1

    def test_action_temporal_ordering(self):
        """Action scene_ids are temporally ordered."""
        scenes = [
            make_scene(
                "scene_3",
                start_time=2.0,
                end_time=3.0,
                actions=["Action"],
            ),
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                actions=["Action"],
            ),
            make_scene(
                "scene_2",
                start_time=1.0,
                end_time=2.0,
                actions=["Action"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)
        action_idx = index.get_action("action")
        assert action_idx is not None
        # Should be temporally sorted by start_time
        assert action_idx.scene_ids == ["scene_1", "scene_2", "scene_3"]


# ============================================================================
# Test: Serialization stability
# ============================================================================


class TestSerializationStability:
    """Tests for deterministic serialization."""

    def test_json_serialization_idempotent(self):
        """JSON serialization is idempotent."""
        scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0, characters=["A"]),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        json1 = index.to_json()
        json2 = index.to_json()

        assert json1 == json2

    def test_dict_serialization_idempotent(self):
        """Dict serialization is idempotent."""
        scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0, characters=["A"]),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        dict1 = index.to_dict_deterministic()
        dict2 = index.to_dict_deterministic()

        assert dict1 == dict2

    def test_serialization_keys_sorted(self):
        """Serialized output has alphabetically sorted keys."""
        scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0, characters=["A"]),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)
        data = index.to_dict_deterministic()

        # Top-level keys should be sorted
        keys = list(data.keys())
        assert keys == sorted(keys), f"Keys not sorted: {keys}"

        # scene_indexes keys should be sorted
        scene_keys = list(data["scene_indexes"].keys())
        assert scene_keys == sorted(scene_keys)


# ============================================================================
# Test: Replay stability
# ============================================================================


class TestReplayStability:
    """Tests for replay-safe behavior."""

    def test_multiple_builds_identical(self):
        """Multiple build calls produce identical results."""
        scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0),
            make_scene("scene_2", start_time=1.0, end_time=2.0),
            make_scene("scene_3", start_time=2.0, end_time=3.0),
        ]

        index1 = SemanticRetrievalIndex.build_from_scenes(scenes)
        index2 = SemanticRetrievalIndex.build_from_scenes(scenes)
        index3 = SemanticRetrievalIndex.build_from_scenes(scenes)

        assert index1.index_hash == index2.index_hash == index3.index_hash

    def test_index_hash_deterministic(self):
        """Index hash is deterministic."""
        scenes = [
            make_scene("scene_1", start_time=0.0, end_time=1.0),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        # Hash should be a valid hex string
        assert len(index.index_hash) == 64  # SHA-256

        # Same scene produces same hash
        index2 = SemanticRetrievalIndex.build_from_scenes(scenes)
        assert index.index_hash == index2.index_hash

    def test_include_empty_flag(self):
        """include_empty flag works correctly."""
        scenes = [
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                characters=["Character"],
            ),
        ]

        index_with = SemanticRetrievalIndex.build_from_scenes(
            scenes, include_empty=True
        )
        index_without = SemanticRetrievalIndex.build_from_scenes(
            scenes, include_empty=False
        )

        # Should have character in both
        assert index_with.get_character("character") is not None
        assert index_without.get_character("character") is not None

        # Scene count should be same since it has content
        assert index_with.scene_count == index_without.scene_count == 1


# ============================================================================
# Test: Scene content preservation
# ============================================================================


class TestContentPreservation:
    """Tests for content preservation in indexes."""

    def test_dialogue_and_ocr_truncated(self):
        """Dialogue and OCR are truncated to 200 chars."""
        long_dialogue = "A" * 500
        long_ocr = "B" * 500

        scenes = [
            make_scene(
                "scene_1",
                start_time=0.0,
                end_time=1.0,
                dialogue=long_dialogue,
                ocr_text=long_ocr,
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)
        scene_idx = index.get_scene("scene_1")

        assert scene_idx is not None
        assert len(scene_idx.dialogue_snippet) <= 200
        assert len(scene_idx.ocr_snippet) <= 200


# ============================================================================
# Test: Multi-video handling
# ============================================================================


class TestMultiVideoHandling:
    """Tests for handling multiple videos."""

    def test_multiple_videos_separate_scenes(self):
        """Scenes from different videos are handled separately."""
        scenes = [
            make_scene(
                "scene_1",
                video_id="vid_001",
                start_time=0.0,
                end_time=1.0,
                characters=["Hero"],
            ),
            make_scene(
                "scene_2",
                video_id="vid_002",
                start_time=0.0,
                end_time=1.0,
                characters=["Hero"],
            ),
        ]

        index = SemanticRetrievalIndex.build_from_scenes(scenes)

        assert index.scene_count == 2

        scene1 = index.get_scene("scene_1")
        scene2 = index.get_scene("scene_2")

        assert scene1 is not None
        assert scene2 is not None
        assert scene1.video_id == "vid_001"
        assert scene2.video_id == "vid_002"


# ============================================================================
# Run tests
# ============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])