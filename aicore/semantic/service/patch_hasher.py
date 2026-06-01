"""PatchHasher — deterministic hash computation and verification.

Phase 2A.3: Stable content hashing for cache keys, replay identity,
and deduplication.  Every patch content layout produces exactly one
SHA-256 hash regardless of metadata (timestamps, provenance, etc.).

Usage:
    from aicore.semantic.service.patch_hasher import PatchHasher

    hasher = PatchHasher()
    h = hasher.compute_hash(my_patch)
    assert hasher.verify_hash(my_patch, h)
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from aicore.semantic.contracts.semantic_patch import SemanticPatch


class PatchHasher:
    """Deterministic hasher for SemanticPatch instances.

    The hash algorithm:
    1. Extract content payload via patch._content_dict()
    2. Serialize with ``json.dumps(..., sort_keys=True, default=str)``
    3. SHA-256 hex digest of the resulting UTF-8 bytes

    This ensures that two semantically identical patches produce the
    same hash regardless of:
    - patch_hash field value
    - provenance / conflict_markers metadata
    - object identity (only value equality matters)
    """

    @staticmethod
    def compute_hash(patch: SemanticPatch) -> str:
        """Compute the stable content hash for a patch.

        Args:
            patch: The SemanticPatch to hash.

        Returns:
            SHA-256 hex string (64 characters).
        """
        raw = patch._content_dict()
        return PatchHasher._hash_dict(raw)

    @staticmethod
    def verify_hash(patch: SemanticPatch, expected_hash: str) -> bool:
        """Verify that a patch's content matches an expected hash.

        Args:
            patch: The SemanticPatch to verify.
            expected_hash: SHA-256 hex string to compare against.

        Returns:
            True if the patch content produces the same hash.
        """
        actual = PatchHasher.compute_hash(patch)
        return actual == expected_hash

    @staticmethod
    def hash_scene_id(scene_id: str, source_node: str) -> str:
        """Compute a composite hash from scene_id and source_node.

        Useful for building cache keys that are scoped to a specific
        extraction source and scene.

        Args:
            scene_id: The target scene identifier.
            source_node: The node identifier that produced the patch.

        Returns:
            SHA-256 hex string (64 characters).
        """
        composite = f"{scene_id}::{source_node}"
        return hashlib.sha256(composite.encode("utf-8")).hexdigest()

    @staticmethod
    def _hash_dict(d: Dict[str, Any]) -> str:
        """Internal: hash a dict via deterministic JSON serialization."""
        raw_json = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    @staticmethod
    def batch_hashes(
        patches: list[SemanticPatch],
    ) -> Dict[str, SemanticPatch]:
        """Compute hashes for a batch of patches.

        Args:
            patches: Iterable of SemanticPatch instances.

        Returns:
            Dict mapping hash → patch for deduplication.
        """
        result: Dict[str, SemanticPatch] = {}
        for p in patches:
            h = PatchHasher.compute_hash(p)
            # First occurrence wins (deterministic dedup).
            if h not in result:
                result[h] = p
        return result