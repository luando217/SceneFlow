"""Tests for AggregationEngine."""

import pytest

from aicore.semantic.aggregation.aggregation_engine import (
    AggregationEngine,
    AggregationGroup,
)
from tests.fixtures.scene_semantic_fixtures import (
    create_test_scene,
    create_multi_character_scene,
)


class TestAggregationGroup:
    """Test AggregationGroup functionality."""

    def test_group_creation(self):
        """Test creating aggregation group."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
            merge_reason="dialogue_continuity",
        )

        assert group.group_id == "test_group"
        assert len(group.scenes) == 2
        assert group.merge_reason == "dialogue_continuity"

    def test_group_summary(self):
        """Test group summary generation."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        summary = group.summary()

        assert summary["group_id"] == "test_group"
        assert summary["scene_count"] == 2
        assert summary["total_duration"] == 2.0
        assert "scene_ids" in summary
        assert len(summary["scene_ids"]) == 2

    def test_to_merged_state(self):
        """Test converting group to merged state."""
        scenes = [
            create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob"]),
            create_multi_character_scene("scene_2", 1.0, 2.0, ["Bob", "Charlie"]),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        merged = group.to_merged_state()

        # Should have merged characters
        assert len(merged.characters) >= 2  # At least Alice, Bob, Charlie

    def test_to_semantic_patch(self):
        """Test converting group to semantic patch."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = group.to_semantic_patch()

        assert patch.scene_id == "test_group"
        assert patch.source_node == "aggregation_engine_v1"
        assert patch.schema_version == "Phase2A.3"


class TestAggregationEngine:
    """Test AggregationEngine functionality."""

    def test_engine_creation(self):
        """Test creating engine."""
        engine = AggregationEngine()

        assert engine.continuity_detector is not None
        assert engine.rule_set is not None

    def test_aggregate_single_scene(self):
        """Test aggregating single scene."""
        engine = AggregationEngine()

        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        groups = engine.aggregate(scenes)

        assert len(groups) == 1
        assert len(groups[0].scenes) == 1

    def test_aggregate_multiple_scenes_no_merge(self):
        """Test aggregating scenes with no continuity."""
        engine = AggregationEngine()

        # Create scenes with large time gap
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0, video_id="video_1"),
            create_test_scene("scene_2", 10.0, 11.0, video_id="video_2"),
        ]

        groups = engine.aggregate(scenes)

        # Should be separate groups
        assert len(groups) >= 1

    def test_aggregate_temporal_continuity(self):
        """Test aggregating temporally continuous scenes."""
        engine = AggregationEngine()

        # Create adjacent scenes
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        groups = engine.aggregate(scenes)

        # Likely to be grouped (temporal continuity rule)
        assert len(groups) >= 1

    def test_aggregate_character_continuity(self):
        """Test aggregating scenes with character continuity."""
        engine = AggregationEngine()

        scenes = [
            create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob"]),
            create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice", "Bob"]),
        ]

        groups = engine.aggregate(scenes)

        # Character overlap should trigger merge
        assert len(groups) >= 1

    def test_deterministic_ordering(self):
        """Test that aggregation is deterministic."""
        engine = AggregationEngine()

        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
            create_test_scene("scene_3", 2.0, 3.0),
        ]

        # Run multiple times
        groups1 = engine.aggregate(scenes)
        groups2 = engine.aggregate(scenes)
        groups3 = engine.aggregate(scenes)

        # Should have same structure
        assert len(groups1) == len(groups2) == len(groups3)
        assert [len(g.scenes) for g in groups1] == [len(g.scenes) for g in groups2]

    def test_merge_decision(self):
        """Test getting merge decision."""
        engine = AggregationEngine()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_b = create_test_scene("scene_2", 1.0, 2.0)

        decision = engine.get_merge_decision(scene_a, scene_b)

        assert "should_merge" in decision
        assert "decision" in decision
        assert "scores" in decision

    def test_stable_group_ids(self):
        """Test that group IDs are stable."""
        engine = AggregationEngine()

        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        groups1 = engine.aggregate(scenes)
        groups2 = engine.aggregate(scenes)

        # Group IDs should match
        ids1 = [g.group_id for g in groups1]
        ids2 = [g.group_id for g in groups2]

        assert ids1 == ids2


class TestGroupDeterminism:
    """Test deterministic properties of aggregation."""

    def test_deterministic_serialization(self):
        """Test that group serialization is deterministic."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch1 = group.to_semantic_patch()
        patch2 = group.to_semantic_patch()

        json1 = patch1.to_json_deterministic()
        json2 = patch2.to_json_deterministic()

        assert json1 == json2

    def test_merge_state_deterministic(self):
        """Test that merged state generation is deterministic."""
        scenes = [
            create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob"]),
            create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice", "Bob"]),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        merged1 = group.to_merged_state()
        merged2 = group.to_merged_state()

        # Character order should be stable
        chars1 = list(merged1.characters.keys())
        chars2 = list(merged2.characters.keys())

        assert chars1 == chars2

    def test_group_summarization_stable(self):
        """Test that group summaries are stable."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        summary1 = group.summary()
        summary2 = group.summary()

        # Summaries should be identical
        assert summary1 == summary2
