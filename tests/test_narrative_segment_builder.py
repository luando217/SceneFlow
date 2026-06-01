"""Tests for NarrativeSegmentBuilder."""

from aicore.semantic.aggregation.narrative_segment_builder import (
    NarrativeSegmentBuilder,
    NarrativeSegment,
)
from aicore.semantic.aggregation.temporal_coherence_engine import (
    TemporalCoherenceResult,
    TransitionType,
)
from aicore.semantic.schemas.scene_semantic import (
    SceneSemantic,
)
from aicore.semantic.schemas.entities import (
    CharacterEntity,
    ActionEntity,
    EnvironmentEntity,
)


def create_test_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
    video_id: str = "test_video",
    episode_id: str = "test_episode",
    characters: list[str] | None = None,
    actions: list[str] | None = None,
    environments: list[str] | None = None,
) -> SceneSemantic:
    """Helper to create a test scene."""
    char_list = []
    if characters:
        for char_name in characters:
            char_list.append(
                CharacterEntity(
                    normalized_name=char_name,
                    confidence=0.9,
                    source="test",
                )
            )

    action_list = []
    if actions:
        for action_name in actions:
            action_list.append(
                ActionEntity(
                    normalized_name=action_name,
                    confidence=0.8,
                    source="test",
                )
            )

    env_list = []
    if environments:
        for env_name in environments:
            env_list.append(
                EnvironmentEntity(
                    normalized_name=env_name,
                    confidence=0.85,
                    source="test",
                )
            )

    return SceneSemantic(
        scene_id=scene_id,
        video_id=video_id,
        episode_id=episode_id,
        start_time=start_time,
        end_time=end_time,
        characters=char_list,
        actions=action_list,
        environments=env_list,
        start_frame=0,
        end_frame=30,
    )


def create_coherence_result(
    scene_ids: list[str],
    continuity_scores: list[float] | None = None,
    transition_types: list[TransitionType] | None = None,
) -> TemporalCoherenceResult:
    """Helper to create a test temporal coherence result."""
    if continuity_scores is None:
        continuity_scores = [0.8] * max(len(scene_ids) - 1, 1)
    if transition_types is None:
        transition_types = [TransitionType.CONTINUOUS] * max(len(scene_ids) - 1, 1)

    return TemporalCoherenceResult(
        scene_ids=scene_ids,
        continuity_scores=continuity_scores,
        continuity_chains=[],
        flow_breaks=[],
        temporal_groups=[],
        transition_types=transition_types,
        overall_coherence=0.8 if continuity_scores else 1.0,
    )


class TestNarrativeSegment:
    """Test NarrativeSegment functionality."""

    def test_segment_creation(self):
        """Test creating a narrative segment."""
        segment = NarrativeSegment(
            segment_id="seg_test",
            scene_ids=["scene_1", "scene_2"],
            dominant_characters=["Alice", "Bob"],
            dominant_environment="kitchen",
            continuity_score=0.75,
            transition_type="continuous",
            segment_hash="abc123",
        )

        assert segment.segment_id == "seg_test"
        assert segment.scene_ids == ["scene_1", "scene_2"]
        assert segment.dominant_characters == ["Alice", "Bob"]
        assert segment.dominant_environment == "kitchen"
        assert segment.continuity_score == 0.75
        assert segment.transition_type == "continuous"
        assert segment.segment_hash == "abc123"

    def test_segment_to_dict(self):
        """Test segment serialization to dict."""
        segment = NarrativeSegment(
            segment_id="seg_test",
            scene_ids=["scene_1", "scene_2"],
            dominant_characters=["Alice"],
            dominant_environment="kitchen",
            continuity_score=0.8,
            transition_type="continuous",
            segment_hash="def456",
        )

        result = segment.to_dict()
        assert result["segment_id"] == "seg_test"
        assert result["scene_ids"] == ["scene_1", "scene_2"]
        assert result["dominant_characters"] == ["Alice"]
        assert result["dominant_environment"] == "kitchen"
        assert result["continuity_score"] == 0.8
        assert result["transition_type"] == "continuous"
        assert result["segment_hash"] == "def456"
        assert result["scene_count"] == 2

    def test_segment_from_temporal_coherence_single_scene(self):
        """Test creating segment from single scene."""
        scene = create_test_scene("scene_1", 0.0, 1.0)
        coherence_result = create_coherence_result(["scene_1"], [])

        segment = NarrativeSegment.from_temporal_coherence(
            scenes=[scene],
            coherence_result=coherence_result,
            segment_index=0,
            total_segments=1,
        )

        assert segment.segment_id == "seg_scene_1"
        assert segment.scene_ids == ["scene_1"]
        assert segment.dominant_environment == "unknown"
        assert segment.transition_type == "unknown"
        assert segment.continuity_score == 0.5

    def test_segment_from_temporal_coherence_with_content(self):
        """Test creating segment from scene with content."""
        scene = create_test_scene(
            "scene_1", 0.0, 1.0,
            characters=["Alice"],
            environments=["kitchen"],
        )
        coherence_result = create_coherence_result(["scene_1"], [])

        segment = NarrativeSegment.from_temporal_coherence(
            scenes=[scene],
            coherence_result=coherence_result,
            segment_index=0,
            total_segments=1,
        )

        assert segment.segment_id == "seg_scene_1"
        assert segment.scene_ids == ["scene_1"]
        assert "alice" in segment.dominant_characters
        assert segment.dominant_environment == "kitchen"
        assert segment.continuity_score == 1.0
        assert segment.transition_type == "unknown"


class TestNarrativeSegmentBuilder:
    """Test NarrativeSegmentBuilder functionality."""

    def test_builder_creation(self):
        """Test creating a narrative segment builder."""
        builder = NarrativeSegmentBuilder()
        assert builder.coherence_engine is not None

    def test_build_segments_empty(self):
        """Test building segments from empty scene list."""
        builder = NarrativeSegmentBuilder()
        segments = builder.build_segments([])
        assert segments == []

    def test_build_segments_single_scene(self):
        """Test building segments from single scene."""
        builder = NarrativeSegmentBuilder()
        scene = create_test_scene("scene_1", 0.0, 1.0)
        segments = builder.build_segments([scene])

        assert len(segments) == 1
        segment = segments[0]
        assert segment.segment_id == "seg_scene_1"
        assert segment.scene_ids == ["scene_1"]
        assert segment.transition_type == "unknown"

    def test_build_segments_multiple_scenes_continuous(self):
        """Test building segments from continuous scenes."""
        builder = NarrativeSegmentBuilder()
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
            create_test_scene("scene_3", 2.0, 3.0),
        ]
        segments = builder.build_segments(scenes)

        # Should create at least one segment
        assert len(segments) >= 1

        # Check that all scene IDs are accounted for
        all_scene_ids = []
        for segment in segments:
            all_scene_ids.extend(segment.scene_ids)
        assert set(all_scene_ids) == {
            "scene_1", "scene_2", "scene_3"
        }

    def test_build_segments_deterministic_ordering(self):
        """Test that segment building produces deterministic ordering."""
        builder = NarrativeSegmentBuilder()
        scenes = [
            create_test_scene("scene_c", 2.0, 3.0),
            create_test_scene("scene_a", 0.0, 1.0),
            create_test_scene("scene_b", 1.0, 2.0),
        ]

        # Run multiple times
        segments1 = builder.build_segments(scenes)
        segments2 = builder.build_segments(scenes)
        segments3 = builder.build_segments(scenes)

        # Should have same structure
        assert len(segments1) == len(segments2) == len(segments3)
        ids1 = [s.segment_id for s in segments1]
        ids2 = [s.segment_id for s in segments2]
        ids3 = [s.segment_id for s in segments3]
        assert ids1 == ids2 == ids3

    def test_build_segments_deterministic_scene_ids(self):
        """Test that scene IDs within segments are deterministic."""
        builder = NarrativeSegmentBuilder()
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
            create_test_scene("scene_3", 2.0, 3.0),
        ]

        segments1 = builder.build_segments(scenes)
        segments2 = builder.build_segments(scenes)

        # Scene IDs in each segment should be identical
        for s1, s2 in zip(segments1, segments2):
            assert s1.scene_ids == s2.scene_ids

    def test_build_segments_with_character_continuity(self):
        """Test building segments with character continuity."""
        builder = NarrativeSegmentBuilder()
        scenes = [
            create_test_scene(
                "scene_1", 0.0, 1.0,
                characters=["Alice", "Bob"],
                environments=["house"],
            ),
            create_test_scene(
                "scene_2", 1.0, 2.0,
                characters=["Alice", "Bob"],
                environments=["house"],
            ),
            create_test_scene(
                "scene_3", 2.0, 3.0,
                characters=["Charlie"],
                environments=["office"],
            ),
        ]

        segments = builder.build_segments(scenes)

        # Should group first two scenes together due to character/environment continuity
        assert len(segments) >= 1

        # Check that segments have reasonable content
        for segment in segments:
            assert len(segment.scene_ids) > 0
            assert segment.continuity_score >= 0.0
            assert segment.continuity_score <= 1.0
            assert isinstance(segment.dominant_environment, str)
            assert isinstance(segment.transition_type, str)

    def test_get_narrative_summary_empty(self):
        """Test narrative summary with empty segments."""
        builder = NarrativeSegmentBuilder()
        summary = builder.get_narrative_summary([])
        assert summary["segment_count"] == 0
        assert summary["total_scenes"] == 0
        assert summary["avg_continuity"] == 0.0
        assert summary["unique_characters"] == 0
        assert summary["unique_environments"] == 0

    def test_get_narrative_summary_with_segments(self):
        """Test narrative summary with segments."""
        builder = NarrativeSegmentBuilder()
        segments = [
            NarrativeSegment(
                segment_id="seg_1",
                scene_ids=["scene_1", "scene_2"],
                dominant_characters=["Alice", "Bob"],
                dominant_environment="kitchen",
                continuity_score=0.8,
                transition_type="continuous",
                segment_hash="hash1",
            ),
            NarrativeSegment(
                segment_id="seg_2",
                scene_ids=["scene_3"],
                dominant_characters=["Charlie"],
                dominant_environment="office",
                continuity_score=0.6,
                transition_type="scene_boundary",
                segment_hash="hash2",
            ),
        ]

        summary = builder.get_narrative_summary(segments)
        assert summary["segment_count"] == 2
        assert summary["total_scenes"] == 3
        assert summary["avg_continuity"] == 0.7  # (0.8 + 0.6) / 2
        assert summary["unique_characters"] == 3  # Alice, Bob, Charlie
        assert summary["unique_environments"] == 2  # kitchen, office
        assert summary["segment_ids"] == ["seg_1", "seg_2"]

    def test_replay_safety_segment_creation(self):
        """Test that segment creation is replay-safe (same input → same output)."""
        builder = NarrativeSegmentBuilder()
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0, characters=["Alice"]),
            create_test_scene("scene_2", 1.0, 2.0, characters=["Alice"]),
            create_test_scene("scene_3", 2.0, 3.0, characters=["Bob"]),
        ]

        # Create segments multiple times
        segments1 = builder.build_segments(scenes)
        segments2 = builder.build_segments(scenes)

        # All properties should be identical
        assert len(segments1) == len(segments2)
        for s1, s2 in zip(segments1, segments2):
            assert s1.segment_id == s2.segment_id
            assert s1.scene_ids == s2.scene_ids
            assert s1.dominant_characters == s2.dominant_characters
            assert s1.dominant_environment == s2.dominant_environment
            assert s1.continuity_score == s2.continuity_score
            assert s1.transition_type == s2.transition_type
            assert s1.segment_hash == s2.segment_hash

    def test_segment_deterministic_hash_generation(self):
        """Test that segment hash generation is deterministic."""
        scene = create_test_scene("test_scene", 0.0, 1.0)
        coherence_result = create_coherence_result(["test_scene"], [])

        segment1 = NarrativeSegment.from_temporal_coherence(
            scenes=[scene],
            coherence_result=coherence_result,
            segment_index=0,
            total_segments=1,
        )
        segment2 = NarrativeSegment.from_temporal_coherence(
            scenes=[scene],
            coherence_result=coherence_result,
            segment_index=0,
            total_segments=1,
        )

        assert segment1.segment_hash == segment2.segment_hash

    def test_no_hidden_mutations(self):
        """Test that builder doesn't mutate input scenes."""
        builder = NarrativeSegmentBuilder()
        original_scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]
        # Deep copy to check for mutations
        import copy
        scenes_copy = copy.deepcopy(original_scenes)

        builder.build_segments(original_scenes)

        # Scenes should be unchanged
        assert len(original_scenes) == len(scenes_copy)
        for orig, copy_scene in zip(original_scenes, scenes_copy):
            assert orig.scene_id == copy_scene.scene_id
            assert orig.video_id == copy_scene.video_id
            assert orig.start_time == copy_scene.start_time
            assert orig.end_time == copy_scene.end_time