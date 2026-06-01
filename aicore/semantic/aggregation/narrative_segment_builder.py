"""NarrativeSegmentBuilder — deterministic narrative segment construction.

Builds deterministic narrative segments from temporal coherence analysis:
- Groups scenes into coherent narrative units
- Extracts dominant characters, environment, and transition types
- Computes aggregate continuity scores
- Generates deterministic segment IDs with replay-safe hashing

All operations are:
- Deterministic (same input → same segments)
- Replay-safe (serialization preserves grouping)
- Free of randomness/LLM/embeddings
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Sequence

from aicore.semantic.aggregation.continuity_chain_hasher import (
    ContinuityChainHasher,
)
from aicore.semantic.aggregation.temporal_coherence_engine import (
    TemporalCoherenceResult,
    TemporalCoherenceEngine,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class NarrativeSegment:
    """A deterministic narrative segment — a coherent unit of scenes."""

    def __init__(
        self,
        segment_id: str,
        scene_ids: Sequence[str],
        dominant_characters: Sequence[str],
        dominant_environment: str,
        continuity_score: float,
        transition_type: str,
        segment_hash: str,
    ):
        """Initialize narrative segment.

        Args:
            segment_id: Human-readable segment identifier
            scene_ids: Scene IDs belonging to this segment
            dominant_characters: Most frequent character names
            dominant_environment: Most frequent environment
            continuity_score: Average continuity within segment
            transition_type: Type of transition leading into segment
            segment_hash: Deterministic hash of segment contents
        """
        self.segment_id = segment_id
        self.scene_ids = list(scene_ids)
        self.dominant_characters = list(dominant_characters)
        self.dominant_environment = dominant_environment
        self.continuity_score = round(continuity_score, 6)
        self.transition_type = transition_type
        self.segment_hash = segment_hash

    def to_dict(self) -> Dict:
        """Convert to deterministic dict for serialization.

        Returns:
            Stable dict representation
        """
        return {
            "segment_id": self.segment_id,
            "scene_ids": list(self.scene_ids),
            "dominant_characters": list(self.dominant_characters),
            "dominant_environment": self.dominant_environment,
            "continuity_score": self.continuity_score,
            "transition_type": self.transition_type,
            "segment_hash": self.segment_hash,
            "scene_count": len(self.scene_ids),
        }

    @classmethod
    def from_temporal_coherence(
        cls,
        scenes: Sequence[SceneSemantic],
        coherence_result: TemporalCoherenceResult,
        segment_index: int,
        total_segments: int,
    ) -> "NarrativeSegment":
        """Create segment from temporal coherence analysis.

        Args:
            scenes: Original scene sequence (sorted)
            coherence_result: Precomputed temporal coherence
            segment_index: Index of this segment (0-based)
            total_segments: Total number of segments to be created

        Returns:
            NarrativeSegment with deterministic properties
        """
        chains = coherence_result.continuity_chains

        if not chains:
            # No chains: use fallback
            return cls._build_fallback_segment(
                scenes, coherence_result, segment_index,
                total_segments,
            )

        # Use the longest chain as segment basis (deterministic)
        chain = max(chains, key=lambda c: len(c.scene_ids))

        char_counter: Counter = Counter()
        env_counter: Counter = Counter()

        for scene_id in chain.scene_ids:
            scene = next(
                (s for s in scenes if s.scene_id == scene_id), None
            )
            if not scene:
                continue
            for char in scene.characters:
                char_counter[char.normalized_name] += 1
            for env in scene.environments:
                env_counter[env.normalized_name] += 1

        # Top 3 dominant characters
        dominant_chars = [
            char for char, _ in char_counter.most_common(3)
        ]
        dominant_env = (
            env_counter.most_common(1)[0][0]
            if env_counter
            else "unknown"
        )

        # Compute average continuity score within segment
        if len(chain.scene_ids) > 1:
            indices = sorted(
                i for i, s in enumerate(scenes)
                if s.scene_id in chain.scene_ids
            )
            if len(indices) >= 2:
                scores = []
                for idx in range(len(indices) - 1):
                    si = indices[idx]
                    if si < len(coherence_result.continuity_scores):
                        scores.append(
                            coherence_result.continuity_scores[si]
                        )
                avg_score = (
                    sum(scores) / len(scores) if scores else 0.0
                )
            else:
                avg_score = 0.5
        else:
            scene = next(
                (s for s in scenes
                 if s.scene_id == chain.scene_ids[0]),
                None,
            )
            has_content = (
                scene is not None
                and (
                    scene.characters
                    or scene.actions
                    or scene.environments
                )
            )
            avg_score = 1.0 if has_content else 0.5

        # Determine transition type
        if segment_index == 0:
            transition_type = "unknown"
        else:
            first_idx = next(
                (i for i, s in enumerate(scenes)
                 if s.scene_id == chain.scene_ids[0]),
                0,
            )
            if (
                first_idx > 0
                and first_idx <= len(coherence_result.transition_types)
            ):
                transition_type = (
                    coherence_result
                    .transition_types[first_idx - 1]
                    .value
                )
            else:
                transition_type = "scene_boundary"

        # Generate deterministic segment ID
        first_id = (
            chain.scene_ids[0] if chain.scene_ids else "none"
        )
        last_id = (
            chain.scene_ids[-1] if chain.scene_ids else "none"
        )
        segment_id = (
            f"seg_{first_id}_to_{last_id}_x"
            f"{len(chain.scene_ids)}"
        )

        # Generate deterministic hash
        sorted_ids = "|".join(sorted(chain.scene_ids))
        sorted_chars = "|".join(sorted(dominant_chars))
        score_repr = f"{avg_score:.6f}"
        hash_content = (
            f"segment:{segment_id}:{sorted_ids}:"
            f"{sorted_chars}:{dominant_env}:"
            f"{score_repr}:{transition_type}"
        )
        segment_hash = ContinuityChainHasher.compute_deterministic_hash(
            hash_content
        )

        return cls(
            segment_id=segment_id,
            scene_ids=chain.scene_ids,
            dominant_characters=dominant_chars,
            dominant_environment=dominant_env,
            continuity_score=round(avg_score, 6),
            transition_type=transition_type,
            segment_hash=segment_hash,
        )

    @classmethod
    def _build_fallback_segment(
        cls,
        scenes: Sequence[SceneSemantic],
        coherence_result: TemporalCoherenceResult,
        segment_index: int,
        total_segments: int,
    ) -> "NarrativeSegment":
        """Build segment when no continuity chains are detected.

        Groups scenes by temporal adjacency as fallback.
        """
        if len(scenes) == 1:
            scene = scenes[0]
            segment_id = f"seg_{scene.scene_id}"
            chars = [c.normalized_name for c in scene.characters]
            dom_chars = sorted(set(chars)) if chars else []
            dom_env = (
                sorted(
                    {e.normalized_name
                     for e in scene.environments}
                )[0]
                if scene.environments
                else "unknown"
            )
            has_content = (
                scene.characters or scene.actions
                or scene.environments
            )
            internal_score = 1.0 if has_content else 0.5
            transition = (
                "unknown"
                if segment_index == 0
                else "scene_boundary"
            )

            sorted_chars = "|".join(sorted(dom_chars))
            hash_content = (
                f"segment:{segment_id}:{scene.scene_id}:"
                f"{sorted_chars}:{dom_env}:"
                f"{internal_score:.6f}:{transition}"
            )
            segment_hash = ContinuityChainHasher.compute_deterministic_hash(
                hash_content
            )

            return cls(
                segment_id=segment_id,
                scene_ids=[scene.scene_id],
                dominant_characters=dom_chars,
                dominant_environment=dom_env,
                continuity_score=internal_score,
                transition_type=transition,
                segment_hash=segment_hash,
            )

        # Use temporal groups as fallback
        groups = coherence_result.temporal_groups

        if groups and segment_index < len(groups):
            group = groups[segment_index]
            scene_ids = group.scene_ids
        else:
            # Sequential grouping
            sps = max(1, len(scenes) // max(total_segments, 1))
            start_idx = segment_index * sps
            end_idx = min(start_idx + sps, len(scenes))
            scene_ids = [
                scenes[i].scene_id for i in range(start_idx, end_idx)
            ]
            if not scene_ids and scenes:
                scene_ids = [scenes[-1].scene_id]

        if not scene_ids:
            scene_ids = (
                [scenes[0].scene_id] if scenes else ["unknown"]
            )

        segment_scenes = [
            s for s in scenes if s.scene_id in scene_ids
        ]

        char_counter: Counter = Counter()
        env_counter: Counter = Counter()

        for scene in segment_scenes:
            for char in scene.characters:
                char_counter[char.normalized_name] += 1
            for env in scene.environments:
                env_counter[env.normalized_name] += 1

        dominant_chars = [
            char for char, _ in char_counter.most_common(3)
        ]
        dominant_env = (
            env_counter.most_common(1)[0][0]
            if env_counter
            else "unknown"
        )

        # Compute continuity score
        if len(segment_scenes) > 1:
            indices = sorted(
                i for i, s in enumerate(scenes)
                if s.scene_id in scene_ids
            )
            if len(indices) >= 2:
                scores = []
                for idx in range(len(indices) - 1):
                    si = indices[idx]
                    ei = indices[idx + 1]
                    if si < len(coherence_result.continuity_scores):
                        span = coherence_result.continuity_scores[si:ei]
                        if span:
                            scores.append(sum(span) / len(span))
                avg_score = (
                    sum(scores) / len(scores) if scores else 0.0
                )
            else:
                avg_score = 0.5
        else:
            scene = segment_scenes[0] if segment_scenes else None
            has_content = (
                scene is not None
                and (
                    scene.characters
                    or scene.actions
                    or scene.environments
                )
            )
            avg_score = 1.0 if has_content else 0.5

        # Determine transition type
        if segment_index == 0:
            transition_type = "unknown"
        else:
            sps = max(1, len(scenes) // max(total_segments, 1))
            prev_end = (segment_index - 1) * sps
            if (
                0 <= prev_end < len(coherence_result.transition_types)
            ):
                transition_type = (
                    coherence_result.transition_types[prev_end].value
                )
            else:
                transition_type = "scene_boundary"

        first_id = scene_ids[0] if scene_ids else "none"
        last_id = scene_ids[-1] if scene_ids else "none"
        segment_id = (
            f"seg_fallback_{first_id}_to_{last_id}_x"
            f"{len(scene_ids)}"
        )

        sorted_ids = "|".join(sorted(scene_ids))
        sorted_chars = "|".join(sorted(dominant_chars))
        score_repr = f"{avg_score:.6f}"
        hash_content = (
            f"segment:{segment_id}:{sorted_ids}:"
            f"{sorted_chars}:{dominant_env}:"
            f"{score_repr}:{transition_type}"
        )
        segment_hash = ContinuityChainHasher.compute_deterministic_hash(
            hash_content
        )

        return cls(
            segment_id=segment_id,
            scene_ids=scene_ids,
            dominant_characters=dominant_chars,
            dominant_environment=dominant_env,
            continuity_score=round(avg_score, 6),
            transition_type=transition_type,
            segment_hash=segment_hash,
        )


class NarrativeSegmentBuilder:
    """Deterministic builder of narrative segments from scene sequences.

    Uses temporal coherence analysis to group scenes into
    semantically coherent narrative segments.

    Guarantees:
    - Same input scenes → same segments (deterministic)
    - Stable segment IDs across runs
    - Replay-safe serialization
    """

    def __init__(
        self,
        temporal_coherence_engine: Optional[
            "TemporalCoherenceEngine"
        ] = None,
    ):
        """Initialize builder.

        Args:
            temporal_coherence_engine: Custom engine (default: standard)
        """
        self.coherence_engine = (
            temporal_coherence_engine or TemporalCoherenceEngine()
        )

    def build_segments(
        self,
        scenes: Sequence[SceneSemantic],
    ) -> List[NarrativeSegment]:
        """Build deterministic narrative segments from scene sequence.

        Process:
        1. Sort scenes by (video_id, episode_id, start_time)
        2. Run temporal coherence analysis
        3. Extract continuity chains as basis for segments
        4. For each chain, build a NarrativeSegment
        5. Handle gaps/scene not in chains as needed

        Args:
            scenes: Sequence of scenes to segment

        Returns:
            List of NarrativeSegment objects in narrative order
        """
        if not scenes:
            return []

        # Sort deterministically
        sorted_scenes = sorted(
            scenes,
            key=lambda s: (
                s.video_id, s.episode_id or "", s.start_time
            ),
        )

        # Get temporal coherence analysis
        coherence_result = self.coherence_engine.analyze(
            sorted_scenes
        )

        # Build segments from continuity chains
        segments: List[NarrativeSegment] = []
        chains = coherence_result.continuity_chains

        if chains:
            # Sort by start_index for deterministic order
            sorted_chains = sorted(
                chains, key=lambda c: c.start_index
            )

            for i, chain in enumerate(sorted_chains):
                segment = NarrativeSegment.from_temporal_coherence(
                    scenes=sorted_scenes,
                    coherence_result=coherence_result,
                    segment_index=i,
                    total_segments=len(sorted_chains),
                )
                segments.append(segment)
        else:
            # No chains: single segment or temporal groups
            if len(sorted_scenes) == 1:
                segment = NarrativeSegment.from_temporal_coherence(
                    scenes=sorted_scenes,
                    coherence_result=coherence_result,
                    segment_index=0,
                    total_segments=1,
                )
                segments.append(segment)
            else:
                groups = coherence_result.temporal_groups
                if groups:
                    for i, group in enumerate(groups):
                        group_scenes = [
                            s for s in sorted_scenes
                            if s.scene_id in group.scene_ids
                        ]
                        if group_scenes:
                            group_coherence = (
                                self.coherence_engine.analyze(
                                    group_scenes
                                )
                            )
                            segment = (
                                NarrativeSegment
                                .from_temporal_coherence(
                                    scenes=group_scenes,
                                    coherence_result=group_coherence,
                                    segment_index=i,
                                    total_segments=len(groups),
                                )
                            )
                            segments.append(segment)
                else:
                    segment = NarrativeSegment.from_temporal_coherence(
                        scenes=sorted_scenes,
                        coherence_result=coherence_result,
                        segment_index=0,
                        total_segments=1,
                    )
                    segments.append(segment)

        # Ensure deterministic ordering
        segments.sort(key=lambda s: s.segment_id)

        return segments

    def get_narrative_summary(
        self, segments: Sequence[NarrativeSegment]
    ) -> Dict:
        """Get summary statistics for narrative segments.

        Args:
            segments: Sequence of narrative segments

        Returns:
            Summary dict with counts and aggregate stats
        """
        if not segments:
            return {
                "segment_count": 0,
                "total_scenes": 0,
                "avg_continuity": 0.0,
                "unique_characters": 0,
                "unique_environments": 0,
            }

        all_scenes: set = set()
        all_chars: set = set()
        all_envs: set = set()
        continuities = []

        for seg in segments:
            all_scenes.update(seg.scene_ids)
            all_chars.update(seg.dominant_characters)
            if seg.dominant_environment != "unknown":
                all_envs.add(seg.dominant_environment)
            continuities.append(seg.continuity_score)

        return {
            "segment_count": len(segments),
            "total_scenes": len(all_scenes),
            "avg_continuity": (
                sum(continuities) / len(continuities)
                if continuities
                else 0.0
            ),
            "unique_characters": len(all_chars),
            "unique_environments": len(all_envs),
            "segment_ids": [s.segment_id for s in segments],
        }