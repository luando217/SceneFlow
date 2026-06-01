"""Tests for MergeRule and MergeRuleSet."""

import pytest

from aicore.semantic.aggregation.merge_rule import (
    DialogueContinuityRule,
    ActionSequenceRule,
    CharacterInteractionRule,
    TemporalSequenceRule,
    MergeRuleSet,
    MergeRuleResult,
)
from tests.fixtures.scene_semantic_fixtures import (
    create_test_scene,
    create_multi_character_scene,
)


class TestDialogueContinuityRule:
    """Test DialogueContinuityRule."""

    def test_rule_creation(self):
        """Test creating dialogue continuity rule."""
        rule = DialogueContinuityRule()

        assert rule.rule_type.value == "dialogue_continuity"
        assert rule.priority == 100

    def test_apply_both_have_dialogue(self):
        """Test applying rule when both scenes have dialogue."""
        rule = DialogueContinuityRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_a.dialogue = "Hello"

        scene_b = create_test_scene("scene_2", 1.0, 2.0)
        scene_b.dialogue = "Hi there"

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.MERGE

    def test_apply_one_empty_dialogue(self):
        """Test applying rule when one has no dialogue."""
        rule = DialogueContinuityRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_a.dialogue = "Hello"

        scene_b = create_test_scene("scene_2", 1.0, 2.0)
        scene_b.dialogue = None

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.UNDECIDED

    def test_score_both_have_dialogue(self):
        """Test scoring when both have dialogue."""
        rule = DialogueContinuityRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_a.dialogue = "Hello"

        scene_b = create_test_scene("scene_2", 1.0, 2.0)
        scene_b.dialogue = "Hi"

        score = rule.score(scene_a, scene_b)

        assert score == 1.0


class TestActionSequenceRule:
    """Test ActionSequenceRule."""

    def test_rule_creation(self):
        """Test creating action sequence rule."""
        rule = ActionSequenceRule()

        assert rule.rule_type.value == "action_sequence"
        assert rule.priority == 90

    def test_apply_shared_actions(self):
        """Test applying rule with shared actions."""
        from aicore.semantic.schemas.entities import ActionEntity

        rule = ActionSequenceRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_a.actions = [ActionEntity(name="run", normalized_name="run", confidence=1.0)]

        scene_b = create_test_scene("scene_2", 1.0, 2.0)
        scene_b.actions = [ActionEntity(name="run", normalized_name="run", confidence=1.0)]

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.MERGE

    def test_apply_different_actions(self):
        """Test applying rule with different actions."""
        from aicore.semantic.schemas.entities import ActionEntity

        rule = ActionSequenceRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_a.actions = [ActionEntity(name="run", normalized_name="run", confidence=1.0)]

        scene_b = create_test_scene("scene_2", 1.0, 2.0)
        scene_b.actions = [ActionEntity(name="walk", normalized_name="walk", confidence=1.0)]

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.UNDECIDED


class TestCharacterInteractionRule:
    """Test CharacterInteractionRule."""

    def test_rule_creation(self):
        """Test creating character interaction rule."""
        rule = CharacterInteractionRule()

        assert rule.rule_type.value == "character_interaction"
        assert rule.priority == 80

    def test_apply_shared_characters(self):
        """Test applying rule with shared characters."""
        rule = CharacterInteractionRule()

        scene_a = create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob", "Charlie"])
        scene_b = create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice", "Bob"])

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.MERGE

    def test_apply_one_character_overlap(self):
        """Test applying rule with only one character overlap."""
        rule = CharacterInteractionRule()

        scene_a = create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob"])
        scene_b = create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice", "Charlie"])

        result = rule.apply(scene_a, scene_b)

        # Only 1 overlap < 2 threshold
        assert result == MergeRuleResult.UNDECIDED

    def test_score_shared_characters(self):
        """Test scoring with shared characters."""
        rule = CharacterInteractionRule()

        scene_a = create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob"])
        scene_b = create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice", "Bob"])

        score = rule.score(scene_a, scene_b)

        assert score == 1.0


class TestTemporalSequenceRule:
    """Test TemporalSequenceRule."""

    def test_rule_creation(self):
        """Test creating temporal sequence rule."""
        rule = TemporalSequenceRule()

        assert rule.rule_type.value == "temporal_sequence"
        assert rule.priority == 70

    def test_apply_adjacent_scenes(self):
        """Test applying rule to adjacent scenes."""
        rule = TemporalSequenceRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0, video_id="video_1")
        scene_b = create_test_scene("scene_2", 1.0, 2.0, video_id="video_1")

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.MERGE

    def test_apply_different_videos(self):
        """Test applying rule to different videos."""
        rule = TemporalSequenceRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0, video_id="video_1")
        scene_b = create_test_scene("scene_2", 1.0, 2.0, video_id="video_2")

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.SEPARATE

    def test_apply_large_gap(self):
        """Test applying rule with large time gap."""
        rule = TemporalSequenceRule(max_gap_ms=100.0)

        scene_a = create_test_scene("scene_1", 0.0, 1.0, video_id="video_1")
        scene_b = create_test_scene("scene_2", 2.0, 3.0, video_id="video_1")

        result = rule.apply(scene_a, scene_b)

        assert result == MergeRuleResult.SEPARATE

    def test_score_close_scenes(self):
        """Test scoring for close scenes."""
        rule = TemporalSequenceRule(max_gap_ms=500.0)

        scene_a = create_test_scene("scene_1", 0.0, 1.0, video_id="video_1")
        scene_b = create_test_scene("scene_2", 1.0, 2.0, video_id="video_1")

        score = rule.score(scene_a, scene_b)

        assert score == 1.0


class TestMergeRuleSet:
    """Test MergeRuleSet functionality."""

    def test_ruleset_creation(self):
        """Test creating rule set."""
        ruleset = MergeRuleSet()

        assert len(ruleset.rules) > 0

    def test_ruleset_priority_order(self):
        """Test that rules are ordered by priority."""
        ruleset = MergeRuleSet()

        priorities = [r.priority for r in ruleset.rules]

        # Should be in descending order
        assert priorities == sorted(priorities, reverse=True)

    def test_apply_returns_first_decision(self):
        """Test that apply returns first decisive rule."""
        ruleset = MergeRuleSet()

        scene_a = create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice", "Bob", "Charlie"])
        scene_b = create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice", "Bob"])

        result, rule = ruleset.apply(scene_a, scene_b)

        assert result != MergeRuleResult.UNDECIDED
        assert rule is not None

    def test_score_all_rules(self):
        """Test that score computes all rules."""
        ruleset = MergeRuleSet()

        scene_a = create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice"])
        scene_b = create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice"])

        scores = ruleset.score(scene_a, scene_b)

        assert "overall_score" in scores
        assert "rule_scores" in scores
        assert "decision" in scores
        assert "deciding_rule" in scores

    def test_score_value_range(self):
        """Test that scores are in valid range."""
        ruleset = MergeRuleSet()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_b = create_test_scene("scene_2", 1.0, 2.0)

        scores = ruleset.score(scene_a, scene_b)

        assert 0.0 <= scores["overall_score"] <= 1.0
        for rule_score in scores["rule_scores"].values():
            assert 0.0 <= rule_score <= 1.0


class TestMergeRuleDeterminism:
    """Test deterministic properties of merge rules."""

    def test_rule_deterministic_apply(self):
        """Test that rule application is deterministic."""
        rule = TemporalSequenceRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_b = create_test_scene("scene_2", 1.0, 2.0)

        result1 = rule.apply(scene_a, scene_b)
        result2 = rule.apply(scene_a, scene_b)
        result3 = rule.apply(scene_a, scene_b)

        assert result1 == result2 == result3

    def test_rule_deterministic_score(self):
        """Test that rule scoring is deterministic."""
        rule = TemporalSequenceRule()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_b = create_test_scene("scene_2", 1.0, 2.0)

        score1 = rule.score(scene_a, scene_b)
        score2 = rule.score(scene_a, scene_b)
        score3 = rule.score(scene_a, scene_b)

        assert score1 == score2 == score3

    def test_ruleset_deterministic_decision(self):
        """Test that ruleset decisions are deterministic."""
        ruleset = MergeRuleSet()

        scene_a = create_multi_character_scene("scene_1", 0.0, 1.0, ["Alice"])
        scene_b = create_multi_character_scene("scene_2", 1.0, 2.0, ["Alice"])

        result1, rule1 = ruleset.apply(scene_a, scene_b)
        result2, rule2 = ruleset.apply(scene_a, scene_b)

        assert result1 == result2
        assert rule1 == rule2

    def test_ruleset_deterministic_score(self):
        """Test that ruleset scoring is deterministic."""
        ruleset = MergeRuleSet()

        scene_a = create_test_scene("scene_1", 0.0, 1.0)
        scene_b = create_test_scene("scene_2", 1.0, 2.0)

        scores1 = ruleset.score(scene_a, scene_b)
        scores2 = ruleset.score(scene_a, scene_b)

        assert scores1 == scores2
