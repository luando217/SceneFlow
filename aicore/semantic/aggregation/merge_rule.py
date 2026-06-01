"""MergeRule — explicit semantic merge rules for scene aggregation.

Defines deterministic rules for merging SceneSemantic objects into
semantic patch groups. Rules are explicit, inspectable, and deterministic.

No AI inference—pure rule-based merging.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from aicore.semantic.schemas.scene_semantic import SceneSemantic


class MergeRuleType(str, Enum):
    """Type of semantic merge rule."""

    DIALOGUE_CONTINUITY = "dialogue_continuity"
    """Multiple scenes form continuous dialogue exchange."""

    ACTION_SEQUENCE = "action_sequence"
    """Multiple scenes form continuous action sequence."""

    SCENE_TRANSITION = "scene_transition"
    """Scenes are connected by transition/environment change."""

    CHARACTER_INTERACTION = "character_interaction"
    """Scenes focus on interaction between same characters."""

    TEMPORAL_SEQUENCE = "temporal_sequence"
    """Scenes are temporally adjacent with character continuity."""


class MergeRuleResult(str, Enum):
    """Result of applying merge rule."""

    MERGE = "merge"
    """Scenes should be merged."""

    SEPARATE = "separate"
    """Scenes should remain separate."""

    UNDECIDED = "undecided"
    """Rule cannot determine (other rules should decide)."""


class MergeRule:
    """Base class for semantic merge rules."""

    def __init__(self, rule_type: MergeRuleType, priority: int = 50):
        """Initialize rule.

        Args:
            rule_type: Type of rule
            priority: Execution priority (higher = checked first)
        """
        self.rule_type = rule_type
        self.priority = priority

    def apply(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> MergeRuleResult:
        """Apply rule to determine if scenes should merge.

        Args:
            scene_a: First scene
            scene_b: Second scene

        Returns:
            MergeRuleResult indicating merge decision
        """
        raise NotImplementedError

    def score(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> float:
        """Compute merge score [0.0, 1.0].

        Higher = more likely to merge.

        Args:
            scene_a: First scene
            scene_b: Second scene

        Returns:
            Float in [0.0, 1.0]
        """
        raise NotImplementedError


class DialogueContinuityRule(MergeRule):
    """Merge if dialogue is continuous."""

    def __init__(self):
        super().__init__(MergeRuleType.DIALOGUE_CONTINUITY, priority=100)

    def apply(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> MergeRuleResult:
        """Check if dialogue is continuous."""
        if not scene_a.dialogue or not scene_b.dialogue:
            return MergeRuleResult.UNDECIDED

        # Both have dialogue: likely continuous
        return MergeRuleResult.MERGE

    def score(self, scene_a: SceneSemantic, scene_b: SceneSemantic) -> float:
        """Score based on dialogue presence."""
        score = 0.0

        if scene_a.dialogue:
            score += 0.5
        if scene_b.dialogue:
            score += 0.5

        return score


class ActionSequenceRule(MergeRule):
    """Merge if action sequence is continuous."""

    def __init__(self):
        super().__init__(MergeRuleType.ACTION_SEQUENCE, priority=90)

    def apply(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> MergeRuleResult:
        """Check if actions are continuous."""
        if not scene_a.actions or not scene_b.actions:
            return MergeRuleResult.UNDECIDED

        # Check for action overlap (same actions)
        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}

        overlap = actions_a & actions_b
        if overlap:
            return MergeRuleResult.MERGE

        return MergeRuleResult.UNDECIDED

    def score(self, scene_a: SceneSemantic, scene_b: SceneSemantic) -> float:
        """Score based on action overlap."""
        if not scene_a.actions or not scene_b.actions:
            return 0.0

        actions_a = {a.normalized_name for a in scene_a.actions}
        actions_b = {a.normalized_name for a in scene_b.actions}

        overlap = len(actions_a & actions_b)
        total = len(actions_a | actions_b)

        return overlap / total if total > 0 else 0.0


class CharacterInteractionRule(MergeRule):
    """Merge if same characters interact."""

    def __init__(self):
        super().__init__(MergeRuleType.CHARACTER_INTERACTION, priority=80)

    def apply(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> MergeRuleResult:
        """Check if same characters are present."""
        if not scene_a.characters or not scene_b.characters:
            return MergeRuleResult.UNDECIDED

        chars_a = {c.normalized_name for c in scene_a.characters}
        chars_b = {c.normalized_name for c in scene_b.characters}

        overlap = chars_a & chars_b
        if len(overlap) >= 2:  # At least 2 characters in common
            return MergeRuleResult.MERGE

        return MergeRuleResult.UNDECIDED

    def score(self, scene_a: SceneSemantic, scene_b: SceneSemantic) -> float:
        """Score based on character overlap."""
        if not scene_a.characters or not scene_b.characters:
            return 0.0

        chars_a = {c.normalized_name for c in scene_a.characters}
        chars_b = {c.normalized_name for c in scene_b.characters}

        overlap = len(chars_a & chars_b)
        total = len(chars_a | chars_b)

        return overlap / total if total > 0 else 0.0


class TemporalSequenceRule(MergeRule):
    """Merge if scenes are temporally adjacent."""

    def __init__(self, max_gap_ms: float = 500.0):
        super().__init__(MergeRuleType.TEMPORAL_SEQUENCE, priority=70)
        self.max_gap_ms = max_gap_ms

    def apply(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> MergeRuleResult:
        """Check if scenes are temporally adjacent."""
        if scene_a.video_id != scene_b.video_id:
            return MergeRuleResult.SEPARATE

        # Check temporal order
        if scene_a.end_time > scene_b.start_time:
            return MergeRuleResult.SEPARATE

        # Check temporal gap
        gap_ms = (scene_b.start_time - scene_a.end_time) * 1000
        if gap_ms <= self.max_gap_ms:
            return MergeRuleResult.MERGE

        return MergeRuleResult.SEPARATE

    def score(self, scene_a: SceneSemantic, scene_b: SceneSemantic) -> float:
        """Score based on temporal proximity."""
        if scene_a.video_id != scene_b.video_id:
            return 0.0

        gap_ms = (scene_b.start_time - scene_a.end_time) * 1000
        if gap_ms < 0:  # Overlapping
            return 1.0

        # Score decreases with gap
        return max(0.0, 1.0 - (gap_ms / self.max_gap_ms))


class MergeRuleSet:
    """Ordered collection of merge rules.

    Rules are applied in priority order (highest first).
    First definitive result (MERGE or SEPARATE) wins.
    """

    def __init__(self):
        self.rules: List[MergeRule] = []
        self._init_default_rules()

    def _init_default_rules(self) -> None:
        """Initialize default rule set."""
        self.add_rule(DialogueContinuityRule())
        self.add_rule(ActionSequenceRule())
        self.add_rule(CharacterInteractionRule())
        self.add_rule(TemporalSequenceRule())

    def add_rule(self, rule: MergeRule) -> None:
        """Add rule to set."""
        self.rules.append(rule)
        # Sort by priority (highest first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def apply(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> tuple[MergeRuleResult, Optional[MergeRule]]:
        """Apply rule set to determine merge decision.

        Returns:
            (decision, rule_that_decided) tuple
        """
        for rule in self.rules:
            result = rule.apply(scene_a, scene_b)

            if result != MergeRuleResult.UNDECIDED:
                return result, rule

        # No rule decided: default to undecided
        return MergeRuleResult.UNDECIDED, None

    def score(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> dict:
        """Score according to all rules.

        Returns:
            {
                "overall_score": float [0.0, 1.0],
                "rule_scores": {rule_type: score},
                "decision": MergeRuleResult,
                "deciding_rule": Optional[MergeRule],
            }
        """
        rule_scores = {}
        for rule in self.rules:
            score = rule.score(scene_a, scene_b)
            rule_scores[rule.rule_type.value] = score

        # Overall score is weighted average
        total_score = sum(rule_scores.values())
        overall_score = total_score / len(self.rules) if self.rules else 0.0

        decision, deciding_rule = self.apply(scene_a, scene_b)

        return {
            "overall_score": overall_score,
            "rule_scores": rule_scores,
            "decision": decision.value,
            "deciding_rule": deciding_rule.rule_type.value if deciding_rule else None,
        }
