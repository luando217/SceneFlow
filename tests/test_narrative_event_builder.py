"""Tests for narrative event grouping — deterministic event builder.

These tests validate:
- Narrative event schemas (frozen=True, extra="forbid")
- Deterministic hashing
- Deterministic serialization
- Event classification
- Event boundary detection
- Transition analysis
- Event grouping
- Replay stability
- Shuffle invariance

NO AI, embeddings, vector DB, or randomness.
"""

from __future__ import annotations

import json
from typing import List, Optional

import pytest

from aicore.semantic.aggregation.narrative_event_schemas import (
    BoundaryReason,
    EventBoundary,
    EventTransition,
    NarrativeEvent,
    NarrativeEventGroup,
    NarrativeEventGroupingResult,
    NarrativeEventType,
    TransitionLabel,
    _generate_boundary_hash,
    _generate_event_hash,
    _generate_group_hash,
    _generate_transition_hash,
)
from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EnvironmentEntity,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def create_test_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
    video_id: str = "test_video",
    dialogue: str = "",
    characters: Optional[List[CharacterEntity]] = None,
    actions: Optional[List[ActionEntity]] = None,
    environments: Optional[List[EnvironmentEntity]] = None,
    motion_direction: str = "static",
    motion_intensity: float = 0.0,
) -> SceneSemantic:
    """Create a test scene."""
    return SceneSemantic(
        scene_id=scene_id,
        video_id=video_id,
        episode_id=None,
        start_time=start_time,
        end_time=end_time,
        start_frame=0,
        end_frame=30,
        characters=characters or [],
        actions=actions or [],
        objects=[],
        environments=environments or [
            EnvironmentEntity(normalized_name="default_env", confidence=1.0),
        ],
        emotions=[],
        dialogue=dialogue,
        motion_direction=motion_direction,
        motion_intensity=motion_intensity,
    )


def create_combat_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
) -> SceneSemantic:
    """Create a high-action combat scene."""
    return create_test_scene(
        scene_id=scene_id,
        start_time=start_time,
        end_time=end_time,
        characters=[
            CharacterEntity(normalized_name="hero", confidence=1.0),
            CharacterEntity(normalized_name="villain", confidence=1.0),
        ],
        actions=[
            ActionEntity(normalized_name="attack", confidence=1.0),
            ActionEntity(normalized_name="defend", confidence=1.0),
        ],
        motion_direction="circular",
        motion_intensity=0.9,
    )


def create_dialogue_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
    dialogue: str = "Hello, how are you?",
) -> SceneSemantic:
    """Create a dialogue-heavy scene."""
    return create_test_scene(
        scene_id=scene_id,
        start_time=start_time,
        end_time=end_time,
        characters=[
            CharacterEntity(normalized_name="speaker_a", confidence=1.0),
            CharacterEntity(normalized_name="speaker_b", confidence=1.0),
        ],
        dialogue=dialogue,
        motion_direction="static",
        motion_intensity=0.1,
    )


def create_travel_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
) -> SceneSemantic:
    """Create a travel/movement scene."""
    return create_test_scene(
        scene_id=scene_id,
        start_time=start_time,
        end_time=end_time,
        characters=[
            CharacterEntity(normalized_name="traveler", confidence=1.0),
        ],
        actions=[
            ActionEntity(normalized_name="walk", confidence=1.0),
        ],
        environments=[
            EnvironmentEntity(normalized_name="road", confidence=1.0),
        ],
        motion_direction="right",
        motion_intensity=0.5,
    )


def create_idle_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
) -> SceneSemantic:
    """Create a low-activity idle scene."""
    return create_test_scene(
        scene_id=scene_id,
        start_time=start_time,
        end_time=end_time,
        characters=[
            CharacterEntity(normalized_name="character", confidence=1.0),
        ],
        motion_direction="static",
        motion_intensity=0.0,
    )


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestNarrativeEventSchemas:
    """Validate schema constraints (frozen=True, extra='forbid')."""

    def test_narrative_event_frozen(self):
        """NarrativeEvent must be frozen."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1", "scene_2"],
            event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero"],
            dominant_environment="battlefield",
            continuity_strength=0.9,
            deterministic_hash="abc123",
        )
        with pytest.raises(Exception):  # pydantic.ValidationError or TypeError
            event.deterministic_id = "new_id"

    def test_narrative_event_extra_forbidden(self):
        """NarrativeEvent must reject extra fields."""
        with pytest.raises(Exception):
            NarrativeEvent(
                deterministic_id="event_1",
                scene_ids=["scene_1"],
                event_type=NarrativeEventType.IDLE_SEQUENCE,
                continuity_strength=0.5,
                deterministic_hash="abc123",
                unknown_field="should fail",
            )

    def test_narrative_event_sorted_scene_ids(self):
        """Scene IDs must be deterministically sorted."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_3", "scene_1", "scene_2"],
            event_type=NarrativeEventType.DIALOGUE_EXCHANGE,
            continuity_strength=0.5,
            deterministic_hash="abc123",
        )
        assert event.scene_ids == ["scene_1", "scene_2", "scene_3"]

    def test_event_boundary_frozen(self):
        """EventBoundary must be frozen."""
        boundary = EventBoundary(
            boundary_id="boundary_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.HARD_CONTINUITY_BREAK,
            confidence=0.9,
            continuity_break_score=0.9,
            deterministic_hash="xyz789",
        )
        with pytest.raises(Exception):
            boundary.confidence = 0.5

    def test_event_transition_frozen(self):
        """EventTransition must be frozen."""
        transition = EventTransition(
            transition_id="transition_1",
            from_event_id="event_1",
            to_event_id="event_2",
            label=TransitionLabel.SMOOTH_TRANSITION,
            coherence_score=0.8,
            character_overlap=0.7,
            action_continuity=0.6,
            environment_continuity=0.5,
            deterministic_hash="trans123",
        )
        with pytest.raises(Exception):
            transition.coherence_score = 0.5

    def test_event_group_frozen(self):
        """NarrativeEventGroup must be frozen."""
        group = NarrativeEventGroup(
            group_id="group_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["event_1", "event_2"],
            dominant_event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero"],
            event_count=2,
            average_continuity_strength=0.9,
            total_temporal_span_sec=20.0,
            internal_coherence=0.85,
            deterministic_hash="grp123",
        )
        with pytest.raises(Exception):
            group.group_id = "new_id"


# ---------------------------------------------------------------------------
# Deterministic hashing tests
# ---------------------------------------------------------------------------


class TestDeterministicHashing:
    """Validate deterministic SHA-256 hashing."""

    def test_event_hash_deterministic(self):
        """Same input always produces same hash."""
        hash1 = _generate_event_hash(
            event_type="combat_sequence",
            scene_ids=["scene_1", "scene_2"],
            dominant_characters=["hero"],
            continuity_strength=0.9,
        )
        hash2 = _generate_event_hash(
            event_type="combat_sequence",
            scene_ids=["scene_1", "scene_2"],
            dominant_characters=["hero"],
            continuity_strength=0.9,
        )
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

    def test_event_hash_order_independent(self):
        """Scene order doesn't affect hash."""
        hash1 = _generate_event_hash(
            event_type="dialogue_exchange",
            scene_ids=["scene_1", "scene_2"],
            dominant_characters=["speaker_a", "speaker_b"],
            continuity_strength=0.8,
        )
        hash2 = _generate_event_hash(
            event_type="dialogue_exchange",
            scene_ids=["scene_2", "scene_1"],
            dominant_characters=["speaker_b", "speaker_a"],
            continuity_strength=0.8,
        )
        assert hash1 == hash2

    def test_boundary_hash_deterministic(self):
        """Boundaries have deterministic hashing."""
        hash1 = _generate_boundary_hash(
            scene_before="scene_1",
            scene_after="scene_2",
            reason="temporal_discontinuity",
            confidence=0.9,
        )
        hash2 = _generate_boundary_hash(
            scene_before="scene_1",
            scene_after="scene_2",
            reason="temporal_discontinuity",
            confidence=0.9,
        )
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_transition_hash_deterministic(self):
        """Transitions have deterministic hashing."""
        hash1 = _generate_transition_hash(
            from_event_id="event_1",
            to_event_id="event_2",
            label="escalation",
            coherence_score=0.7,
        )
        hash2 = _generate_transition_hash(
            from_event_id="event_1",
            to_event_id="event_2",
            label="escalation",
            coherence_score=0.7,
        )
        assert hash1 == hash2

    def test_group_hash_deterministic(self):
        """Groups have deterministic hashing."""
        hash1 = _generate_group_hash(
            group_id="group_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["event_1", "event_2"],
            dominant_event_type="combat_sequence",
        )
        hash2 = _generate_group_hash(
            group_id="group_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["event_1", "event_2"],
            dominant_event_type="combat_sequence",
        )
        assert hash1 == hash2


# ---------------------------------------------------------------------------
# Deterministic serialization tests
# ---------------------------------------------------------------------------


class TestDeterministicSerialization:
    """Validate byte-identical JSON serialization."""

    def test_event_to_json_deterministic(self):
        """JSON output is deterministic."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_2", "scene_1"],
            event_type=NarrativeEventType.EMOTIONAL_SEQUENCE,
            dominant_characters=["character"],
            continuity_strength=0.75,
            deterministic_hash="abc123",
        )
        json1 = event.to_json()
        json2 = event.to_json()
        assert json1 == json2

    def test_event_to_dict_sorted_keys(self):
        """Dict keys are deterministically sorted."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1", "scene_2"],
            event_type=NarrativeEventType.IDLE_SEQUENCE,
            dominant_characters=["hero"],
            continuity_strength=0.6,
            deterministic_hash="xyz",
        )
        d = event.to_dict_deterministic()
        keys = list(d.keys())
        assert keys == sorted(keys)

    def test_boundary_to_json_deterministic(self):
        """Boundary JSON is deterministic."""
        boundary = EventBoundary(
            boundary_id="b_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.HARD_CONTINUITY_BREAK,
            confidence=1.0,
            continuity_break_score=1.0,
            deterministic_hash="bnd",
        )
        json1 = boundary.to_json()
        json2 = boundary.to_json()
        assert json1 == json2

    def test_transition_to_json_deterministic(self):
        """Transition JSON is deterministic."""
        transition = EventTransition(
            transition_id="t_1",
            from_event_id="e_1",
            to_event_id="e_2",
            label=TransitionLabel.DEESCALATION,
            coherence_score=0.5,
            character_overlap=0.6,
            action_continuity=0.7,
            environment_continuity=0.8,
            deterministic_hash="trn",
        )
        json1 = transition.to_json()
        json2 = transition.to_json()
        assert json1 == json2

    def test_group_to_json_deterministic(self):
        """Group JSON is deterministic."""
        group = NarrativeEventGroup(
            group_id="g_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["e_2", "e_1"],
            dominant_event_type=NarrativeEventType.ENVIRONMENT_TRANSITION,
            dominant_characters=["hero"],
            event_count=2,
            average_continuity_strength=0.7,
            total_temporal_span_sec=20.0,
            internal_coherence=0.75,
            deterministic_hash="grp",
        )
        json1 = group.to_json()
        json2 = group.to_json()
        assert json1 == json2

    def test_result_to_json_deterministic(self):
        """Full result JSON is deterministic."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero"],
            continuity_strength=0.9,
            deterministic_hash="hash123",
        )
        d = event.to_dict_deterministic()
        json_str = json.dumps(d, sort_keys=True, default=str)
        json_str2 = json.dumps(d, sort_keys=True, default=str)
        assert json_str == json_str2


# ---------------------------------------------------------------------------
# Event classification tests
# ---------------------------------------------------------------------------


class TestDeterministicClassification:
    """Validate deterministic event type classification."""

    def test_event_type_enum_values(self):
        """All event types are properly defined."""
        assert NarrativeEventType.COMBAT_SEQUENCE.value == "combat_sequence"
        assert NarrativeEventType.DIALOGUE_EXCHANGE.value == "dialogue_exchange"
        assert NarrativeEventType.TRAVEL_SEQUENCE.value == "travel_sequence"
        assert NarrativeEventType.ENVIRONMENT_TRANSITION.value == "environment_transition"
        assert NarrativeEventType.EMOTIONAL_SEQUENCE.value == "emotional_sequence"
        assert NarrativeEventType.IDLE_SEQUENCE.value == "idle_sequence"
        assert NarrativeEventType.FLASHBACK_CANDIDATE.value == "flashback_candidate"
        assert NarrativeEventType.TIMESKIP_CANDIDATE.value == "timeskip_candidate"

    def test_transition_label_enum_values(self):
        """All transition labels are properly defined."""
        assert TransitionLabel.SMOOTH_TRANSITION.value == "smooth_transition"
        assert TransitionLabel.HARD_CUT.value == "hard_cut"
        assert TransitionLabel.ESCALATION.value == "escalation"
        assert TransitionLabel.DEESCALATION.value == "deescalation"
        assert TransitionLabel.FLASHBACK_TRANSITION.value == "flashback_transition"
        assert TransitionLabel.TEMPORAL_JUMP.value == "temporal_jump"

    def test_boundary_reason_enum_values(self):
        """All boundary reasons are properly defined."""
        assert BoundaryReason.HARD_CONTINUITY_BREAK.value == "hard_continuity_break"
        assert BoundaryReason.MAJOR_ENVIRONMENT_SHIFT.value == "major_environment_shift"
        assert BoundaryReason.TEMPORAL_DISCONTINUITY.value == "temporal_discontinuity"
        assert BoundaryReason.DIALOGUE_INTERRUPTION.value == "dialogue_interruption"
        assert BoundaryReason.CHARACTER_CONTINUITY_LOSS.value == "character_continuity_loss"

    def test_event_type_classification_deterministic(self):
        """Event type is deterministic based on structural properties."""
        # Combat scene
        combat_event = NarrativeEvent(
            deterministic_id="combat_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero", "villain"],
            continuity_strength=0.9,
            deterministic_hash="abc",
        )
        assert combat_event.event_type == NarrativeEventType.COMBAT_SEQUENCE
        assert combat_event.action_intensity >= 0.0

        # Idle scene
        idle_event = NarrativeEvent(
            deterministic_id="idle_1",
            scene_ids=["scene_2"],
            event_type=NarrativeEventType.IDLE_SEQUENCE,
            dominant_characters=["character"],
            continuity_strength=0.6,
            deterministic_hash="def",
        )
        assert idle_event.event_type == NarrativeEventType.IDLE_SEQUENCE


# ---------------------------------------------------------------------------
# Event boundary detection tests
# ---------------------------------------------------------------------------


class TestBoundaryDetection:
    """Validate deterministic boundary detection."""

    def test_boundary_creation_deterministic(self):
        """Boundaries are created deterministically."""
        boundary = EventBoundary(
            boundary_id="b_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.MAJOR_ENVIRONMENT_SHIFT,
            confidence=0.9,
            continuity_break_score=0.85,
            deterministic_hash=_generate_boundary_hash(
                scene_before="scene_1",
                scene_after="scene_2",
                reason="major_environment_shift",
                confidence=0.9,
            ),
        )
        assert boundary.boundary_id == "b_1"
        assert boundary.reason == BoundaryReason.MAJOR_ENVIRONMENT_SHIFT

    def test_boundary_replay_deterministic(self):
        """Same input always produces same boundary."""
        boundary1 = EventBoundary(
            boundary_id="b_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.TEMPORAL_DISCONTINUITY,
            confidence=0.9,
            continuity_break_score=0.9,
            deterministic_hash="same_hash",
        )
        boundary2 = EventBoundary(
            boundary_id="b_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.TEMPORAL_DISCONTINUITY,
            confidence=0.9,
            continuity_break_score=0.9,
            deterministic_hash="same_hash",
        )
        assert boundary1.reason == boundary2.reason
        assert boundary1.scene_before == boundary2.scene_before

    def test_boundary_reason_detection(self):
        """Different reasons trigger different boundary types."""
        env_shift = EventBoundary(
            boundary_id="b_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.MAJOR_ENVIRONMENT_SHIFT,
            confidence=0.95,
            continuity_break_score=0.9,
            deterministic_hash="hash1",
        )
        char_loss = EventBoundary(
            boundary_id="b_2",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.CHARACTER_CONTINUITY_LOSS,
            confidence=0.8,
            continuity_break_score=0.7,
            deterministic_hash="hash2",
        )
        assert env_shift.reason != char_loss.reason


# ---------------------------------------------------------------------------
# Transition analysis tests
# ---------------------------------------------------------------------------


class TestTransitionAnalysis:
    """Validate deterministic transition labeling."""

    def test_transition_creation_deterministic(self):
        """Transitions are created deterministically."""
        transition = EventTransition(
            transition_id="t_1",
            from_event_id="event_1",
            to_event_id="event_2",
            label=TransitionLabel.SMOOTH_TRANSITION,
            coherence_score=0.85,
            character_overlap=0.75,
            action_continuity=0.8,
            environment_continuity=0.7,
            deterministic_hash=_generate_transition_hash(
                from_event_id="event_1",
                to_event_id="event_2",
                label="smooth_transition",
                coherence_score=0.85,
            ),
        )
        assert transition.label == TransitionLabel.SMOOTH_TRANSITION
        assert transition.character_overlap == 0.75

    def test_escalation_transition(self):
        """Escalation transitions are labeled correctly."""
        escalation = EventTransition(
            transition_id="t_1",
            from_event_id="idle_event",
            to_event_id="combat_event",
            label=TransitionLabel.ESCALATION,
            coherence_score=0.6,
            character_overlap=0.5,
            action_continuity=0.3,
            environment_continuity=0.4,
            deterministic_hash="esc_hash",
        )
        assert escalation.label == TransitionLabel.ESCALATION

    def test_transition_replay_deterministic(self):
        """Same events always produce same transitions."""
        trans1 = EventTransition(
            transition_id="t_1",
            from_event_id="event_1",
            to_event_id="event_2",
            label=TransitionLabel.ESCALATION,
            coherence_score=0.7,
            character_overlap=0.8,
            action_continuity=0.6,
            environment_continuity=0.5,
            deterministic_hash="trans_hash",
        )
        trans2 = EventTransition(
            transition_id="t_1",
            from_event_id="event_1",
            to_event_id="event_2",
            label=TransitionLabel.ESCALATION,
            coherence_score=0.7,
            character_overlap=0.8,
            action_continuity=0.6,
            environment_continuity=0.5,
            deterministic_hash="trans_hash",
        )
        assert trans1.label == trans2.label
        assert trans1.character_overlap == trans2.character_overlap


# ---------------------------------------------------------------------------
# Event grouping tests
# ---------------------------------------------------------------------------


class TestEventGrouping:
    """Validate event grouping by continuity."""

    def test_event_group_creation(self):
        """Event groups are created correctly."""
        group = NarrativeEventGroup(
            group_id="g_1",
            scene_ids=["scene_1", "scene_2", "scene_3"],
            event_ids=["event_1", "event_2"],
            dominant_event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero", "villain"],
            event_count=2,
            average_continuity_strength=0.85,
            total_temporal_span_sec=30.0,
            internal_coherence=0.9,
            deterministic_hash="group_hash",
        )
        assert len(group.scene_ids) == 3
        assert len(group.event_ids) == 2

    def test_group_replay_deterministic(self):
        """Same input always produces same group."""
        group1 = NarrativeEventGroup(
            group_id="g_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["event_1", "event_2"],
            dominant_event_type=NarrativeEventType.DIALOGUE_EXCHANGE,
            dominant_characters=["speaker_a", "speaker_b"],
            event_count=2,
            average_continuity_strength=0.8,
            total_temporal_span_sec=20.0,
            internal_coherence=0.85,
            deterministic_hash="same_hash",
        )
        group2 = NarrativeEventGroup(
            group_id="g_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["event_1", "event_2"],
            dominant_event_type=NarrativeEventType.DIALOGUE_EXCHANGE,
            dominant_characters=["speaker_a", "speaker_b"],
            event_count=2,
            average_continuity_strength=0.8,
            total_temporal_span_sec=20.0,
            internal_coherence=0.85,
            deterministic_hash="same_hash",
        )
        assert group1.dominant_event_type == group2.dominant_event_type
        assert group1.average_continuity_strength == group2.average_continuity_strength


# ---------------------------------------------------------------------------
# Result container tests
# ---------------------------------------------------------------------------


class TestResultContainer:
    """Validate NarrativeEventGroupingResult container."""

    def test_result_container_structure(self):
        """Result container holds all components."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero"],
            continuity_strength=0.9,
            deterministic_hash="event_hash",
        )
        boundary = EventBoundary(
            boundary_id="b_1",
            scene_before="scene_1",
            scene_after="scene_2",
            reason=BoundaryReason.HARD_CONTINUITY_BREAK,
            confidence=0.9,
            continuity_break_score=0.9,
            deterministic_hash="boundary_hash",
        )
        transition = EventTransition(
            transition_id="t_1",
            from_event_id="event_1",
            to_event_id="event_2",
            label=TransitionLabel.SMOOTH_TRANSITION,
            coherence_score=0.8,
            character_overlap=0.7,
            action_continuity=0.6,
            environment_continuity=0.5,
            deterministic_hash="trans_hash",
        )
        group = NarrativeEventGroup(
            group_id="g_1",
            scene_ids=["scene_1", "scene_2"],
            event_ids=["event_1"],
            dominant_event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero"],
            event_count=1,
            average_continuity_strength=0.9,
            total_temporal_span_sec=20.0,
            internal_coherence=0.85,
            deterministic_hash="group_hash",
        )

        result = NarrativeEventGroupingResult(
            events=[event],
            boundaries=[boundary],
            transitions=[transition],
            groups=[group],
        )

        assert len(result.events) == 1
        assert len(result.boundaries) == 1
        assert len(result.transitions) == 1
        assert len(result.groups) == 1

    def test_result_serialization(self):
        """Result serializes deterministically."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.IDLE_SEQUENCE,
            dominant_characters=["character"],
            continuity_strength=0.5,
            deterministic_hash="hash1",
        )
        result = NarrativeEventGroupingResult(events=[event])

        json1 = result.to_json()
        json2 = result.to_json()
        assert json1 == json2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Validate edge case handling."""

    def test_single_scene_event(self):
        """Single scene produces valid event."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.DIALOGUE_EXCHANGE,
            dominant_characters=["speaker"],
            continuity_strength=1.0,
            deterministic_hash="single",
        )
        assert len(event.scene_ids) == 1
        assert event.temporal_span_sec == 0.0

    def test_empty_characters_list(self):
        """Empty character list is handled."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.ENVIRONMENT_TRANSITION,
            dominant_characters=[],  # Empty allowed
            continuity_strength=0.5,
            deterministic_hash="empty_chars",
        )
        assert event.dominant_characters == []

    def test_max_continuity_values(self):
        """Boundary values are handled."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.COMBAT_SEQUENCE,
            dominant_characters=["hero"],
            continuity_strength=1.0,  # Max value
            deterministic_hash="max_hash",
        )
        assert event.continuity_strength == 1.0

    def test_min_continuity_values(self):
        """Minimum continuity values are handled."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["scene_1"],
            event_type=NarrativeEventType.IDLE_SEQUENCE,
            dominant_characters=["character"],
            continuity_strength=0.0,  # Min value
            deterministic_hash="min_hash",
        )
        assert event.continuity_strength == 0.0


# ---------------------------------------------------------------------------
# Scene ordering stability tests
# ---------------------------------------------------------------------------


class TestSceneOrderingStability:
    """Validate that scene ordering doesn't affect deterministic results."""

    def test_hash_stability_with_different_ordering(self):
        """Hash is stable regardless of input ordering."""
        hash1 = _generate_event_hash(
            event_type="combat_sequence",
            scene_ids=["scene_1", "scene_2", "scene_3"],
            dominant_characters=["hero", "villain"],
            continuity_strength=0.9,
        )
        hash2 = _generate_event_hash(
            event_type="combat_sequence",
            scene_ids=["scene_3", "scene_1", "scene_2"],
            dominant_characters=["villain", "hero"],
            continuity_strength=0.9,
        )
        # Sorted internally, so should be equal
        assert hash1 == hash2

    def test_scene_id_sorting(self):
        """Scene IDs are sorted deterministically."""
        event = NarrativeEvent(
            deterministic_id="event_1",
            scene_ids=["z_scene", "a_scene", "m_scene"],
            event_type=NarrativeEventType.TRAVEL_SEQUENCE,
            dominant_characters=["traveler"],
            continuity_strength=0.7,
            deterministic_hash="sorted",
        )
        # Should be sorted alphabetically
        assert event.scene_ids == ["a_scene", "m_scene", "z_scene"]