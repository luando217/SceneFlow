"""TemporalCoherenceEngine — deterministic temporal coherence detection.

Detects deterministic temporal coherence signals between scenes:
- Semantic flow breaks (continuity discontinuities)
- Continuity chains (maximal sequences of strong continuity)
- Stable temporal sequences (temporally grouped scenes)
- Scene transition coherence (how coherent transitions are)

All logic is:
- Deterministic (same input → same output)
- Replay-safe
- Free of randomness/LLM/embeddings/vector search
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from aicore.semantic.aggregation.continuity_chain_hasher import (
    ContinuityChainHasher,
)
from aicore.semantic.aggregation.continuity_detector import ContinuityDetector
from aicore.semantic.aggregation.merge_rule import (
    MergeRuleResult,
    MergeRuleSet,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class TransitionType(str, Enum):
    """Deterministic transition types between consecutive scenes."""

    CONTINUOUS = "continuous"
    """Scenes have strong semantic continuity (character/action overlap)."""

    TEMPORAL_JUMP = "temporal_jump"
    """Large time gap between scenes."""

    CHARACTER_CHANGE = "character_change"
    """Complete character set change."""

    ENVIRONMENT_CHANGE = "environment_change"
    """Environment/location change."""

    ACTION_SHIFT = "action_shift"
    """Significant action pattern change."""

    SCENE_BOUNDARY = "scene_boundary"
    """Clear scene boundary detected."""

    UNKNOWN = "unknown"
    """Cannot determine transition type."""


class FlowBreakType(str, Enum):
    """Types of semantic flow breaks."""

    NONE = "none"
    """No break — scenes are continuous."""

    TEMPORAL = "temporal"
    """Break caused by temporal gap."""

    CHARACTER = "character"
    """Break caused by character change."""

    ENVIRONMENT = "environment"
    """Break caused by environment change."""

    ACTION = "action"
    """Break caused by action shift."""

    MIXED = "mixed"
    """Break caused by multiple factors."""


class ContinuityChain:
    """A maximal sequence of scenes with strong continuity.

    Represents a deterministic continuity chain — scenes that
    form an unbroken narrative thread.
    """

    def __init__(
        self,
        chain_id: str,
        scene_ids: Sequence[str],
        transition_types: Sequence[str],
        scores: Sequence[float],
        start_index: int,
        end_index: int,
        average_score: float,
    ):
        """Initialize continuity chain.

        Args:
            chain_id: Deterministic chain identifier
            scene_ids: Ordered scene IDs in the chain
            transition_types: Transition types between consecutive scenes
            scores: Continuity scores between consecutive scenes
            start_index: Global scene index where chain starts
            end_index: Global scene index where chain ends
            average_score: Average continuity score across chain
        """
        self.chain_id = chain_id
        self.scene_ids = list(scene_ids)
        self.transition_types = list(transition_types)
        self.scores = list(scores)
        self.start_index = start_index
        self.end_index = end_index
        self.average_score = average_score

    def to_dict(self) -> Dict:
        """Convert to deterministic dict for serialization.

        Returns:
            Stable dict representation
        """
        return {
            "chain_id": self.chain_id,
            "scene_ids": list(self.scene_ids),
            "transition_types": list(self.transition_types),
            "scores": [round(s, 6) for s in self.scores],
            "start_index": self.start_index,
            "end_index": self.end_index,
            "average_score": round(self.average_score, 6),
            "scene_count": len(self.scene_ids),
            "hash": self._hash(),
        }

    def _hash(self) -> str:
        """Generate deterministic hash for this chain.

        Returns:
            Stable hex digest
        """
        return ContinuityChainHasher.hash_continuity_chain_v1(
            chain_id=self.chain_id,
            scene_ids=self.scene_ids,
            transition_types=self.transition_types,
            scores=self.scores,
        )


class FlowBreak:
    """Detected semantic flow break between scenes."""

    def __init__(
        self,
        index: int,
        scene_a_id: str,
        scene_b_id: str,
        break_type: FlowBreakType,
        continuity_score: float,
        factors: Dict[str, float],
    ):
        """Initialize flow break.

        Args:
            index: Global index of the break (between scene_i and scene_i+1)
            scene_a_id: Scene before the break
            scene_b_id: Scene after the break
            break_type: Classification of the break
            continuity_score: Raw continuity score (lower = stronger break)
            factors: Detailed factor scores contributing to the break
        """
        self.index = index
        self.scene_a_id = scene_a_id
        self.scene_b_id = scene_b_id
        self.break_type = break_type
        self.continuity_score = continuity_score
        self.factors = dict(factors)

    def to_dict(self) -> Dict:
        """Convert to deterministic dict for serialization.

        Returns:
            Stable dict representation
        """
        return {
            "index": self.index,
            "scene_a_id": self.scene_a_id,
            "scene_b_id": self.scene_b_id,
            "break_type": self.break_type.value,
            "continuity_score": round(self.continuity_score, 6),
            "factors": {k: round(v, 6) for k, v in self.factors.items()},
        }


class TemporalGroup:
    """A group of scenes with stable temporal adjacency."""

    def __init__(
        self,
        video_id: str,
        scene_ids: Sequence[str],
        start_time: float,
        end_time: float,
        gap_ms: float,
    ):
        """Initialize temporal group.

        Args:
            video_id: Video identifier
            scene_ids: Ordered scene IDs in the group
            start_time: Group start time (seconds)
            end_time: Group end time (seconds)
            gap_ms: Maximum temporal gap between consecutive scenes (ms)
        """
        self.video_id = video_id
        self.scene_ids = list(scene_ids)
        self.start_time = start_time
        self.end_time = end_time
        self.gap_ms = gap_ms

    def to_dict(self) -> Dict:
        """Convert to deterministic dict for serialization.

        Returns:
            Stable dict representation
        """
        return {
            "video_id": self.video_id,
            "scene_ids": list(self.scene_ids),
            "start_time": round(self.start_time, 6),
            "end_time": round(self.end_time, 6),
            "gap_ms": round(self.gap_ms, 6),
            "scene_count": len(self.scene_ids),
            "hash": self._hash(),
        }

    def _hash(self) -> str:
        """Generate deterministic hash for this temporal group.

        Returns:
            Stable hex digest
        """
        return ContinuityChainHasher.hash_temporal_group(
            video_id=self.video_id,
            start_time=self.start_time,
            end_time=self.end_time,
            scene_ids=self.scene_ids,
        )


class TemporalCoherenceResult:
    """Complete temporal coherence analysis result.

    Contains all deterministic coherence signals for a scene sequence.
    """

    def __init__(
        self,
        scene_ids: List[str],
        continuity_scores: List[float],
        continuity_chains: List[ContinuityChain],
        flow_breaks: List[FlowBreak],
        temporal_groups: List[TemporalGroup],
        transition_types: List[TransitionType],
        overall_coherence: float,
    ):
        """Initialize result.

        Args:
            scene_ids: All scene IDs in order
            continuity_scores: Continuity scores between consecutive scenes
            continuity_chains: Detected continuity chains
            flow_breaks: Detected flow breaks
            temporal_groups: Temporal adjacency groups
            transition_types: Transition types for each pair
            overall_coherence: Aggregate coherence score [0.0, 1.0]
        """
        self.scene_ids = list(scene_ids)
        self.continuity_scores = [round(s, 6) for s in continuity_scores]
        self.continuity_chains = list(continuity_chains)
        self.flow_breaks = list(flow_breaks)
        self.temporal_groups = list(temporal_groups)
        self.transition_types = list(transition_types)
        self.overall_coherence = round(overall_coherence, 6)

    def to_dict(self) -> Dict:
        """Convert to deterministic dict for serialization.

        Returns:
            Stable dict representation
        """
        return {
            "scene_ids": list(self.scene_ids),
            "continuity_scores": self.continuity_scores,
            "continuity_chains": [c.to_dict() for c in self.continuity_chains],
            "flow_breaks": [b.to_dict() for b in self.flow_breaks],
            "temporal_groups": [g.to_dict() for g in self.temporal_groups],
            "transition_types": [t.value for t in self.transition_types],
            "overall_coherence": self.overall_coherence,
            "scene_pair_count": len(self.scene_ids) - 1,
        }


class TemporalCoherenceEngine:
    """Deterministic temporal coherence analysis engine.

    Analyzes a sequence of scenes to detect:
    - Continuity chains (maximal unbroken narrative threads)
    - Flow breaks (points of discontinuity)
    - Temporal groups (scenes grouped by temporal adjacency)
    - Transition types (deterministic classification)
    - Overall coherence score

    All methods are deterministic and replay-safe.
    """

    # Minimum continuity score to be considered part of a chain
    CHAIN_CONTINUITY_THRESHOLD: float = 0.3

    # Maximum temporal gap (ms) for temporal grouping
    TEMPORAL_GROUP_GAP_MS: float = 1000.0

    # Score below which a flow break is registered
    FLOW_BREAK_THRESHOLD: float = 0.25

    def __init__(
        self,
        continuity_detector: Optional[ContinuityDetector] = None,
        rule_set: Optional[MergeRuleSet] = None,
    ):
        """Initialize engine.

        Args:
            continuity_detector: Custom detector (default: standard)
            rule_set: Custom rule set (default: standard set)
        """
        self.continuity_detector = continuity_detector or ContinuityDetector()
        self.rule_set = rule_set or MergeRuleSet()

    def analyze(
        self,
        scenes: Sequence[SceneSemantic],
    ) -> TemporalCoherenceResult:
        """Run full temporal coherence analysis on scene sequence.

        Args:
            scenes: Ordered sequence of scenes to analyze

        Returns:
            TemporalCoherenceResult with all deterministic signals
        """
        sorted_scenes = sorted(
            scenes,
            key=lambda s: (s.video_id, s.episode_id or "", s.start_time),
        )

        scene_ids = [s.scene_id for s in sorted_scenes]

        # Compute pairwise continuity scores
        continuity_scores = self._compute_continuity_scores(sorted_scenes)

        # Detect transition types
        transition_types = self._detect_transition_types(
            sorted_scenes, continuity_scores
        )

        # Detect flow breaks
        flow_breaks = self._detect_flow_breaks(
            sorted_scenes, scene_ids, continuity_scores
        )

        # Build continuity chains
        chains = self._build_continuity_chains(
            sorted_scenes, scene_ids, continuity_scores, transition_types
        )

        # Build temporal groups
        temporal_groups = self._build_temporal_groups(
            sorted_scenes, scene_ids
        )

        # Compute overall coherence
        overall_coherence = self._compute_overall_coherence(
            continuity_scores, len(scene_ids)
        )

        return TemporalCoherenceResult(
            scene_ids=scene_ids,
            continuity_scores=continuity_scores,
            continuity_chains=chains,
            flow_breaks=flow_breaks,
            temporal_groups=temporal_groups,
            transition_types=transition_types,
            overall_coherence=overall_coherence,
        )

    def _compute_continuity_scores(
        self,
        scenes: List[SceneSemantic],
    ) -> List[float]:
        """Compute deterministic continuity scores for consecutive scene pairs.

        Args:
            scenes: Sorted scene list

        Returns:
            List of continuity scores (len = len(scenes) - 1)
        """
        scores: List[float] = []

        for i in range(len(scenes) - 1):
            scene_a = scenes[i]
            scene_b = scenes[i + 1]

            score_result = self.rule_set.score(scene_a, scene_b)
            continuity_desc = self.continuity_detector.describe_continuity(
                scene_a, scene_b
            )

            # Blend rule-based overall score with continuity score
            rule_score = score_result["overall_score"]
            continuity_score = continuity_desc["score"]

            # Weighted blend (equal weight default)
            blended = (rule_score + continuity_score) / 2.0
            scores.append(blended)

        return scores

    def _detect_transition_types(
        self,
        scenes: List[SceneSemantic],
        continuity_scores: List[float],
    ) -> List[TransitionType]:
        """Detect deterministic transition types for each pair.

        Args:
            scenes: Sorted scene list
            continuity_scores: Computed continuity scores

        Returns:
            List of transition types (len = len(scenes) - 1)
        """
        types: List[TransitionType] = []

        for i in range(len(scenes) - 1):
            scene_a = scenes[i]
            scene_b = scenes[i + 1]
            score = continuity_scores[i]

            transition = self._classify_transition(scene_a, scene_b, score)
            types.append(transition)

        return types

    def _classify_transition(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
        continuity_score: float,
    ) -> TransitionType:
        """Classify transition type between two scenes deterministically.

        Args:
            scene_a: Earlier scene
            scene_b: Later scene
            continuity_score: Computed continuity score

        Returns:
            TransitionType classification
        """
        # High continuity score → continuous
        if continuity_score >= TemporalCoherenceEngine.CHAIN_CONTINUITY_THRESHOLD:
            return TransitionType.CONTINUOUS

        # Check for temporal jump
        if (
            scene_a.video_id == scene_b.video_id
            and scene_a.end_time is not None
            and scene_b.start_time is not None
        ):
            gap_ms = (scene_b.start_time - scene_a.end_time) * 1000.0
            if gap_ms > TemporalCoherenceEngine.TEMPORAL_GROUP_GAP_MS * 2:
                return TransitionType.TEMPORAL_JUMP

        # Check for character change
        chars_a = {c.normalized_name for c in scene_a.characters}
        chars_b = {c.normalized_name for c in scene_b.characters}
        if chars_a and chars_b:
            overlap = chars_a & chars_b
            union = chars_a | chars_b
            ratio = len(overlap) / len(union) if union else 0.0
            if ratio < 0.25 and len(chars_a) > 0 and len(chars_b) > 0:
                return TransitionType.CHARACTER_CHANGE

        # Check for environment change
        envs_a = {e.normalized_name for e in scene_a.environments}
        envs_b = {e.normalized_name for e in scene_b.environments}
        if envs_a and envs_b:
            overlap = envs_a & envs_b
            if not overlap:
                return TransitionType.ENVIRONMENT_CHANGE

        # Check for action shift
        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}
        if actions_a and actions_b:
            overlap = actions_a & actions_b
            union = actions_a | actions_b
            ratio = len(overlap) / len(union) if union else 0.0
            if ratio < 0.2:
                return TransitionType.ACTION_SHIFT

        # Check merge rule decision
        decision, _ = self.rule_set.apply(scene_a, scene_b)
        if decision == MergeRuleResult.SEPARATE:
            return TransitionType.SCENE_BOUNDARY

        return TransitionType.UNKNOWN

    def _detect_flow_breaks(
        self,
        scenes: List[SceneSemantic],
        scene_ids: List[str],
        continuity_scores: List[float],
    ) -> List[FlowBreak]:
        """Detect semantic flow breaks deterministically.

        A flow break occurs when continuity score drops below
        FLOW_BREAK_THRESHOLD or the merge rule returns SEPARATE.

        Args:
            scenes: Sorted scene list
            scene_ids: Scene IDs in order
            continuity_scores: Computed continuity scores

        Returns:
            List of detected FlowBreak objects
        """
        breaks: List[FlowBreak] = []

        for i in range(len(scenes) - 1):
            score = continuity_scores[i]
            scene_a = scenes[i]
            scene_b = scenes[i + 1]

            if score >= TemporalCoherenceEngine.FLOW_BREAK_THRESHOLD:
                continue

            # Classify the break type
            break_type = self._classify_break_type(scene_a, scene_b)

            # Gather factor scores
            factors = self._get_break_factors(scene_a, scene_b)

            breaks.append(FlowBreak(
                index=i,
                scene_a_id=scene_ids[i],
                scene_b_id=scene_ids[i + 1],
                break_type=break_type,
                continuity_score=score,
                factors=factors,
            ))

        return breaks

    def _classify_break_type(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> FlowBreakType:
        """Classify flow break type deterministically.

        Args:
            scene_a: Earlier scene
            scene_b: Later scene

        Returns:
            FlowBreakType classification
        """
        active_factors: List[FlowBreakType] = []

        # Temporal check
        if (
            scene_a.video_id == scene_b.video_id
            and scene_a.end_time is not None
            and scene_b.start_time is not None
        ):
            gap_ms = (scene_b.start_time - scene_a.end_time) * 1000.0
            if gap_ms > TemporalCoherenceEngine.TEMPORAL_GROUP_GAP_MS:
                active_factors.append(FlowBreakType.TEMPORAL)

        # Character check
        chars_a = {c.normalized_name for c in scene_a.characters}
        chars_b = {c.normalized_name for c in scene_b.characters}
        if chars_a and chars_b:
            overlap = chars_a & chars_b
            if not overlap:
                active_factors.append(FlowBreakType.CHARACTER)

        # Environment check
        envs_a = {e.normalized_name for e in scene_a.environments}
        envs_b = {e.normalized_name for e in scene_b.environments}
        if envs_a and envs_b:
            overlap = envs_a & envs_b
            if not overlap:
                active_factors.append(FlowBreakType.ENVIRONMENT)

        # Action check
        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}
        if actions_a and actions_b:
            if not (actions_a & actions_b):
                active_factors.append(FlowBreakType.ACTION)

        if len(active_factors) >= 2:
            return FlowBreakType.MIXED
        elif len(active_factors) == 1:
            return active_factors[0]
        else:
            return FlowBreakType.NONE

    def _get_break_factors(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> Dict[str, float]:
        """Gather detailed factor scores contributing to a break.

        Args:
            scene_a: Earlier scene
            scene_b: Later scene

        Returns:
            Dict mapping factor name to score
        """
        factors: Dict[str, float] = {}

        # Character overlap ratio
        chars_a = {c.normalized_name for c in scene_a.characters}
        chars_b = {c.normalized_name for c in scene_b.characters}
        if chars_a or chars_b:
            union = chars_a | chars_b
            overlap = chars_a & chars_b
            factors["character_overlap"] = len(overlap) / len(union) if union else 0.0
        else:
            factors["character_overlap"] = 0.0

        # Action overlap ratio
        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}
        if actions_a or actions_b:
            union = actions_a | actions_b
            overlap = actions_a & actions_b
            factors["action_overlap"] = len(overlap) / len(union) if union else 0.0
        else:
            factors["action_overlap"] = 0.0

        # Environment overlap
        envs_a = {e.normalized_name for e in scene_a.environments}
        envs_b = {e.normalized_name for e in scene_b.environments}
        if envs_a or envs_b:
            union = envs_a | envs_b
            overlap = envs_a & envs_b
            factors["environment_continuity"] = (
                len(overlap) / len(union) if union else 0.0
            )
        else:
            factors["environment_continuity"] = 0.0

        # Temporal proximity (normalized)
        if (
            scene_a.video_id == scene_b.video_id
            and scene_a.end_time is not None
            and scene_b.start_time is not None
        ):
            gap_ms = (scene_b.start_time - scene_a.end_time) * 1000.0
            factors["temporal_proximity"] = max(
                0.0, 1.0 - (gap_ms / TemporalCoherenceEngine.TEMPORAL_GROUP_GAP_MS)
            )
        else:
            factors["temporal_proximity"] = 0.0

        # Dialogue continuity
        has_dialogue_a = bool(scene_a.dialogue)
        has_dialogue_b = bool(scene_b.dialogue)
        factors["dialogue_continuity"] = 1.0 if (
            has_dialogue_a and has_dialogue_b
        ) else 0.0

        return factors

    def _build_continuity_chains(
        self,
        scenes: List[SceneSemantic],
        scene_ids: List[str],
        continuity_scores: List[float],
        transition_types: List[TransitionType],
    ) -> List[ContinuityChain]:
        """Build maximal continuity chains deterministically.

        A continuity chain is a maximal consecutive subsequence where
        all continuity scores >= CHAIN_CONTINUITY_THRESHOLD.

        Args:
            scenes: Sorted scene list
            scene_ids: Scene IDs in order
            continuity_scores: Computed continuity scores
            transition_types: Transition types for each pair

        Returns:
            List of ContinuityChain objects
        """
        if len(scenes) <= 1:
            return []

        chains: List[ContinuityChain] = []
        chain_start: Optional[int] = None
        chain_scene_ids: List[str] = []
        chain_types: List[str] = []
        chain_scores: List[float] = []

        for i in range(len(scenes) - 1):
            score = continuity_scores[i]
            in_chain = score >= TemporalCoherenceEngine.CHAIN_CONTINUITY_THRESHOLD

            if in_chain:
                if chain_start is None:
                    # Start new chain
                    chain_start = i
                    chain_scene_ids = [scene_ids[i], scene_ids[i + 1]]
                    chain_types = [transition_types[i].value]
                    chain_scores = [score]
                else:
                    # Extend chain
                    chain_scene_ids.append(scene_ids[i + 1])
                    chain_types.append(transition_types[i].value)
                    chain_scores.append(score)
            else:
                if chain_start is not None and len(chain_scene_ids) >= 2:
                    # Finalize chain
                    chain = self._finalize_chain(
                        chain_start=chain_start,
                        end_index=i,
                        scene_ids=chain_scene_ids,
                        transition_types=chain_types,
                        scores=chain_scores,
                    )
                    chains.append(chain)
                    chain_start = None
                    chain_scene_ids = []
                    chain_types = []
                    chain_scores = []

        # Finalize last chain if still open
        if chain_start is not None and len(chain_scene_ids) >= 2:
            chain = self._finalize_chain(
                chain_start=chain_start,
                end_index=len(scenes) - 1,
                scene_ids=chain_scene_ids,
                transition_types=chain_types,
                scores=chain_scores,
            )
            chains.append(chain)

        return chains

    def _finalize_chain(
        self,
        chain_start: int,
        end_index: int,
        scene_ids: List[str],
        transition_types: List[str],
        scores: List[float],
    ) -> ContinuityChain:
        """Create a finalized ContinuityChain with deterministic ID.

        Args:
            chain_start: Global start index
            end_index: Global end index (inclusive)
            scene_ids: Scene IDs in the chain
            transition_types: Transition type values
            scores: Continuity scores

        Returns:
            ContinuityChain with stable ID and hash
        """
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Generate deterministic chain ID from first and last scene
        first_id = scene_ids[0] if scene_ids else "none"
        last_id = scene_ids[-1] if scene_ids else "none"
        chain_id = f"chain_{first_id}_to_{last_id}_x{len(scene_ids)}"

        return ContinuityChain(
            chain_id=chain_id,
            scene_ids=scene_ids,
            transition_types=transition_types,
            scores=scores,
            start_index=chain_start,
            end_index=end_index,
            average_score=avg_score,
        )

    def _build_temporal_groups(
        self,
        scenes: List[SceneSemantic],
        scene_ids: List[str],
    ) -> List[TemporalGroup]:
        """Build temporal adjacency groups deterministically.

        Groups consecutive scenes within the same video that are
        within TEMPORAL_GROUP_GAP_MS of each other.

        Args:
            scenes: Sorted scene list
            scene_ids: Scene IDs in order

        Returns:
            List of TemporalGroup objects
        """
        if len(scenes) <= 1:
            return []

        groups: List[TemporalGroup] = []
        group_start_idx: int = 0
        max_gap_ms: float = 0.0

        def _finalize_temporal_group(
            start_idx: int,
            end_idx: int,
            current_max_gap: float,
        ) -> TemporalGroup:
            """Create TemporalGroup for a range of scene indices."""
            group_scenes = scenes[start_idx : end_idx + 1]
            group_ids = scene_ids[start_idx : end_idx + 1]
            first_scene = group_scenes[0]
            last_scene = group_scenes[-1]

            return TemporalGroup(
                video_id=first_scene.video_id,
                scene_ids=group_ids,
                start_time=first_scene.start_time,
                end_time=last_scene.end_time,
                gap_ms=current_max_gap,
            )

        for i in range(1, len(scenes)):
            scene_prev = scenes[i - 1]
            scene_curr = scenes[i]

            # Check if temporal gap allows grouping
            if (
                scene_prev.video_id == scene_curr.video_id
                and scene_prev.end_time is not None
                and scene_curr.start_time is not None
            ):
                gap_ms = (scene_curr.start_time - scene_prev.end_time) * 1000.0

                if gap_ms <= TemporalCoherenceEngine.TEMPORAL_GROUP_GAP_MS:
                    # Extend current group
                    max_gap_ms = max(max_gap_ms, gap_ms)
                    continue

            # Finalize current group
            if i - 1 > group_start_idx or (
                i - 1 == group_start_idx and (i - 1) == 0
            ):
                group = _finalize_temporal_group(
                    group_start_idx, i - 1, max_gap_ms
                )
                groups.append(group)

            # Start new group
            group_start_idx = i
            max_gap_ms = 0.0

        # Finalize last group if it has at least 2 scenes
        if len(scenes) - 1 > group_start_idx:
            group = _finalize_temporal_group(
                group_start_idx, len(scenes) - 1, max_gap_ms
            )
            groups.append(group)

        # If no groups were formed but we have scenes, create singleton groups
        if not groups and len(scenes) >= 2:
            group = _finalize_temporal_group(0, len(scenes) - 1, max_gap_ms)
            groups.append(group)

        return groups

    def _compute_overall_coherence(
        self,
        continuity_scores: List[float],
        num_scenes: int,
    ) -> float:
        """Compute aggregate coherence score.

        Args:
            continuity_scores: Continuity scores for each pair
            num_scenes: Total number of scenes

        Returns:
            Coherence score [0.0, 1.0]
        """
        if not continuity_scores or num_scenes <= 1:
            return 1.0

        # Average of all continuity scores
        avg_score = sum(continuity_scores) / len(continuity_scores)

        # Penalize for breaks (count scores below threshold)
        num_breaks = sum(
            1 for s in continuity_scores
            if s < TemporalCoherenceEngine.FLOW_BREAK_THRESHOLD
        )
        break_penalty = num_breaks / len(continuity_scores)

        # Blend: average score penalized by break density
        coherence = avg_score * (1.0 - (break_penalty * 0.5))

        return max(0.0, min(1.0, coherence))

    def get_scene_chains(
        self, scenes: Sequence[SceneSemantic]
    ) -> List[ContinuityChain]:
        """Get only the continuity chains (lightweight query).

        Args:
            scenes: Ordered sequence of scenes

        Returns:
            List of continuity chains
        """
        result = self.analyze(scenes)
        return result.continuity_chains

    def get_flow_breaks(
        self, scenes: Sequence[SceneSemantic]
    ) -> List[FlowBreak]:
        """Get only the flow breaks (lightweight query).

        Args:
            scenes: Ordered sequence of scenes

        Returns:
            List of flow breaks
        """
        result = self.analyze(scenes)
        return result.flow_breaks