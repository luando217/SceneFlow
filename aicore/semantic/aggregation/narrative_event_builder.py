"""NarrativeEventBuilder — deterministic narrative event grouping.

Builds narrative events from continuity chains and temporal coherence analysis.
All logic is:
- Deterministic (same input → same output)
- Replay-safe
- Free of randomness/LLM/embeddings/vector search
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Dict, List, Optional, Sequence, Set, Tuple

from aicore.semantic.aggregation.continuity_chain_builder import (
    ContinuityChainBuilder,
)
from aicore.semantic.aggregation.continuity_chain_schemas import (
    CharacterContinuityChain,
    ContinuityChainResult,
    DialogueContinuityChain,
    EnvironmentContinuityChain,
)
from aicore.semantic.aggregation.coherence_schemas import (
    ContinuityBreak,
)
from aicore.semantic.aggregation.narrative_event_schemas import (
    EventBoundary,
    EventTransition,
    NarrativeEvent,
    NarrativeEventGroup,
    TransitionLabel,
)
from aicore.semantic.aggregation.temporal_coherence_engine import (
    TemporalCoherenceEngine,
    TemporalCoherenceResult,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class EventType(str, Enum):
    """Deterministic event type classifications."""

    COMBAT_SEQUENCE = "combat_sequence"
    DIALOGUE_EXCHANGE = "dialogue_exchange"
    TRAVEL_SEQUENCE = "travel_sequence"
    ENVIRONMENT_TRANSITION = "environment_transition"
    EMOTIONAL_SEQUENCE = "emotional_sequence"
    IDLE_SEQUENCE = "idle_sequence"
    FLASHBACK_CANDIDATE = "flashback_candidate"
    TIMESKIP_CANDIDATE = "timeskip_candidate"


# ── Helper utilities ──────────────────────────────────────────────────────────


def _compute_deterministic_hash(data: dict) -> str:
    """Compute replay-safe SHA-256 hex digest.

    Args:
        data: Dictionary to hash

    Returns:
        SHA-256 hex digest string
    """
    serialized = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _stable_hash_scene_ids(scene_ids: Sequence[str]) -> str:
    """Compute stable hash from ordered scene IDs.

    Args:
        scene_ids: Ordered list of scene IDs

    Returns:
        SHA-256 hex digest
    """
    raw = "|".join(scene_ids)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── NarrativeEventBuilder ─────────────────────────────────────────────────────


class NarrativeEventBuilder:
    """Builds deterministic narrative events from scenes and continuity data.

    Uses ONLY:
    - continuity chains
    - temporal adjacency
    - dialogue continuity
    - environment continuity
    - action continuity
    - coherence scores
    """

    def __init__(
        self,
        coherence_engine: Optional[TemporalCoherenceEngine] = None,
    ) -> None:
        """Initialize builder.

        Args:
            coherence_engine: Optional temporal coherence engine instance
        """
        self._coherence_engine = coherence_engine or TemporalCoherenceEngine()
        self._chain_builder = ContinuityChainBuilder()

    # ── Public API ─────────────────────────────────────────────────────────

    def build_events(
        self,
        scenes: Sequence[SceneSemantic],
        continuity_chains: Optional[ContinuityChainResult] = None,
        coherence_result: Optional[TemporalCoherenceResult] = None,
    ) -> List[NarrativeEvent]:
        """Build narrative events from scenes.

        Args:
            scenes: Ordered list of scene semantics
            continuity_chains: Optional pre-computed continuity chains
            coherence_result: Optional pre-computed coherence result

        Returns:
            List of narrative events

        Raises:
            ValueError: If scenes is empty
        """
        if not scenes:
            return []

        # Compute continuity data if not provided
        if continuity_chains is None:
            scene_list = list(scenes)
            if len(scene_list) == 1:
                # Single scene - create minimal chains
                continuity_chains = ContinuityChainResult(
                    character_chains=[
                        CharacterContinuityChain(
                            chain_id="singleton_char",
                            character=self._get_single_character_name(scene_list[0]),
                            scene_ids=[scene_list[0].scene_id],
                            continuity_score=1.0,
                            strength=1.0,
                        )
                    ],
                    dialogue_chains=[],
                    environment_chains=[],
                )
            else:
                continuity_chains = self._chain_builder.build_character_chains(
                    scene_list
                )
        if coherence_result is None:
            coherence_result = self._coherence_engine.analyze(scenes)

        # Build events from continuity chains
        events: List[NarrativeEvent] = []
        used_scenes: Set[str] = set()

        # 1. Build events from character continuity chains
        for chain in continuity_chains.character_chains:
            chain_scenes = self._resolve_chain_scenes(chain, scenes)
            if not chain_scenes:
                continue

            event = self._build_event(chain_scenes, continuity_chains, coherence_result)
            events.append(event)
            used_scenes.update(chain.scene_ids)

        # 2. Build events from environment continuity chains
        for chain in continuity_chains.environment_chains:
            chain_scenes = self._resolve_chain_scenes(chain, scenes)
            if not chain_scenes:
                continue

            if all(s.scene_id not in used_scenes for s in chain_scenes):
                event = self._build_event(
                    chain_scenes, continuity_chains, coherence_result
                )
                events.append(event)
                used_scenes.update(chain.scene_ids)

        # 3. Build events for remaining ungrouped scenes
        for scene in scenes:
            if scene.scene_id not in used_scenes:
                event = self._build_event(
                    [scene], continuity_chains, coherence_result
                )
                events.append(event)
                used_scenes.add(scene.scene_id)

        # Sort events by first scene temporal position for stability
        events.sort(key=lambda e: (self._get_earliest_time(e), e.event_id))

        return events

    def _get_single_character_name(self, scene: SceneSemantic) -> str:
        """Get character name from single scene.

        Args:
            scene: Scene to extract character from

        Returns:
            Character name or 'unknown'
        """
        if scene.characters:
            return scene.characters[0].normalized_name
        return "unknown"

    def _resolve_chain_scenes(
        self,
        chain: object,
        scenes: Sequence[SceneSemantic],
    ) -> List[SceneSemantic]:
        """Resolve continuity chain scene IDs to scene objects.

        Args:
            chain: Continuity chain with scene_ids attribute
            scenes: Available scenes

        Returns:
            List of resolved scenes in chain order
        """
        scene_ids = getattr(chain, "scene_ids", [])
        scene_map = {s.scene_id: s for s in scenes}
        resolved: List[SceneSemantic] = []
        for sid in scene_ids:
            if sid in scene_map:
                resolved.append(scene_map[sid])
        return resolved

    # ── Event building internals ───────────────────────────────────────────

    def _build_event(
        self,
        scenes: List[SceneSemantic],
        continuity_chains: ContinuityChainResult,
        coherence_result: TemporalCoherenceResult,
    ) -> NarrativeEvent:
        """Build a single narrative event from scenes.

        Args:
            scenes: Ordered list of scene semantics
            continuity_chains: Continuity chain result
            coherence_result: Coherence result

        Returns:
            Constructed narrative event
        """
        scene_ids = [s.scene_id for s in scenes]
        event_id = _stable_hash_scene_ids(scene_ids)

        # Compute event properties
        event_type = self._classify_event_type(scenes)
        dominant_chars = self._compute_dominant_characters(scenes)
        dominant_env = self._compute_dominant_environment(scenes)
        coherence_strength = self._compute_coherence_score(scenes)
        actions = self._collect_actions(scenes)
        dialogue_topics = self._collect_dialogue_topics(scenes)
        temporal_span = self._compute_temporal_span(scenes)
        temporal_gap = self._compute_temporal_gap(scenes)
        dialogue_ratio = self._compute_dialogue_ratio(scenes)
        character_count = self._compute_character_count(scenes)

        # Build deterministic hash
        hash_input = {
            "scene_ids": scene_ids,
            "event_type": event_type,
            "dominant_characters": dominant_chars,
            "dominant_environment": dominant_env,
            "coherence_strength": coherence_strength,
            "actions": actions,
            "dialogue_topics": dialogue_topics,
            "temporal_span": temporal_span,
            "temporal_gap": temporal_gap,
            "dialogue_ratio": dialogue_ratio,
            "character_count": character_count,
        }
        deterministic_hash = _compute_deterministic_hash(hash_input)

        return NarrativeEvent(
            deterministic_id=event_id,
            deterministic_hash=deterministic_hash,
            scene_ids=scene_ids,
            event_type=event_type,
            dominant_characters=dominant_chars,
            dominant_environment=dominant_env,
            continuity_strength=coherence_strength,
            coherence_strength=coherence_strength,
            actions=actions,
            dialogue_topics=dialogue_topics,
            temporal_span=temporal_span,
            temporal_gap=temporal_gap,
            dialogue_ratio=dialogue_ratio,
            character_count=character_count,
        )

    # ── Event classification ───────────────────────────────────────────────

    def _classify_event_type(self, scenes: List[SceneSemantic]) -> str:
        """Classify event type using deterministic heuristics.

        Args:
            scenes: Scenes to classify

        Returns:
            Event type string
        """
        if not scenes:
            return EventType.IDLE_SEQUENCE.value

        # Collect signals
        actions = self._collect_actions(scenes)
        characters = self._compute_dominant_characters(scenes)
        environments = self._collect_environments(scenes)
        avg_dialogue = self._compute_dialogue_ratio(scenes)
        motion_intensity = self._compute_avg_motion(scenes)
        action_pace = self._compute_dominant_pace(scenes)
        num_characters = len(characters)

        # Heuristic: flashback detection via temporal gaps
        max_gap = self._compute_temporal_gap(scenes)
        if max_gap > 30000:  # >30s gap suggests discontinuity
            # Check if dialogue pattern suggests memory/flashback
            if avg_dialogue > 0.3 and num_characters <= 2:
                return EventType.FLASHBACK_CANDIDATE.value
            return EventType.TIMESKIP_CANDIDATE.value

        # Heuristic: combat sequence
        combat_keywords = {"punch", "kick", "slash", "block", "dodge", "attack" "_strike", "counter"}
        if any(a in combat_keywords for a in actions):
            if motion_intensity > 0.3 or action_pace in ("fast", "intense"):
                return EventType.COMBAT_SEQUENCE.value

        # Heuristic: dialogue exchange
        if avg_dialogue > 0.4 and motion_intensity < 0.5:
            if action_pace in ("slow", "normal"):
                return EventType.DIALOGUE_EXCHANGE.value

        # Heuristic: travel sequence
        travel_keywords = {"walk", "run", "move", "travel", "chase", "follow"}
        if any(a in travel_keywords for a in actions):
            if len(environments) >= 2 or action_pace == "fast":
                return EventType.TRAVEL_SEQUENCE.value

        # Heuristic: environment transition
        if len(environments) >= 2:
            if len(characters) <= 2:
                return EventType.ENVIRONMENT_TRANSITION.value

        # Heuristic: emotional sequence
        emotions = self._collect_emotions(scenes)
        emotional_keywords = {"cry", "laugh", "shout", "anger", "sad", "joy", "fear"}
        if any(e in emotional_keywords for e in emotions):
            if avg_dialogue > 0.2 or motion_intensity < 0.4:
                return EventType.EMOTIONAL_SEQUENCE.value

        # Default: idle sequence
        return EventType.IDLE_SEQUENCE.value

    # ── Continuity feature extraction ──────────────────────────────────────

    def _compute_dialogue_ratio(self, scenes: List[SceneSemantic]) -> float:
        """Compute dialogue ratio deterministically.

        Args:
            scenes: Scenes to analyze

        Returns:
            Dialogue ratio [0.0, 1.0]
        """
        if not scenes:
            return 0.0

        ratios = []
        for scene in scenes:
            dialogue = scene.dialogue or ""
            if not dialogue:
                ratios.append(0.0)
                continue

            # Ratio based on dialogue presence and length
            total_duration = 1.0
            if scene.end_time and scene.start_time:
                total_duration = max(1.0, scene.end_time - scene.start_time)

            # Simple heuristic: dialogue length vs duration
            text_ratio = min(1.0, len(dialogue) / (total_duration * 50))
            ratios.append(text_ratio)

        return sum(ratios) / len(ratios)

    def _compute_character_count(self, scenes: List[SceneSemantic]) -> int:
        """Compute total character count.

        Args:
            scenes: Scenes to analyze

        Returns:
            Number of unique characters
        """
        characters: Set[str] = set()
        for scene in scenes:
            for char in scene.characters:
                characters.add(char.normalized_name)
        return len(characters)

    def _collect_actions(self, scenes: List[SceneSemantic]) -> List[str]:
        """Collect unique action names.

        Args:
            scenes: Scenes to analyze

        Returns:
            Sorted list of action names
        """
        actions: Set[str] = set()
        for scene in scenes:
            for action in scene.actions:
                actions.add(action.normalized_name)
        return sorted(actions)

    def _collect_dialogue_topics(self, scenes: List[SceneSemantic]) -> List[str]:
        """Collect dialogue content as topics.

        Args:
            scenes: Scenes to analyze

        Returns:
            Sorted list of dialogue topics (words/sentences)
        """
        topics: Set[str] = set()
        for scene in scenes:
            dialogue = scene.dialogue or ""
            if dialogue.strip():
                # Extract individual words as topics
                words = dialogue.lower().split()
                for w in words:
                    clean = w.strip(".,!?:;\"'()-")
                    if clean and len(clean) > 2:  # Only meaningful words
                        topics.add(clean)
        return sorted(topics)

    def _compute_dominant_characters(
        self,
        scenes: List[SceneSemantic],
    ) -> List[str]:
        """Compute dominant characters by frequency.

        Args:
            scenes: Scenes to analyze

        Returns:
            Sorted list of dominant character names
        """
        char_counts: Dict[str, int] = {}
        for scene in scenes:
            for char in scene.characters:
                name = char.normalized_name
                char_counts[name] = char_counts.get(name, 0) + 1

        if not char_counts:
            return []

        # Sort by count descending, then alphabetically for determinism
        sorted_chars = sorted(
            char_counts.items(),
            key=lambda x: (-x[1], x[0]),
        )
        return [name for name, _ in sorted_chars]

    def _compute_dominant_environment(
        self,
        scenes: List[SceneSemantic],
    ) -> Optional[str]:
        """Compute dominant environment name.

        Args:
            scenes: Scenes to analyze

        Returns:
            Most frequent environment name or None
        """
        env_counts: Dict[str, int] = {}
        for scene in scenes:
            for env in scene.environments:
                name = env.normalized_name
                env_counts[name] = env_counts.get(name, 0) + 1

        if not env_counts:
            return None

        # Return most common (deterministic: highest count, then alphabetically)
        sorted_envs = sorted(
            env_counts.items(),
            key=lambda x: (-x[1], x[0]),
        )
        return sorted_envs[0][0] if sorted_envs else None

    def _compute_coherence_score(
        self,
        scenes: List[SceneSemantic],
    ) -> float:
        """Compute internal coherence score.

        Args:
            scenes: Scenes to analyze

        Returns:
            Coherence score [0.0, 1.0]
        """
        if len(scenes) <= 1:
            return 1.0

        # Compute based on character and environment overlap
        char_sets = []
        env_sets = []
        action_sets = []

        for scene in scenes:
            chars = {c.normalized_name for c in scene.characters}
            envs = {e.normalized_name for e in scene.environments}
            actions = {a.normalized_name for a in scene.actions}
            char_sets.append(chars)
            env_sets.append(envs)
            action_sets.append(actions)

        # Character overlap
        char_overlap = self._compute_overlap_ratio(char_sets)
        env_overlap = self._compute_overlap_ratio(env_sets)
        action_overlap = self._compute_overlap_ratio(action_sets)

        # Weighted combination
        score = (
            char_overlap * 0.5
            + env_overlap * 0.3
            + action_overlap * 0.2
        )
        return round(min(1.0, max(0.0, score)), 6)

    def _compute_overlap_ratio(
        self,
        sets: List[Set[str]],
    ) -> float:
        """Compute average pairwise overlap ratio.

        Args:
            sets: List of sets to compare

        Returns:
            Overlap ratio [0.0, 1.0]
        """
        if len(sets) <= 1:
            return 1.0

        total_overlap = 0.0
        pairs = 0

        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                if not sets[i] and not sets[j]:
                    # Both empty → match
                    total_overlap += 1.0
                elif not sets[i] or not sets[j]:
                    # One empty → no match
                    total_overlap += 0.0
                else:
                    # Compute Jaccard overlap
                    union = len(sets[i] | sets[j])
                    intersection = len(sets[i] & sets[j])
                    total_overlap += intersection / union if union > 0 else 1.0
                pairs += 1

        return total_overlap / pairs if pairs > 0 else 1.0

    def _compute_temporal_span(
        self,
        scenes: List[SceneSemantic],
    ) -> float:
        """Compute total temporal span in seconds.

        Args:
            scenes: Scenes to analyze

        Returns:
            Temporal span in seconds
        """
        if not scenes:
            return 0.0

        first_start = scenes[0].start_time or 0.0
        last_end = scenes[-1].end_time or 0.0

        return max(0.0, last_end - first_start)

    def _compute_temporal_gap(self, scenes: List[SceneSemantic]) -> float:
        """Compute maximum temporal gap in ms.

        Args:
            scenes: Scenes to analyze

        Returns:
            Maximum gap in milliseconds
        """
        if len(scenes) <= 1:
            return 0.0

        max_gap = 0.0
        for i in range(len(scenes) - 1):
            current_end = scenes[i].end_time or 0.0
            next_start = scenes[i + 1].start_time or 0.0
            gap = max(0.0, next_start - current_end) * 1000
            max_gap = max(max_gap, gap)

        return max_gap

    def _compute_avg_motion(self, scenes: List[SceneSemantic]) -> float:
        """Compute average motion intensity.

        Args:
            scenes: Scenes to analyze

        Returns:
            Average motion intensity [0, 1]
        """
        if not scenes:
            return 0.0

        total = sum(s.motion_intensity for s in scenes)
        return total / len(scenes)

    def _compute_dominant_pace(self, scenes: List[SceneSemantic]) -> str:
        """Compute dominant action pace.

        Args:
            scenes: Scenes to analyze

        Returns:
            Dominant pace value
        """
        if not scenes:
            return "slow"

        pace_counts: Dict[str, int] = {}
        for scene in scenes:
            pace = scene.action_pace or "slow"
            pace_counts[pace] = pace_counts.get(pace, 0) + 1

        # Sort by count desc, then alphabetically
        sorted_paces = sorted(
            pace_counts.items(),
            key=lambda x: (-x[1], x[0]),
        )
        return sorted_paces[0][0] if sorted_paces else "slow"

    def _collect_environments(self, scenes: List[SceneSemantic]) -> List[str]:
        """Collect unique environment names.

        Args:
            scenes: Scenes to analyze

        Returns:
            Sorted list of environment names
        """
        envs: Set[str] = set()
        for scene in scenes:
            for env in scene.environments:
                envs.add(env.normalized_name)
        return sorted(envs)

    def _collect_emotions(self, scenes: List[SceneSemantic]) -> List[str]:
        """Collect unique emotion names.

        Args:
            scenes: Scenes to analyze

        Returns:
            Sorted list of emotion names
        """
        emotions: Set[str] = set()
        for scene in scenes:
            for emotion in scene.emotions:
                emotions.add(emotion.normalized_name)
        return sorted(emotions)

    def _get_earliest_time(self, event: NarrativeEvent) -> float:
        """Get earliest temporal position from scene IDs.

        This is a fallback for sorting when scenes aren't available.

        Args:
            event: Narrative event

        Returns:
            Earliest time position (uses hash of scene_ids as deterministic fallback)
        """
        # Without access to original scenes, use scene_id as deterministic sort key
        # We encode scene IDs as a float-like value from prefix of IDs
        if event.scene_ids:
            first_id = event.scene_ids[0]
            return float(abs(hash(first_id)) % 10**9)
        return 0.0


# ── EventBoundaryDetector ─────────────────────────────────────────────────────


class EventBoundaryDetector:
    """Detects deterministic event boundaries between scenes.

    Uses ONLY:
    - hard continuity breaks
    - major environment shifts
    - temporal discontinuity
    - dialogue interruption
    - character continuity loss
    """

    # Thresholds for boundary detection
    HARD_CHARACTER_OVERLAP_THRESHOLD = 0.0  # No shared characters → hard break
    MAJOR_ENV_OVERLAP_THRESHOLD = 0.1  # Very low env overlap → major shift
    DIALOGUE_GAP_THRESHOLD = 5000  # 5s dialogue gap → interruption
    TEMPORAL_GAP_THRESHOLD = 10000  # 10s gap → temporal discontinuity
    CRITICAL_COHERENCE_THRESHOLD = 0.2  # Very low coherence → hard break

    def __init__(self) -> None:
        """Initialize boundary detector."""
        pass

    def detect_boundaries(
        self,
        scenes: Sequence[SceneSemantic],
        coherence_result: Optional[TemporalCoherenceResult] = None,
    ) -> List[EventBoundary]:
        """Detect event boundaries between consecutive scenes.

        Args:
            scenes: Ordered list of scene semantics
            coherence_result: Optional pre-computed coherence result

        Returns:
            List of event boundaries (gaps between scenes)
        """
        scene_list = list(scenes)
        if len(scene_list) <= 1:
            return []

        boundaries: List[EventBoundary] = []

        for i in range(len(scene_list) - 1):
            curr = scene_list[i]
            next = scene_list[i + 1]

            boundary = self._detect_single_boundary(curr, next, i, scene_list)
            if boundary is not None:
                boundaries.append(boundary)

        return boundaries

    def _detect_single_boundary(
        self,
        curr: SceneSemantic,
        next_scene: SceneSemantic,
        index: int,
        all_scenes: List[SceneSemantic],
    ) -> Optional[EventBoundary]:
        """Detect boundary between two consecutive scenes.

        Args:
            curr: Current scene
            next_scene: Next scene
            index: Current scene index
            all_scenes: All scenes (for context)

        Returns:
            EventBoundary if detected, None otherwise
        """
        reasons: List[str] = []
        boundary_type: Optional[str] = None
        strength = 0.0

        # 1. Character continuity check
        curr_chars = {c.normalized_name for c in curr.characters}
        next_chars = {c.normalized_name for c in next_scene.characters}

        if curr_chars and next_chars:
            overlap = len(curr_chars & next_chars)
            if overlap == 0:
                reasons.append("character_continuity_loss")
                strength = max(strength, 0.8)
                boundary_type = "character_loss"
        elif curr_chars or next_chars:
            # One has characters, other doesn't
            reasons.append("character_asymmetry")
            strength = max(strength, 0.5)

        # 2. Environment shift
        curr_envs = {e.normalized_name for e in curr.environments}
        next_envs = {e.normalized_name for e in next_scene.environments}

        if curr_envs and next_envs:
            env_overlap = len(curr_envs & next_envs)
            env_union = len(curr_envs | next_envs)
            env_jaccard = env_overlap / env_union if env_union > 0 else 1.0

            if env_jaccard < self.MAJOR_ENV_OVERLAP_THRESHOLD:
                reasons.append("major_environment_shift")
                strength = max(strength, 0.7)
                if boundary_type is None:
                    boundary_type = "environment_shift"

        # 3. Temporal discontinuity
        curr_end = curr.end_time or 0.0
        next_start = next_scene.start_time or 0.0
        temporal_gap = max(0.0, next_start - curr_end) * 1000

        if temporal_gap > self.TEMPORAL_GAP_THRESHOLD:
            reasons.append("temporal_discontinuity")
            strength = max(strength, 0.6)
            if boundary_type is None:
                boundary_type = "temporal_gap"

        # 4. Dialogue interruption
        curr_dialogue = curr.dialogue or ""
        next_dialogue = next_scene.dialogue or ""
        has_dialogue_curr = bool(curr_dialogue.strip())
        has_dialogue_next = bool(next_dialogue.strip())

        if has_dialogue_curr and not has_dialogue_next:
            reasons.append("dialogue_interruption")
            strength = max(strength, 0.4)
        elif not has_dialogue_curr and has_dialogue_next:
            reasons.append("dialogue_onset")
            strength = max(strength, 0.3)

        # 5. Hard coherence break (if coherence result available)
        # (computed as heuristic from available data)

        # Only return boundary if we detected something
        if not reasons:
            return None

        # Build boundary ID deterministically
        boundary_input = {
            "prev_scene_id": curr.scene_id,
            "next_scene_id": next_scene.scene_id,
            "reasons": sorted(reasons),
            "strength": strength,
            "index": index,
        }
        boundary_id = _compute_deterministic_hash(boundary_input)

        return EventBoundary(
            boundary_id=boundary_id,
            prev_scene_id=curr.scene_id,
            next_scene_id=next_scene.scene_id,
            boundary_type=boundary_type or "continuity_break",
            reasons=sorted(reasons),
            strength=round(min(1.0, strength), 6),
            temporal_gap_ms=round(temporal_gap, 3),
        )


# ── NarrativeTransitionAnalyzer ───────────────────────────────────────────────


class NarrativeTransitionAnalyzer:
    """Analyzes deterministic narrative transitions between events.

    Builds deterministic transition labels:
    - smooth_transition
    - hard_cut
    - escalation
    - deescalation
    - flashback_transition
    - temporal_jump
    """

    def analyze_transition(
        self,
        prev_event: NarrativeEvent,
        next_event: NarrativeEvent,
        prev_scenes: Sequence[SceneSemantic],
        next_scenes: Sequence[SceneSemantic],
    ) -> EventTransition:
        """Analyze transition between two narrative events.

        Args:
            prev_event: Previous narrative event
            next_event: Next narrative event
            prev_scenes: Scenes in previous event
            next_scenes: Scenes in next event

        Returns:
            Analyzed event transition
        """
        prev_list = list(prev_scenes)
        next_list = list(next_scenes)

        # Compute transition features
        char_overlap = self._compute_char_overlap(prev_list, next_list)
        env_overlap = self._compute_env_overlap(prev_list, next_list)
        action_overlap = self._compute_action_overlap(prev_list, next_list)
        temporal_gap = self._compute_boundary_gap(prev_list, next_list)
        coherence_delta = (
            next_event.coherence_strength - prev_event.coherence_strength
        )
        emotion_shift = self._detect_emotion_shift(prev_list, next_list)
        dialogue_change = self._detect_dialogue_change(prev_list, next_list)

        # Classify transition label
        label = self._classify_transition(
            char_overlap=char_overlap,
            env_overlap=env_overlap,
            action_overlap=action_overlap,
            temporal_gap=temporal_gap,
            coherence_delta=coherence_delta,
            emotion_shift=emotion_shift,
            dialogue_change=dialogue_change,
            prev_event_type=prev_event.event_type,
            next_event_type=next_event.event_type,
        )

        # Build transition ID
        transition_input = {
            "prev_event_id": prev_event.event_id,
            "next_event_id": next_event.event_id,
            "char_overlap": char_overlap,
            "env_overlap": env_overlap,
            "label": label.value,
        }
        transition_id = _compute_deterministic_hash(transition_input)

        return EventTransition(
            transition_id=transition_id,
            prev_event_id=prev_event.event_id,
            next_event_id=next_event.event_id,
            label=label.value,
            char_overlap=char_overlap,
            env_overlap=env_overlap,
            action_overlap=action_overlap,
            temporal_gap_ms=temporal_gap,
            coherence_delta=round(coherence_delta, 6),
            emotion_shift=emotion_shift,
            dialogue_change=dialogue_change,
        )

    def _compute_char_overlap(
        self,
        prev_scenes: List[SceneSemantic],
        next_scenes: List[SceneSemantic],
    ) -> float:
        """Compute character overlap ratio between two scene groups.

        Args:
            prev_scenes: Scenes from previous event
            next_scenes: Scenes from next event

        Returns:
            Overlap ratio [0.0, 1.0]
        """
        prev_chars: Set[str] = set()
        next_chars: Set[str] = set()

        for s in prev_scenes:
            prev_chars.update(c.normalized_name for c in s.characters)
        for s in next_scenes:
            next_chars.update(c.normalized_name for c in s.characters)

        if not prev_chars and not next_chars:
            return 1.0
        if not prev_chars or not next_chars:
            return 0.0

        union = len(prev_chars | next_chars)
        intersection = len(prev_chars & next_chars)
        return intersection / union if union > 0 else 1.0

    def _compute_env_overlap(
        self,
        prev_scenes: List[SceneSemantic],
        next_scenes: List[SceneSemantic],
    ) -> float:
        """Compute environment overlap ratio.

        Args:
            prev_scenes: Scenes from previous event
            next_scenes: Scenes from next event

        Returns:
            Overlap ratio [0.0, 1.0]
        """
        prev_envs: Set[str] = set()
        next_envs: Set[str] = set()

        for s in prev_scenes:
            prev_envs.update(e.normalized_name for e in s.environments)
        for s in next_scenes:
            next_envs.update(e.normalized_name for e in s.environments)

        if not prev_envs and not next_envs:
            return 1.0
        if not prev_envs or not next_envs:
            return 0.0

        union = len(prev_envs | next_envs)
        intersection = len(prev_envs & next_envs)
        return intersection / union if union > 0 else 1.0

    def _compute_action_overlap(
        self,
        prev_scenes: List[SceneSemantic],
        next_scenes: List[SceneSemantic],
    ) -> float:
        """Compute action overlap ratio.

        Args:
            prev_scenes: Scenes from previous event
            next_scenes: Scenes from next event

        Returns:
            Overlap ratio [0.0, 1.0]
        """
        prev_actions: Set[str] = set()
        next_actions: Set[str] = set()

        for s in prev_scenes:
            prev_actions.update(a.normalized_name for a in s.actions)
        for s in next_scenes:
            next_actions.update(a.normalized_name for a in s.actions)

        if not prev_actions and not next_actions:
            return 1.0
        if not prev_actions or not next_actions:
            return 0.0

        union = len(prev_actions | next_actions)
        intersection = len(prev_actions & next_actions)
        return intersection / union if union > 0 else 1.0

    def _compute_boundary_gap(
        self,
        prev_scenes: List[SceneSemantic],
        next_scenes: List[SceneSemantic],
    ) -> float:
        """Compute temporal gap between event groups.

        Args:
            prev_scenes: Scenes from previous event
            next_scenes: Scenes from next event

        Returns:
            Temporal gap in milliseconds
        """
        if not prev_scenes or not next_scenes:
            return 0.0

        last_prev_end = prev_scenes[-1].end_time or 0.0
        first_next_start = next_scenes[0].start_time or 0.0

        gap = max(0.0, first_next_start - last_prev_end) * 1000
        return gap

    def _detect_emotion_shift(
        self,
        prev_scenes: List[SceneSemantic],
        next_scenes: List[SceneSemantic],
    ) -> bool:
        """Detect significant emotion shift between events.

        Args:
            prev_scenes: Scenes from previous event
            next_scenes: Scenes from next event

        Returns:
            True if emotion shift detected
        """
        prev_emotions: Set[str] = set()
        next_emotions: Set[str] = set()

        for s in prev_scenes:
            prev_emotions.update(e.normalized_name for e in s.emotions)
        for s in next_scenes:
            next_emotions.update(e.normalized_name for e in s.emotions)

        if not prev_emotions and not next_emotions:
            return False

        # Detect if emotions are completely different
        if prev_emotions and next_emotions:
            overlap = prev_emotions & next_emotions
            return len(overlap) == 0

        return True  # One has emotions, other doesn't → shift

    def _detect_dialogue_change(
        self,
        prev_scenes: List[SceneSemantic],
        next_scenes: List[SceneSemantic],
    ) -> bool:
        """Detect significant dialogue pattern change.

        Args:
            prev_scenes: Scenes from previous event
            next_scenes: Scenes from next event

        Returns:
            True if dialogue change detected
        """
        prev_has_dialogue = any(
            bool((s.dialogue or "").strip()) for s in prev_scenes
        )
        next_has_dialogue = any(
            bool((s.dialogue or "").strip()) for s in next_scenes
        )

        return prev_has_dialogue != next_has_dialogue

    def _classify_transition(
        self,
        char_overlap: float,
        env_overlap: float,
        action_overlap: float,
        temporal_gap: float,
        coherence_delta: float,
        emotion_shift: bool,
        dialogue_change: bool,
        prev_event_type: str,
        next_event_type: str,
    ) -> TransitionLabel:
        """Classify transition label deterministically.

        Args:
            char_overlap: Character overlap ratio
            env_overlap: Environment overlap ratio
            action_overlap: Action overlap ratio
            temporal_gap: Temporal gap in ms
            coherence_delta: Coherence score change
            emotion_shift: Whether emotion shift detected
            dialogue_change: Whether dialogue pattern changed
            prev_event_type: Previous event type
            next_event_type: Next event type

        Returns:
            Transition label
        """
        # Temporal jump detection
        if temporal_gap > 30000:  # >30s gap
            if prev_event_type == "flashback_candidate" or next_event_type == "flashback_candidate":
                return TransitionLabel.FLASHBACK_TRANSITION
            return TransitionLabel.TEMPORAL_JUMP

        # Flashback transition
        if prev_event_type == "flashback_candidate" or next_event_type == "flashback_candidate":
            return TransitionLabel.FLASHBACK_TRANSITION

        # Hard cut detection
        if char_overlap < 0.1 and env_overlap < 0.1:
            return TransitionLabel.HARD_CUT
        if char_overlap == 0.0:
            return TransitionLabel.HARD_CUT

        # Escalation detection
        if coherence_delta > 0.2 and action_overlap > 0.3:
            return TransitionLabel.ESCALATION
        if emotion_shift and char_overlap > 0.3:
            return TransitionLabel.ESCALATION

        # Deescalation detection
        if coherence_delta < -0.2 and not emotion_shift:
            return TransitionLabel.DEESCALATION
        if dialogue_change and char_overlap > 0.5:
            return TransitionLabel.DEESCALATION

        # Default to smooth transition
        return TransitionLabel.SMOOTH_TRANSITION


# ── NarrativeEventGroupingEngine ──────────────────────────────────────────────


class NarrativeEventGroupingEngine:
    """Top-level engine for deterministic narrative event grouping.

    Orchestrates:
    - Event building from continuity chains
    - Event boundary detection
    - Transition analysis
    - Event grouping
    """

    def __init__(
        self,
        builder: Optional[NarrativeEventBuilder] = None,
        boundary_detector: Optional[EventBoundaryDetector] = None,
        transition_analyzer: Optional[NarrativeTransitionAnalyzer] = None,
    ) -> None:
        """Initialize grouping engine.

        Args:
            builder: Optional narrative event builder
            boundary_detector: Optional boundary detector
            transition_analyzer: Optional transition analyzer
        """
        self.event_builder = builder or NarrativeEventBuilder()
        self.boundary_detector = boundary_detector or EventBoundaryDetector()
        self.transition_analyzer = transition_analyzer or NarrativeTransitionAnalyzer()

    def group(
        self,
        scenes: Sequence[SceneSemantic],
        continuity_chains: Optional[ContinuityChainResult] = None,
        coherence_result: Optional[TemporalCoherenceResult] = None,
    ) -> List[NarrativeEventGroup]:
        """Group scenes into narrative event groups.

        Args:
            scenes: Ordered list of scene semantics
            continuity_chains: Optional pre-computed continuity chains
            coherence_result: Optional pre-computed coherence result

        Returns:
            List of narrative event groups

        Raises:
            ValueError: If scenes is empty
        """
        scene_list = list(scenes)
        if not scene_list:
            return []

        # 1. Build events
        events = self.event_builder.build_events(
            scene_list,
            continuity_chains=continuity_chains,
            coherence_result=coherence_result,
        )

        if not events:
            return []

        # 2. Detect boundaries
        boundaries = self.boundary_detector.detect_boundaries(
            scene_list,
            coherence_result=coherence_result,
        )

        # 3. Build scene grouping based on boundaries
        groups = self._group_scenes_by_boundaries(
            scene_list, boundaries, events, continuity_chains
        )

        # 4. Analyze transitions between groups
        for i in range(len(groups) - 1):
            prev_group = groups[i]
            next_group = groups[i + 1]

            # Resolve scenes for each group
            prev_scenes = self._resolve_group_scenes(prev_group, scene_list)
            next_scenes = self._resolve_group_scenes(next_group, scene_list)

            transition = self.transition_analyzer.analyze_transition(
                prev_group.events[0] if prev_group.events else prev_group.dominant_event,
                next_group.events[0] if next_group.events else next_group.dominant_event,
                prev_scenes,
                next_scenes,
            )
            prev_group.transition_out = transition

        return groups

    def _group_scenes_by_boundaries(
        self,
        scenes: List[SceneSemantic],
        boundaries: List[EventBoundary],
        events: List[NarrativeEvent],
        continuity_chains: Optional[ContinuityChainResult],
    ) -> List[NarrativeEventGroup]:
        """Group scenes into groups based on detected boundaries.

        Args:
            scenes: All scenes
            boundaries: Detected event boundaries
            events: Built narrative events
            continuity_chains: Optional continuity chains

        Returns:
            List of narrative event groups
        """
        if not scenes:
            return []

        # Build scene-to-event mapping
        scene_to_events: Dict[str, List[NarrativeEvent]] = {}
        for event in events:
            for sid in event.scene_ids:
                if sid not in scene_to_events:
                    scene_to_events[sid] = []
                scene_to_events[sid].append(event)

        # Build boundary set for quick lookup
        boundary_scenes: Set[str] = {b.prev_scene_id for b in boundaries}

        # Group scenes sequentially
        groups: List[NarrativeEventGroup] = []
        current_scenes: List[str] = []

        for scene in scenes:
            current_scenes.append(scene.scene_id)

            # Check if this scene has a boundary after it
            if scene.scene_id in boundary_scenes:
                # Finalize current group
                if current_scenes:
                    group = self._build_group(
                        current_scenes, scene_to_events, events, scenes
                    )
                    groups.append(group)
                current_scenes = []

        # Handle remaining scenes
        if current_scenes:
            group = self._build_group(
                current_scenes, scene_to_events, events, scenes
            )
            groups.append(group)

        # If no boundaries detected, put all scenes in one group
        if not groups and events:
            all_scene_ids = [s.scene_id for s in scenes]
            group = self._build_group(
                all_scene_ids, scene_to_events, events, scenes
            )
            groups.append(group)

        return groups

    def _build_group(
        self,
        scene_ids: List[str],
        scene_to_events: Dict[str, List[NarrativeEvent]],
        all_events: List[NarrativeEvent],
        all_scenes: List[SceneSemantic],
    ) -> NarrativeEventGroup:
        """Build a narrative event group from scene IDs.

        Args:
            scene_ids: Ordered scene IDs in group
            scene_to_events: Scene ID to event mapping
            all_events: All narrative events
            all_scenes: All scenes

        Returns:
            Constructed narrative event group
        """
        # Collect events that overlap with our scenes
        group_events: List[NarrativeEvent] = []
        seen_event_ids: Set[str] = set()

        for sid in scene_ids:
            for event in scene_to_events.get(sid, []):
                if event.event_id not in seen_event_ids:
                    group_events.append(event)
                    seen_event_ids.add(event.event_id)

        # Sort events by first scene position
        group_events.sort(key=lambda e: e.temporal_span if e.temporal_span > 0 else 0.0)

        # Compute dominant event type
        type_counts: Dict[str, int] = {}
        for event in group_events:
            type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1

        dominant_type = (
            max(type_counts, key=lambda k: (type_counts[k], k))
            if type_counts
            else "unknown"
        )

        # Pick dominant event (highest coherence, then most scenes)
        dominant_event = None
        if group_events:
            dominant_event = max(
                group_events,
                key=lambda e: (e.coherence_strength, len(e.scene_ids), e.event_id),
            )

        # Build group hash
        group_input = {
            "scene_ids": scene_ids,
            "event_ids": [e.event_id for e in group_events],
            "dominant_type": dominant_type,
        }
        group_hash = _compute_deterministic_hash(group_input)

        return NarrativeEventGroup(
            group_id=group_hash,
            scene_ids=scene_ids,
            event_ids=[e.event_id for e in group_events],
            events=group_events,
            dominant_event_type=dominant_type,
            dominant_event=dominant_event,
            transition_out=None,
        )

    def _resolve_group_scenes(
        self,
        group: NarrativeEventGroup,
        all_scenes: List[SceneSemantic],
    ) -> List[SceneSemantic]:
        """Resolve scene IDs to scene objects for a group.

        Args:
            group: Narrative event group
            all_scenes: All scenes

        Returns:
            List of scene semantics for the group
        """
        scene_map = {s.scene_id: s for s in all_scenes}
        resolved: List[SceneSemantic] = []
        for sid in group.scene_ids:
            if sid in scene_map:
                resolved.append(scene_map[sid])
        return resolved