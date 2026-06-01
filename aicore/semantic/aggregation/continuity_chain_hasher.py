"""ContinuityChainHasher — replay-safe deterministic hashing for continuity artifacts.

Provides stable, deterministic hash generation for:
- Continuity chains (ordered sequences of scene pairs)
- Temporal groups (scene groupings based on temporal adjacency)
- Narrative segments (higher-level narrative groupings)

All hashes are:
- Deterministic (same input → same hash across runs/machines)
- Replay-safe (can be serialized/deserialized and produce same hash)
- Non-cryptographic (for identity, not security)
- Free of randomness/LLM/embeddings
"""

from __future__ import annotations

import hashlib
from typing import List, Sequence


def _stable_hash(content: str) -> str:
    """Generate stable SHA-256 hex digest from string content.

    Args:
        content: String content to hash

    Returns:
        Fixed-length hex digest (64 chars)
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sorted_items(items: Sequence[str]) -> List[str]:
    """Return deterministically sorted list of items.

    Args:
        items: Unsorted sequence of strings

    Returns:
        Sorted list (stable across runs)
    """
    return sorted(items)


class ContinuityChainHasher:
    """Replay-safe deterministic hashing for continuity chains and segments.

    All hash methods are pure functions with no side effects, randomness,
    or external dependencies.
    """

    @staticmethod
    def compute_deterministic_hash(content: str) -> str:
        """Compute a deterministic SHA-256 hash from string content.

        Public wrapper around the internal _stable_hash for use
        by other modules in the aggregation pipeline.

        Args:
            content: String content to hash

        Returns:
            Stable hex digest (64 chars)
        """
        return _stable_hash(content)

    @staticmethod
    def hash_chain(
        scene_ids: Sequence[str],
    ) -> str:
        """Generate deterministic hash for a continuity chain.

        A continuity chain is an ordered sequence of scene IDs that
        form a continuous narrative flow.

        Args:
            scene_ids: Ordered scene IDs in the chain

        Returns:
            Stable hex digest
        """
        sorted_ids = _sorted_items(scene_ids)
        content = "|".join(sorted_ids)
        return _stable_hash(f"chain:{content}")

    @staticmethod
    def hash_temporal_group(
        video_id: str,
        start_time: float,
        end_time: float,
        scene_ids: Sequence[str],
    ) -> str:
        """Generate deterministic hash for a temporal group.

        Temporal groups are scenes grouped by temporal adjacency
        within the same video.

        Args:
            video_id: Video identifier
            start_time: Group start time (seconds)
            end_time: Group end time (seconds)
            scene_ids: Ordered scene IDs in the group

        Returns:
            Stable hex digest
        """
        sorted_ids = _sorted_items(scene_ids)
        # Use fixed-precision float representation for deterministic hashing
        start_repr = f"{start_time:.6f}"
        end_repr = f"{end_time:.6f}"
        ids_str = "|".join(sorted_ids)
        content = f"temporal:{video_id}:{start_repr}:{end_repr}:{ids_str}"
        return _stable_hash(content)

    @staticmethod
    def hash_narrative_segment(
        segment_id: str,
        scene_ids: Sequence[str],
        dominant_characters: Sequence[str],
        dominant_environment: str,
        continuity_score: float,
        transition_type: str,
    ) -> str:
        """Generate deterministic hash for a narrative segment.

        Args:
            segment_id: Segment identifier
            scene_ids: Scene IDs belonging to this segment
            dominant_characters: Dominant character normalized names
            dominant_environment: Dominant environment location
            continuity_score: Aggregated continuity score [0.0, 1.0]
            transition_type: Type of transition at segment boundary

        Returns:
            Stable hex digest
        """
        sorted_scene_ids = _sorted_items(scene_ids)
        sorted_chars = _sorted_items(dominant_characters)
        score_repr = f"{continuity_score:.6f}"
        ids_str = "|".join(sorted_scene_ids)
        chars_str = "|".join(sorted_chars)
        content = (
            f"segment:{segment_id}:{ids_str}:"
            f"{chars_str}:{dominant_environment}:"
            f"{score_repr}:{transition_type}"
        )
        return _stable_hash(content)

    @staticmethod
    def hash_scene_pair(
        scene_a_id: str,
        scene_b_id: str,
    ) -> str:
        """Generate deterministic hash for a scene adjacency pair.

        The hash is order-independent (scene_a, scene_b) produces
        same hash as (scene_b, scene_a).

        Args:
            scene_a_id: First scene ID
            scene_b_id: Second scene ID

        Returns:
            Stable hex digest
        """
        sorted_ids = _sorted_items([scene_a_id, scene_b_id])
        content = f"pair:{sorted_ids[0]}|{sorted_ids[1]}"
        return _stable_hash(content)

    @staticmethod
    def hash_continuity_chain_v1(
        chain_id: str,
        scene_ids: Sequence[str],
        transition_types: Sequence[str],
        scores: Sequence[float],
    ) -> str:
        """Generate deterministic v1 hash for a full continuity chain.

        Args:
            chain_id: Chain identifier
            scene_ids: Ordered scene IDs in the chain
            transition_types: Transition types between consecutive scenes
            scores: Continuity scores between consecutive scenes

        Returns:
            Stable hex digest
        """
        ids_str = "|".join(scene_ids)
        types_str = "|".join(transition_types)
        # Use fixed-precision floats for deterministic hashing
        scores_str = "|".join(f"{s:.6f}" for s in scores)
        content = f"chain_v1:{chain_id}:{ids_str}:{types_str}:{scores_str}"
        return _stable_hash(content)