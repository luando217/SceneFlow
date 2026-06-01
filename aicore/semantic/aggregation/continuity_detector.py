"""ContinuityDetector — deterministic continuity checks for scene merging.

Detects semantic continuity between adjacent scenes to determine
if they should be merged into a single semantic patch group.

Rules are deterministic and based on explicit semantic overlap,
not AI-inferred similarity.
"""

from __future__ import annotations

from typing import Dict, Optional

from aicore.semantic.schemas.scene_semantic import SceneSemantic


class ContinuityDetector:
    """Deterministic continuity checking for adjacent scenes.

    Checks:
    - Character continuity (same characters present)
    - Temporal adjacency (scenes are temporally adjacent)
    - Environment continuity (same location)
    - Dialogue continuation (coherent dialogue flow)
    - Motion continuity (consistent motion patterns)
    - Action continuation (action doesn't "break" between scenes)

    All checks are deterministic and thresholds are explicit.
    """

    def __init__(
        self,
        character_overlap_threshold: float = 0.5,
        dialogue_continuation_min_length: int = 10,
        max_temporal_gap_ms: float = 500.0,
    ):
        """Initialize detector with thresholds."""
        self.character_overlap_threshold = character_overlap_threshold
        self.dialogue_continuation_min_length = dialogue_continuation_min_length
        self.max_temporal_gap_ms = max_temporal_gap_ms

    def classify_transition(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> str:
        """Classify the transition type deterministically."""
        if not self._is_temporally_adjacent(scene_a, scene_b):
            return "hard_cut"

        if self.has_dialogue_continuation(scene_a, scene_b):
            return "dialogue_continuation"

        if self.has_combat_continuation(scene_a, scene_b):
            return "action_continuation"

        if self._has_environment_continuity(scene_a, scene_b):
            return "soft_continuation"

        return "environment_shift"

    def get_continuity_score(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> float:
        """Compute deterministic continuity score [0.0, 1.0]."""
        if not self._is_temporally_adjacent(scene_a, scene_b):
            return 0.0

        scores = []
        weights = []

        # 1. Character overlap (0.3)
        scores.append(self._calculate_character_overlap(scene_a, scene_b))
        weights.append(0.3)

        # 2. Environment continuity (0.2)
        scores.append(1.0 if self._has_environment_continuity(scene_a, scene_b) else 0.0)
        weights.append(0.2)

        # 3. Dialogue continuation (0.2)
        scores.append(1.0 if self.has_dialogue_continuation(scene_a, scene_b) else 0.0)
        weights.append(0.2)

        # 4. Motion continuity (0.15)
        scores.append(1.0 if self.has_motion_continuity(scene_a, scene_b) else 0.0)
        weights.append(0.15)
        
        # 5. Action/Combat continuity (0.15)
        scores.append(1.0 if self.has_combat_continuation(scene_a, scene_b) else 0.0)
        weights.append(0.15)

        return sum(s * w for s, w in zip(scores, weights)) / sum(weights)

    def _is_temporally_adjacent(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        if scene_a.video_id != scene_b.video_id:
            return False
        if scene_a.end_time > scene_b.start_time:
            return False
        gap_ms = (scene_b.start_time - scene_a.end_time) * 1000
        return gap_ms <= self.max_temporal_gap_ms

    def _calculate_character_overlap(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> float:
        names_a = {c.normalized_name for c in scene_a.characters}
        names_b = {c.normalized_name for c in scene_b.characters}
        if not names_a or not names_b:
            return 1.0
        overlap = names_a & names_b
        total = names_a | names_b
        return len(overlap) / len(total) if total else 1.0

    def _has_environment_continuity(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        if not scene_a.environments or not scene_b.environments:
            return True
        return scene_a.environments[0].location == scene_b.environments[0].location

    def has_dialogue_continuation(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        if not scene_a.dialogue or not scene_b.dialogue:
            return False
        return len(scene_a.dialogue) >= self.dialogue_continuation_min_length and \
               len(scene_b.dialogue) >= self.dialogue_continuation_min_length

    def has_combat_continuation(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        combat_keywords = {"fight", "attack", "battle", "combat", "strike"}
        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}
        return any(any(k in a for k in combat_keywords) for a in actions_a) and \
               any(any(k in a for k in combat_keywords) for a in actions_b)

    def has_motion_continuity(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> bool:
        if scene_a.motion_direction == scene_b.motion_direction:
            return True
        return abs(scene_b.motion_intensity - scene_a.motion_intensity) < 0.3

    def describe_continuity(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> Dict:
        """Describe continuity between two scenes."""
        score = self.get_continuity_score(scene_a, scene_b)
        return {
            "is_continuous": score > 0.5,
            "score": score,
            "transition": self.classify_transition(scene_a, scene_b),
            "checks": {
                "character": self._calculate_character_overlap(scene_a, scene_b),
                "environment": self._has_environment_continuity(scene_a, scene_b),
                "dialogue": self.has_dialogue_continuation(scene_a, scene_b),
                "motion": self.has_motion_continuity(scene_a, scene_b),
                "combat": self.has_combat_continuation(scene_a, scene_b),
            },
        }
