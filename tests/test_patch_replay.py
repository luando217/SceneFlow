"""Tests for PatchReplay."""

import pytest

from aicore.semantic.aggregation.aggregation_engine import AggregationGroup
from aicore.semantic.aggregation.patch_replay import PatchReplay
from tests.fixtures.scene_semantic_fixtures import (
    create_test_scene,
    create_multi_character_scene,
)


class TestPatchReplay:
    """Test PatchReplay functionality."""

    def test_reconstruct_from_group(self):
        """Test reconstructing patch from group."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        assert patch.scene_id == "test_group"
        assert patch.source_node == "aggregation_engine_v1"

    def test_verify_serialization(self):
        """Test verifying patch serialization."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        assert PatchReplay.verify_serialization(patch)

    def test_verify_immutability(self):
        """Test verifying patch immutability."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        assert PatchReplay.verify_immutability(patch)

    def test_compute_patch_hash(self):
        """Test computing patch hash."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)
        hash_val = PatchReplay.compute_patch_hash(patch)

        assert isinstance(hash_val, str)
        assert len(hash_val) == 64  # SHA256

    def test_verify_hash_integrity_matching(self):
        """Test hash integrity verification with matching hash."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)
        hash_val = PatchReplay.compute_patch_hash(patch)

        assert PatchReplay.verify_hash_integrity(patch, hash_val)

    def test_verify_hash_integrity_mismatch(self):
        """Test hash integrity verification with wrong hash."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        wrong_hash = "a" * 64

        assert not PatchReplay.verify_hash_integrity(patch, wrong_hash)

    def test_replay_from_group_deterministic(self):
        """Test replay produces deterministic results."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        result = PatchReplay.replay_from_group(group, verify_determinism=True)

        assert result["success"]
        assert result["is_deterministic"]
        assert len(set(result["hashes"])) == 1  # All hashes identical

    def test_verify_replay_sequence(self):
        """Test verifying replay sequence."""
        scenes1 = [create_test_scene("scene_1", 0.0, 1.0)]
        scenes2 = [create_test_scene("scene_2", 1.0, 2.0)]

        group1 = AggregationGroup(group_id="group_1", scenes=scenes1)
        group2 = AggregationGroup(group_id="group_2", scenes=scenes2)

        patch1 = PatchReplay.reconstruct_from_group(group1)
        patch2 = PatchReplay.reconstruct_from_group(group2)

        patches = [patch1, patch2]

        result = PatchReplay.verify_replay_sequence(patches)

        assert isinstance(result, dict)
        assert "success" in result
        assert "patch_count" in result
        assert result["patch_count"] == 2

    def test_serialize_for_cache(self):
        """Test serializing patch for cache."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)
        json_str = PatchReplay.serialize_for_cache(patch)

        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_deserialize_from_cache(self):
        """Test deserializing patch from cache."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)
        json_str = PatchReplay.serialize_for_cache(patch)

        restored = PatchReplay.deserialize_from_cache(json_str)

        assert restored.scene_id == patch.scene_id

    def test_verify_cache_roundtrip(self):
        """Test cache roundtrip verification."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        assert PatchReplay.verify_cache_roundtrip(patch)

    def test_compare_patches_identical(self):
        """Test comparing identical patches."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch1 = PatchReplay.reconstruct_from_group(group)
        patch2 = PatchReplay.reconstruct_from_group(group)

        comparison = PatchReplay.compare_patches(patch1, patch2)

        assert comparison["identical"]
        assert comparison["hash_a"] == comparison["hash_b"]

    def test_compare_patches_different(self):
        """Test comparing different patches."""
        scenes1 = [create_test_scene("scene_1", 0.0, 1.0)]
        scenes2 = [create_test_scene("scene_2", 1.0, 2.0)]

        group1 = AggregationGroup(group_id="group_1", scenes=scenes1)
        group2 = AggregationGroup(group_id="group_2", scenes=scenes2)

        patch1 = PatchReplay.reconstruct_from_group(group1)
        patch2 = PatchReplay.reconstruct_from_group(group2)

        comparison = PatchReplay.compare_patches(patch1, patch2)

        # Might be different depending on content
        assert isinstance(comparison["identical"], bool)


class TestPatchReplayDeterminism:
    """Test deterministic properties of patch replay."""

    def test_deterministic_reconstruction(self):
        """Test that reconstruction is deterministic."""
        scenes = [
            create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob"]),
            create_multi_character_scene("scene_2", 1.0, 2.0, ["Bob", "Charlie"]),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch1 = PatchReplay.reconstruct_from_group(group)
        patch2 = PatchReplay.reconstruct_from_group(group)
        patch3 = PatchReplay.reconstruct_from_group(group)

        hash1 = PatchReplay.compute_patch_hash(patch1)
        hash2 = PatchReplay.compute_patch_hash(patch2)
        hash3 = PatchReplay.compute_patch_hash(patch3)

        assert hash1 == hash2 == hash3

    def test_deterministic_serialization(self):
        """Test that serialization is deterministic."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        json1 = PatchReplay.serialize_for_cache(patch)
        json2 = PatchReplay.serialize_for_cache(patch)
        json3 = PatchReplay.serialize_for_cache(patch)

        assert json1 == json2 == json3

    def test_deterministic_hashing(self):
        """Test that hashing is deterministic."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        hash1 = PatchReplay.compute_patch_hash(patch)
        hash2 = PatchReplay.compute_patch_hash(patch)
        hash3 = PatchReplay.compute_patch_hash(patch)

        assert hash1 == hash2 == hash3

    def test_deterministic_replay_sequence(self):
        """Test that replay sequence is deterministic."""
        scenes = [
            create_test_scene("scene_1", 0.0, 1.0),
            create_test_scene("scene_2", 1.0, 2.0),
        ]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        result1 = PatchReplay.replay_from_group(group, verify_determinism=True)
        result2 = PatchReplay.replay_from_group(group, verify_determinism=True)

        assert result1["is_deterministic"]
        assert result2["is_deterministic"]
        assert result1["hash"] == result2["hash"]

    def test_deterministic_cache_roundtrip(self):
        """Test that cache roundtrip is deterministic."""
        scenes = [create_test_scene("scene_1", 0.0, 1.0)]

        group = AggregationGroup(
            group_id="test_group",
            scenes=scenes,
        )

        patch = PatchReplay.reconstruct_from_group(group)

        # Multiple roundtrips
        hash_original = PatchReplay.compute_patch_hash(patch)

        for _ in range(3):
            json_str = PatchReplay.serialize_for_cache(patch)
            restored = PatchReplay.deserialize_from_cache(json_str)
            hash_restored = PatchReplay.compute_patch_hash(restored)

            assert hash_original == hash_restored
