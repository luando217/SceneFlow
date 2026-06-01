"""SemanticHash — deterministic hashing for semantic objects.

Enables:
- Stable cache keys
- Replay verification
- Change detection
- Reproducibility validation
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aicore.semantic.contracts.semantic_patch import SemanticPatch
    from aicore.semantic.schemas.scene_semantic import SceneSemantic


class SemanticHash:
    """Deterministic hashing of semantic objects."""

    @staticmethod
    def compute_scene(scene: SceneSemantic) -> str:
        """SHA256 hash of scene canonical JSON.

        Guarantees:
        - Same scene state → same hash
        - Different state → different hash (with overwhelming probability)
        - Hash stable across Python versions
        - Safe for use as cache key

        Process:
        1. Convert scene to deterministic dict
        2. Serialize to canonical JSON (sorted keys, no spaces)
        3. Hash with SHA256
        4. Return hex string
        """
        canonical = scene.to_dict_deterministic()
        json_str = json.dumps(
            canonical,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        )
        hash_bytes = hashlib.sha256(json_str.encode("utf-8")).digest()
        return hash_bytes.hex()

    @staticmethod
    def compute_patch(patch: SemanticPatch) -> str:
        """SHA256 hash of single patch canonical JSON."""
        canonical = patch.to_dict_deterministic()
        json_str = json.dumps(
            canonical,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        )
        hash_bytes = hashlib.sha256(json_str.encode("utf-8")).digest()
        return hash_bytes.hex()

    @staticmethod
    def compute_patch_sequence(patches: list[SemanticPatch]) -> str:
        """SHA256 hash of entire patch sequence.

        Used for:
        - Replay verification (same patches → same hash → same result)
        - Caching patch sequences
        - Detecting patch list mutations

        Order matters! Reversing patch list changes the hash.
        """
        patch_dicts = [p.to_dict_deterministic() for p in patches]
        json_str = json.dumps(
            patch_dicts,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=True,
        )
        hash_bytes = hashlib.sha256(json_str.encode("utf-8")).digest()
        return hash_bytes.hex()

    @staticmethod
    def verify_scene_integrity(
        scene: SceneSemantic,
        expected_hash: str,
    ) -> bool:
        """Verify scene hasn't been tampered with.

        Returns:
            True if scene hash matches expected value
        """
        computed = SemanticHash.compute_scene(scene)
        return computed == expected_hash

    @staticmethod
    def verify_patch_sequence_integrity(
        patches: list[SemanticPatch],
        expected_hash: str,
    ) -> bool:
        """Verify patch sequence hasn't been tampered with."""
        computed = SemanticHash.compute_patch_sequence(patches)
        return computed == expected_hash

    @staticmethod
    def compare_scenes(
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        """Quick semantic equivalence check via hash.

        Note: Hash collision is theoretically possible but astronomically unlikely
        with SHA256. Use full equality check if absolute certainty is needed.
        """
        hash_a = SemanticHash.compute_scene(scene_a)
        hash_b = SemanticHash.compute_scene(scene_b)
        return hash_a == hash_b

    @staticmethod
    def format_hash(hash_str: str, length: int = 8) -> str:
        """Format hash for display (abbreviated).

        Example:
            a1b2c3d4e5f6g7h8... → a1b2c3d4 (if length=8)
        """
        return hash_str[:length]
