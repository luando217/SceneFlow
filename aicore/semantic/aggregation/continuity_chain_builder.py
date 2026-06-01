"""ContinuityChainBuilder — deterministic builder for continuity chains.

Builds continuity chains from scene sequences with:
- Deterministic ordering
- Deterministic chain breaks
- Temporal span calculation
- SHA-256 hash generation
- Replay-safe rebuilds

All operations are:
- Deterministic (same input → same output)
- Immutable (no mutation after creation)
- Replay-safe (can be serialized/deserialized)
- No randomness, no AI, no embeddings
"""

from __future__ import annotations

import hashlib
from typing import Dict, List, Optional

from aicore.semantic.aggregation.continuity_chain_schemas import (
    ActionContinuityChain,
    CharacterContinuityChain,
    DialogueContinuityChain,
    EnvironmentContinuityChain,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


def _stable_hash(content: str) -> str:
    """Generate stable SHA-256 hex digest from string content.

    Args:
        content: String content to hash

    Returns:
        Fixed-length hex digest (64 chars)
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sorted_strings(items: List[str]) -> List[str]:
    """Return deterministically-sorted copy of a list."""
    return sorted(items)


class ContinuityChainBuilder:
    """Deterministic builder for continuity chains.

    Takes ordered SceneSemantic objects and produces:
    - CharacterContinuityChain
    - ActionContinuityChain
    - EnvironmentContinuityChain
    - DialogueContinuityChain

    All chains are deterministic, frozen, and replay-safe.
    """

    def __init__(
        self,
        min_chain_length: int = 2,
        min_continuity_score: float = 0.5,
    ):
        """Initialize builder with thresholds.

        Args:
            min_chain_length: Minimum scenes to form a chain
            min_continuity_score: Minimum continuity score for chaining
        """
        self.min_chain_length = min_chain_length
        self.min_continuity_score = min_continuity_score

    def build_character_chain(
        self,
        scenes: List[SceneSemantic],
        continuity_scores: Dict[str, float],
        chain_id: str,
    ) -> Optional[CharacterContinuityChain]:
        """Build character continuity chain from scenes.

        Args:
            scenes: Ordered list of scenes (must be temporally sorted)
            continuity_scores: Dict mapping scene_id -> continuity_score to next scene
            chain_id: Unique chain identifier

        Returns:
            CharacterContinuityChain or None if insufficient scenes
        """
        if len(scenes) < self.min_chain_length:
            return None

        # Extract all characters from scenes
        all_characters = set()
        for scene in scenes:
            for char in scene.characters:
                all_characters.add(char.normalized_name)

        if not all_characters:
            return None

        # Calculate aggregate continuity score
        scores = [continuity_scores.get(scene.scene_id, 0.0) for scene in scenes[:-1]]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Calculate temporal span
        temporal_span = scenes[-1].end_time - scenes[0].start_time

        # Generate deterministic hash
        scene_ids = [s.scene_id for s in scenes]
        char_hash = _stable_hash(f"char_chain:{chain_id}:{':'.join(scene_ids)}")

        return CharacterContinuityChain.create(
            chain_id=chain_id,
            ordered_scene_ids=_sorted_strings(scene_ids),
            characters=_sorted_strings(list(all_characters)),
            continuity_score=avg_score,
            temporal_span=temporal_span,
            deterministic_hash=char_hash,
        )

    def build_action_chain(
        self,
        scenes: List[SceneSemantic],
        continuity_scores: Dict[str, float],
        chain_id: str,
        action_intensity_scores: Optional[List[float]] = None,
    ) -> Optional[ActionContinuityChain]:
        """Build action continuity chain from scenes.

        Args:
            scenes: Ordered list of scenes (must be temporally sorted)
            continuity_scores: Dict mapping scene_id -> continuity_score to next scene
            chain_id: Unique chain identifier
            action_intensity_scores: Optional per-scene intensity scores

        Returns:
            ActionContinuityChain or None if insufficient scenes
        """
        if len(scenes) < self.min_chain_length:
            return None

        # Extract all actions from scenes
        all_actions = set()
        for scene in scenes:
            for action in scene.actions:
                all_actions.add(action.normalized_name)

        if not all_actions:
            return None

        # Calculate aggregate continuity score
        scores = [continuity_scores.get(scene.scene_id, 0.0) for scene in scenes[:-1]]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Calculate temporal span
        temporal_span = scenes[-1].end_time - scenes[0].start_time

        # Generate deterministic hash
        scene_ids = [s.scene_id for s in scenes]
        action_hash = _stable_hash(f"action_chain:{chain_id}:{':'.join(scene_ids)}")

        return ActionContinuityChain.create(
            chain_id=chain_id,
            ordered_scene_ids=_sorted_strings(scene_ids),
            actions=_sorted_strings(list(all_actions)),
            continuity_score=avg_score,
            temporal_span=temporal_span,
            deterministic_hash=action_hash,
            action_intensity_scores=action_intensity_scores or [],
        )

    def build_environment_chain(
        self,
        scenes: List[SceneSemantic],
        continuity_scores: Dict[str, float],
        chain_id: str,
    ) -> Optional[EnvironmentContinuityChain]:
        """Build environment continuity chain from scenes.

        Args:
            scenes: Ordered list of scenes (must be temporally sorted)
            continuity_scores: Dict mapping scene_id -> continuity_score to next scene
            chain_id: Unique chain identifier

        Returns:
            EnvironmentContinuityChain or None if insufficient scenes
        """
        if len(scenes) < self.min_chain_length:
            return None

        # Extract all environments from scenes
        all_environments = set()
        location_class = None
        time_of_day = None
        weather = None

        for scene in scenes:
            for env in scene.environments:
                all_environments.add(env.location)
                if location_class is None and env.location:
                    location_class = env.location
                if time_of_day is None and env.time_of_day:
                    time_of_day = env.time_of_day
                if weather is None and env.weather:
                    weather = env.weather

        if not all_environments:
            return None

        # Calculate aggregate continuity score
        scores = [continuity_scores.get(scene.scene_id, 0.0) for scene in scenes[:-1]]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Calculate temporal span
        temporal_span = scenes[-1].end_time - scenes[0].start_time

        # Generate deterministic hash
        scene_ids = [s.scene_id for s in scenes]
        env_hash = _stable_hash(f"env_chain:{chain_id}:{':'.join(scene_ids)}")

        return EnvironmentContinuityChain.create(
            chain_id=chain_id,
            ordered_scene_ids=_sorted_strings(scene_ids),
            environments=_sorted_strings(list(all_environments)),
            continuity_score=avg_score,
            temporal_span=temporal_span,
            deterministic_hash=env_hash,
            location_class=location_class,
            time_of_day=time_of_day,
            weather=weather,
        )

    def build_dialogue_chain(
        self,
        scenes: List[SceneSemantic],
        continuity_scores: Dict[str, float],
        chain_id: str,
        dialogue_lengths: Optional[List[int]] = None,
        dialogue_context: Optional[str] = None,
    ) -> Optional[DialogueContinuityChain]:
        """Build dialogue continuity chain from scenes.

        Args:
            scenes: Ordered list of scenes (must be temporally sorted)
            continuity_scores: Dict mapping scene_id -> continuity_score to next scene
            chain_id: Unique chain identifier
            dialogue_lengths: Optional per-scene dialogue lengths
            dialogue_context: Optional deterministic dialogue summary

        Returns:
            DialogueContinuityChain or None if insufficient scenes
        """
        if len(scenes) < self.min_chain_length:
            return None

        # Extract all speakers from scenes (derived from dialogue content)
        # Since SceneSemantic has dialogue text, we use a deterministic approach
        all_speakers = set()
        for scene in scenes:
            if scene.dialogue:
                # Deterministic: use dialogue content hash to identify speakers
                # In production, this would come from ASR node
                speaker_hash = _stable_hash(scene.dialogue)[:16]
                all_speakers.add(f"speaker_{speaker_hash}")

        if not all_speakers:
            return None

        # Calculate aggregate continuity score
        scores = [continuity_scores.get(scene.scene_id, 0.0) for scene in scenes[:-1]]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Calculate temporal span
        temporal_span = scenes[-1].end_time - scenes[0].start_time

        # Generate deterministic hash
        scene_ids = [s.scene_id for s in scenes]
        dialogue_hash = _stable_hash(
            f"dialogue_chain:{chain_id}:{':'.join(scene_ids)}"
        )

        return DialogueContinuityChain.create(
            chain_id=chain_id,
            ordered_scene_ids=_sorted_strings(scene_ids),
            speakers=_sorted_strings(list(all_speakers)),
            continuity_score=avg_score,
            temporal_span=temporal_span,
            deterministic_hash=dialogue_hash,
            dialogue_lengths=dialogue_lengths or [],
            dialogue_context=dialogue_context,
        )


class DeterministicChainGrouper:
    """Groups scenes into chains based on continuity type.

    Breaks chains deterministically when continuity is interrupted.
    Supports replay-safe rebuilds.
    """

    def __init__(
        self,
        min_chain_length: int = 2,
        min_continuity_score: float = 0.5,
        max_temporal_gap_ms: float = 500.0,
    ):
        """Initialize grouper.

        Args:
            min_chain_length: Minimum scenes to form a chain
            min_continuity_score: Minimum continuity score for chaining
            max_temporal_gap_ms: Maximum gap between scenes (ms)
        """
        self.builder = ContinuityChainBuilder(
            min_chain_length=min_chain_length,
            min_continuity_score=min_continuity_score,
        )
        self.max_temporal_gap_ms = max_temporal_gap_ms
        self.min_continuity_score = min_continuity_score

    def group_by_character(
        self,
        scenes: List[SceneSemantic],
    ) -> List[CharacterContinuityChain]:
        """Group scenes into character continuity chains.

        Args:
            scenes: Temporally ordered scenes

        Returns:
            List of CharacterContinuityChain
        """
        chains: List[CharacterContinuityChain] = []
        current_group: List[SceneSemantic] = []
        continuity_scores: Dict[str, float] = {}
        chain_counter = 0

        for i, scene in enumerate(scenes):
            if i == 0:
                current_group.append(scene)
                continue

            prev_scene = scenes[i - 1]

            # Check temporal adjacency
            if not self._is_temporally_adjacent(prev_scene, scene):
                # Break chain, finalize current
                if current_group:
                    chain = self.builder.build_character_chain(
                        current_group, continuity_scores, f"char_chain_{chain_counter}"
                    )
                    if chain:
                        chains.append(chain)
                    chain_counter += 1
                    continuity_scores = {}
                current_group = [scene]
            else:
                # Calculate continuity score between scenes
                score = self._calculate_character_overlap(prev_scene, scene)
                continuity_scores[prev_scene.scene_id] = score

                if score >= self.min_continuity_score:
                    current_group.append(scene)
                else:
                    # Break chain, finalize current
                    if current_group:
                        chain = self.builder.build_character_chain(
                            current_group, continuity_scores, f"char_chain_{chain_counter}"
                        )
                        if chain:
                            chains.append(chain)
                        chain_counter += 1
                        continuity_scores = {}
                    current_group = [scene]

        # Finalize last group
        if current_group:
            chain = self.builder.build_character_chain(
                current_group, continuity_scores, f"char_chain_{chain_counter}"
            )
            if chain:
                chains.append(chain)

        return chains

    def group_by_action(
        self,
        scenes: List[SceneSemantic],
    ) -> List[ActionContinuityChain]:
        """Group scenes into action continuity chains.

        Args:
            scenes: Temporally ordered scenes

        Returns:
            List of ActionContinuityChain
        """
        chains: List[ActionContinuityChain] = []
        current_group: List[SceneSemantic] = []
        continuity_scores: Dict[str, float] = {}
        action_intensity_scores: List[float] = []
        chain_counter = 0

        for i, scene in enumerate(scenes):
            if i == 0:
                current_group.append(scene)
                action_intensity_scores.append(scene.motion_intensity)
                continue

            prev_scene = scenes[i - 1]

            # Check temporal adjacency
            if not self._is_temporally_adjacent(prev_scene, scene):
                # Break chain, finalize current
                if current_group:
                    chain = self.builder.build_action_chain(
                        current_group,
                        continuity_scores,
                        f"action_chain_{chain_counter}",
                        action_intensity_scores,
                    )
                    if chain:
                        chains.append(chain)
                    chain_counter += 1
                    continuity_scores = {}
                    action_intensity_scores = []
                current_group = [scene]
                action_intensity_scores = [scene.motion_intensity]
            else:
                # Calculate continuity score between scenes
                score = self._calculate_action_overlap(prev_scene, scene)
                continuity_scores[prev_scene.scene_id] = score
                action_intensity_scores.append(scene.motion_intensity)

                if score >= self.min_continuity_score:
                    current_group.append(scene)
                else:
                    # Break chain, finalize current
                    if current_group:
                        chain = self.builder.build_action_chain(
                            current_group,
                            continuity_scores,
                            f"action_chain_{chain_counter}",
                            action_intensity_scores,
                        )
                        if chain:
                            chains.append(chain)
                        chain_counter += 1
                        continuity_scores = {}
                        action_intensity_scores = []
                    current_group = [scene]
                    action_intensity_scores = [scene.motion_intensity]

        # Finalize last group
        if current_group:
            chain = self.builder.build_action_chain(
                current_group,
                continuity_scores,
                f"action_chain_{chain_counter}",
                action_intensity_scores,
            )
            if chain:
                chains.append(chain)

        return chains

    def group_by_environment(
        self,
        scenes: List[SceneSemantic],
    ) -> List[EnvironmentContinuityChain]:
        """Group scenes into environment continuity chains.

        Args:
            scenes: Temporally ordered scenes

        Returns:
            List of EnvironmentContinuityChain
        """
        chains: List[EnvironmentContinuityChain] = []
        current_group: List[SceneSemantic] = []
        continuity_scores: Dict[str, float] = {}
        chain_counter = 0

        for i, scene in enumerate(scenes):
            if i == 0:
                current_group.append(scene)
                continue

            prev_scene = scenes[i - 1]

            # Check temporal adjacency
            if not self._is_temporally_adjacent(prev_scene, scene):
                # Break chain, finalize current
                if current_group:
                    chain = self.builder.build_environment_chain(
                        current_group, continuity_scores, f"env_chain_{chain_counter}"
                    )
                    if chain:
                        chains.append(chain)
                    chain_counter += 1
                    continuity_scores = {}
                current_group = [scene]
            else:
                # Calculate continuity score between scenes
                score = self._calculate_environment_overlap(prev_scene, scene)
                continuity_scores[prev_scene.scene_id] = score

                if score >= self.min_continuity_score:
                    current_group.append(scene)
                else:
                    # Break chain, finalize current
                    if current_group:
                        chain = self.builder.build_environment_chain(
                            current_group, continuity_scores, f"env_chain_{chain_counter}"
                        )
                        if chain:
                            chains.append(chain)
                        chain_counter += 1
                        continuity_scores = {}
                    current_group = [scene]

        # Finalize last group
        if current_group:
            chain = self.builder.build_environment_chain(
                current_group, continuity_scores, f"env_chain_{chain_counter}"
            )
            if chain:
                chains.append(chain)

        return chains

    def _is_temporally_adjacent(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        """Check if two scenes are temporally adjacent."""
        if scene_a.video_id != scene_b.video_id:
            return False
        if scene_b.start_time < scene_a.end_time:
            return False
        gap_ms = (scene_b.start_time - scene_a.end_time) * 1000
        return gap_ms <= self.max_temporal_gap_ms

    def _calculate_character_overlap(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> float:
        """Calculate deterministic character overlap score."""
        names_a = {c.normalized_name for c in scene_a.characters}
        names_b = {c.normalized_name for c in scene_b.characters}
        if not names_a or not names_b:
            return 1.0
        overlap = names_a & names_b
        total = names_a | names_b
        return len(overlap) / len(total) if total else 1.0

    def _calculate_action_overlap(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> float:
        """Calculate deterministic action overlap score."""
        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}
        if not actions_a or not actions_b:
            return 1.0
        overlap = actions_a & actions_b
        total = actions_a | actions_b
        return len(overlap) / len(total) if total else 1.0

    def _calculate_environment_overlap(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> float:
        """Calculate deterministic environment overlap score."""
        if not scene_a.environments or not scene_b.environments:
            return 1.0
        env_a = {e.location for e in scene_a.environments}
        env_b = {e.location for e in scene_b.environments}
        overlap = env_a & env_b
        total = env_a | env_b
        return len(overlap) / len(total) if total else 1.0


__all__ = [
    "ContinuityChainBuilder",
    "DeterministicChainGrouper",
]