"""PatchReplay — deterministic reconstruction and verification of semantic patches.

Enables:
- Reconstruction of patches from aggregation groups
- Deterministic serialization verification
- Replay-safe validation
- Hash integrity checks
"""

from __future__ import annotations

import json
from typing import List, Optional

from aicore.semantic.aggregation.aggregation_engine import AggregationGroup
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.schemas.semantic_hash import SemanticHash
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class PatchReplay:
    """Deterministic patch reconstruction and verification."""

    @staticmethod
    def reconstruct_from_group(group: AggregationGroup) -> SemanticPatch:
        """Reconstruct SemanticPatch from aggregation group.

        This is deterministic: same group always produces same patch.

        Args:
            group: AggregationGroup to reconstruct

        Returns:
            SemanticPatch with deterministic content
        """
        return group.to_semantic_patch()

    @staticmethod
    def verify_serialization(patch: SemanticPatch) -> bool:
        """Verify patch serializes to canonical JSON.

        Args:
            patch: Patch to verify

        Returns:
            True if serialization is canonical and stable
        """
        try:
            json1 = patch.to_json_deterministic()
            json2 = patch.to_json_deterministic()

            # Must be identical
            return json1 == json2
        except Exception:
            return False

    @staticmethod
    def verify_immutability(patch: SemanticPatch) -> bool:
        """Verify patch is immutable (frozen).

        Args:
            patch: Patch to verify

        Returns:
            True if patch is frozen
        """
        return patch.model_config.get("frozen", False)

    @staticmethod
    def compute_patch_hash(patch: SemanticPatch) -> str:
        """Compute deterministic hash of patch.

        Args:
            patch: Patch to hash

        Returns:
            SHA256 hash string
        """
        return SemanticHash.compute_patch(patch)

    @staticmethod
    def verify_hash_integrity(
        patch: SemanticPatch,
        expected_hash: str,
    ) -> bool:
        """Verify patch hash matches expected value.

        Args:
            patch: Patch to verify
            expected_hash: Expected hash value

        Returns:
            True if hashes match
        """
        computed = PatchReplay.compute_patch_hash(patch)
        return computed == expected_hash

    @staticmethod
    def replay_from_group(
        group: AggregationGroup,
        verify_determinism: bool = True,
    ) -> dict:
        """Replay patch creation from group.

        Reconstructs patch multiple times and verifies determinism.

        Args:
            group: AggregationGroup to replay
            verify_determinism: If True, verify with multiple runs

        Returns:
            {
                "success": bool,
                "patch": SemanticPatch,
                "hash": str,
                "is_deterministic": bool,
                "runs": int,
                "hashes": [str],  # all run hashes (if verify_determinism)
            }
        """
        patches = []
        hashes = []

        runs = 3 if verify_determinism else 1

        for run in range(runs):
            patch = PatchReplay.reconstruct_from_group(group)
            patches.append(patch)

            hash_val = PatchReplay.compute_patch_hash(patch)
            hashes.append(hash_val)

        # Check determinism
        all_same = len(set(hashes)) == 1
        is_deterministic = all_same if verify_determinism else True

        return {
            "success": is_deterministic,
            "patch": patches[0],  # Return first patch
            "hash": hashes[0],
            "is_deterministic": is_deterministic,
            "runs": runs,
            "hashes": hashes if verify_determinism else [],
        }

    @staticmethod
    def verify_replay_sequence(
        patches: List[SemanticPatch],
    ) -> dict:
        """Verify entire patch sequence is replay-safe.

        Args:
            patches: Sequence of patches to verify

        Returns:
            {
                "success": bool,
                "patch_count": int,
                "all_frozen": bool,
                "all_serializable": bool,
                "all_hashable": bool,
                "sequence_hash": str,
                "issues": [str],
            }
        """
        issues = []

        # Check each patch
        frozen = all(PatchReplay.verify_immutability(p) for p in patches)
        serializable = all(PatchReplay.verify_serialization(p) for p in patches)

        hashable = True
        hashes = []
        for patch in patches:
            try:
                h = PatchReplay.compute_patch_hash(patch)
                hashes.append(h)
            except Exception as e:
                hashable = False
                issues.append(f"Hash failed: {str(e)}")

        if not frozen:
            issues.append("Not all patches are frozen")
        if not serializable:
            issues.append("Not all patches serialize deterministically")
        if not hashable:
            issues.append("Not all patches are hashable")

        # Compute sequence hash
        sequence_hash = SemanticHash.compute_patch_sequence(patches)

        return {
            "success": len(issues) == 0,
            "patch_count": len(patches),
            "all_frozen": frozen,
            "all_serializable": serializable,
            "all_hashable": hashable,
            "sequence_hash": sequence_hash,
            "issues": issues,
        }

    @staticmethod
    def serialize_for_cache(patch: SemanticPatch) -> str:
        """Serialize patch to canonical JSON for caching.

        Args:
            patch: Patch to serialize

        Returns:
            Canonical JSON string
        """
        return patch.to_json_deterministic()

    @staticmethod
    def deserialize_from_cache(json_str: str) -> SemanticPatch:
        """Deserialize patch from cached JSON.

        Args:
            json_str: JSON string from cache

        Returns:
            Reconstructed SemanticPatch

        Raises:
            ValueError: If JSON is invalid
        """
        try:
            data = json.loads(json_str)
            return SemanticPatch.model_validate(data)
        except Exception as e:
            raise ValueError(f"Failed to deserialize patch: {str(e)}")

    @staticmethod
    def verify_cache_roundtrip(patch: SemanticPatch) -> bool:
        """Verify patch survives cache serialization roundtrip.

        Args:
            patch: Patch to test

        Returns:
            True if serialization roundtrip works deterministically
        """
        try:
            # Serialize
            json_str = PatchReplay.serialize_for_cache(patch)

            # Deserialize
            restored = PatchReplay.deserialize_from_cache(json_str)

            # Compare hashes
            hash1 = PatchReplay.compute_patch_hash(patch)
            hash2 = PatchReplay.compute_patch_hash(restored)

            return hash1 == hash2
        except Exception:
            return False

    @staticmethod
    def compare_patches(
        patch_a: SemanticPatch,
        patch_b: SemanticPatch,
    ) -> dict:
        """Compare two patches for equivalence.

        Args:
            patch_a: First patch
            patch_b: Second patch

        Returns:
            {
                "identical": bool,
                "hash_a": str,
                "hash_b": str,
                "differences": [str],
            }
        """
        hash_a = PatchReplay.compute_patch_hash(patch_a)
        hash_b = PatchReplay.compute_patch_hash(patch_b)

        differences = []

        if patch_a.source_node != patch_b.source_node:
            differences.append(f"source_node: {patch_a.source_node} vs {patch_b.source_node}")

        if patch_a.scene_id != patch_b.scene_id:
            differences.append(f"scene_id: {patch_a.scene_id} vs {patch_b.scene_id}")

        if patch_a.patch_order != patch_b.patch_order:
            differences.append(f"patch_order: {patch_a.patch_order} vs {patch_b.patch_order}")

        return {
            "identical": hash_a == hash_b,
            "hash_a": hash_a,
            "hash_b": hash_b,
            "differences": differences,
        }
