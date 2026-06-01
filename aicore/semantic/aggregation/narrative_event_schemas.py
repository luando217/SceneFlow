"""Narrative event schemas — immutable, deterministic contracts for narrative events.

These schemas define:
- NarrativeEvent: single narrative event (combat, dialogue, travel, etc.)
- NarrativeEventGroup: group of related narrative events
- EventTransition: transition between event groups
- EventBoundary: detected event boundary
- NarrativeEventBuilder: deterministic event builder

All schemas are:
- frozen=True — immutable after construction
- extra="forbid" — no surprise fields
- deterministic — stable, reproducible across runs
- replay-safe — same data → same result
- no AI/embeddings/vector DB/randomness
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, field_validator

from aicore.semantic.utils.replay_utils import DeterministicClock


def _schema_version() -> str:
    return "Phase3.3"


def _now_timestamp() -> float:
    """Deterministic zero timestamp — never uses wall clock time."""
    return DeterministicClock.zero_timestamp()


def _sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return deterministically-sorted copy of a list."""
    if items is None:
        return []
    return sorted(items)


def _sorted_floats(items: Optional[List[float]]) -> List[float]:
    """Return deterministically-ordered copy of a float list."""
    if items is None:
        return []
    return sorted(items)


# ---------------------------------------------------------------------------
# Narrative event type enumeration
# ---------------------------------------------------------------------------


class NarrativeEventType(str, Enum):
    """Deterministic narrative event types.
    
    Classification is based on structural properties only:
    - dialogue content presence
    - action intensity
    - character count
    - environment stability
    - temporal gap
    """

    COMBAT_SEQUENCE = "combat_sequence"
    """High action intensity, multiple characters, dynamic environment."""

    DIALOGUE_EXCHANGE = "dialogue_exchange"
    """Significant dialogue, conversation-focused, stable environment."""

    TRAVEL_SEQUENCE = "travel_sequence"
    """Environment transitions, movement between locations."""

    ENVIRONMENT_TRANSITION = "environment_transition"
    """Major location/setting change."""

    EMOTIONAL_SEQUENCE = "emotional_sequence"
    """Character-focused, emotional content, limited action."""

    IDLE_SEQUENCE = "idle_sequence"
    """Low activity, static scenes, minimal changes."""

    FLASHBACK_CANDIDATE = "flashback_candidate"
    """Temporal discontinuity detected, needs verification."""

    TIMESKIP_CANDIDATE = "timeskip_candidate"
    """Large temporal gap detected, narrative jump."""


class TransitionLabel(str, Enum):
    """Deterministic transition labels between event groups."""

    SMOOTH_TRANSITION = "smooth_transition"
    """Gradual, natural progression between events."""

    HARD_CUT = "hard_cut"
    """Abrupt change, no narrative bridge."""

    ESCALATION = "escalation"
    """Intensity increasing, tension rising."""

    DEESCALATION = "deescalation"
    """Intensity decreasing, tension falling."""

    FLASHBACK_TRANSITION = "flashback_transition"
    """Transition to/from flashback content."""

    TEMPORAL_JUMP = "temporal_jump"
    """Major time skip detected."""


class BoundaryReason(str, Enum):
    """Deterministic reasons for event boundary detection."""

    HARD_CONTINUITY_BREAK = "hard_continuity_break"
    """Complete continuity chain break detected."""

    MAJOR_ENVIRONMENT_SHIFT = "major_environment_shift"
    """Environment changed completely."""

    TEMPORAL_DISCONTINUITY = "temporal_discontinuity"
    """Time gap too large for seamless flow."""

    DIALOGUE_INTERRUPTION = "dialogue_interruption"
    """Dialogue cut off without resolution."""

    CHARACTER_CONTINUITY_LOSS = "character_continuity_loss"
    """Key characters disappeared mid-sequence."""


# ---------------------------------------------------------------------------
# Base event result — shared structure
# ---------------------------------------------------------------------------


class BaseEventResult(BaseModel, ABC):
    """Base class for all narrative event results.

    Every result contains:
    - deterministic_id: unique identifier
    - scene_ids: scenes involved
    - event_type: classification
    - dominant_characters: primary characters
    - dominant_environment: primary environment
    - continuity_strength: how strong the narrative thread is [0.0, 1.0]
    - deterministic_hash: SHA-256 based identity hash
    """

    deterministic_id: str = Field(
        ..., description="Unique event identifier"
    )
    scene_ids: List[str] = Field(
        ..., description="Scene IDs in this event"
    )
    event_type: str = Field(
        ..., description="Event type classification"
    )
    dominant_characters: List[str] = Field(
        default_factory=list,
        description="Primary characters in this event"
    )
    dominant_environment: Optional[str] = Field(
        default=None,
        description="Primary environment/location"
    )
    continuity_strength: float = Field(
        ..., ge=0.0, le=1.0,
        description="How strong the narrative continuity is [0.0, 1.0]"
    )
    deterministic_hash: str = Field(
        ..., description="SHA-256 based deterministic hash"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Schema version"
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp (deterministic)"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("scene_ids", "dominant_characters")
    @classmethod
    def _validate_sorted_ids(cls, v: List[str]) -> List[str]:
        return _sorted_strings(v)

    @abstractmethod
    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Produce deterministically-ordered dict."""
        ...

    @abstractmethod
    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        ...


# ---------------------------------------------------------------------------
# NarrativeEvent — single narrative event
# ---------------------------------------------------------------------------


class NarrativeEvent(BaseEventResult):
    """A single narrative event within a scene sequence.

    Represents a coherent narrative unit (combat, dialogue, travel, etc.)
    with deterministic classification based on structural properties.
    """

    event_type: NarrativeEventType = Field(
        ..., description="Type of narrative event"
    )
    # Structural properties for classification
    action_intensity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Action intensity score [0.0, 1.0]"
    )
    dialogue_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Ratio of dialogue to total duration [0.0, 1.0]"
    )
    character_count: int = Field(
        default=0, ge=0,
        description="Number of characters present"
    )
    # Temporal properties
    temporal_span_sec: float = Field(
        default=0.0, ge=0.0,
        description="Total temporal span in seconds"
    )
    temporal_gap_ms: float = Field(
        default=0.0, ge=0.0,
        description="Internal temporal gaps (ms)"
    )
    # Narrative properties
    involved_actions: List[str] = Field(
        default_factory=list,
        description="Actions performed in this event"
    )
    involved_dialogue_topics: List[str] = Field(
        default_factory=list,
        description="Topics discussed (from keywords)"
    )
    # Coherence data from temporal engine
    coherence_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Internal coherence score [0.0, 1.0]"
    )
    continuity_chain_ids: List[str] = Field(
        default_factory=list,
        description="IDs of continuity chains within this event"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("involved_actions", "involved_dialogue_topics", "continuity_chain_ids")
    @classmethod
    def _validate_sorted_lists(cls, v: List[str]) -> List[str]:
        return _sorted_strings(v)

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "deterministic_id": self.deterministic_id,
            "scene_ids": _sorted_strings(self.scene_ids),
            "event_type": self.event_type.value,
            "dominant_characters": _sorted_strings(self.dominant_characters),
            "dominant_environment": self.dominant_environment,
            "continuity_strength": f"{self.continuity_strength:.6f}",
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
            "action_intensity": f"{self.action_intensity:.6f}",
            "dialogue_ratio": f"{self.dialogue_ratio:.6f}",
            "character_count": self.character_count,
            "temporal_span_sec": f"{self.temporal_span_sec:.6f}",
            "temporal_gap_ms": f"{self.temporal_gap_ms:.6f}",
            "involved_actions": _sorted_strings(self.involved_actions),
            "involved_dialogue_topics": _sorted_strings(self.involved_dialogue_topics),
            "coherence_score": f"{self.coherence_score:.6f}",
            "continuity_chain_ids": _sorted_strings(self.continuity_chain_ids),
        }
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# EventBoundary — detected boundary between events
# ---------------------------------------------------------------------------


class EventBoundary(BaseModel):
    """A detected boundary between narrative events.

    Tracks why a boundary was detected and between which scenes.
    """

    boundary_id: str = Field(
        ..., description="Unique boundary identifier"
    )
    scene_before: str = Field(
        ..., description="Scene ID before boundary"
    )
    scene_after: str = Field(
        ..., description="Scene ID after boundary"
    )
    reason: BoundaryReason = Field(
        ..., description="Reason for boundary detection"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Confidence in boundary detection [0.0, 1.0]"
    )
    continuity_break_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="How severe the continuity break is [0.0, 1.0]"
    )
    involved_entities: List[str] = Field(
        default_factory=list,
        description="Entities involved in the break"
    )
    deterministic_hash: str = Field(
        ..., description="SHA-256 based deterministic hash"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Schema version"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("involved_entities")
    @classmethod
    def _validate_sorted_entities(cls, v: List[str]) -> List[str]:
        return _sorted_strings(v)

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "boundary_id": self.boundary_id,
            "scene_before": self.scene_before,
            "scene_after": self.scene_after,
            "reason": self.reason.value,
            "confidence": f"{self.confidence:.6f}",
            "continuity_break_score": f"{self.continuity_break_score:.6f}",
            "involved_entities": _sorted_strings(self.involved_entities),
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
        }
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# EventTransition — transition between event groups
# ---------------------------------------------------------------------------


class EventTransition(BaseModel):
    """A transition between two narrative event groups.

    Labels the type of transition and measures its properties.
    """

    transition_id: str = Field(
        ..., description="Unique transition identifier"
    )
    from_event_id: str = Field(
        ..., description="Source event group ID"
    )
    to_event_id: str = Field(
        ..., description="Target event group ID"
    )
    label: TransitionLabel = Field(
        ..., description="Transition type label"
    )
    coherence_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="How coherent the transition is [0.0, 1.0]"
    )
    temporal_distance_ms: float = Field(
        default=0.0, ge=0.0,
        description="Time gap between events (ms)"
    )
    character_overlap: float = Field(
        ..., ge=0.0, le=1.0,
        description="Character overlap ratio [0.0, 1.0]"
    )
    action_continuity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Action continuity score [0.0, 1.0]"
    )
    environment_continuity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Environment continuity score [0.0, 1.0]"
    )
    deterministic_hash: str = Field(
        ..., description="SHA-256 based deterministic hash"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Schema version"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "transition_id": self.transition_id,
            "from_event_id": self.from_event_id,
            "to_event_id": self.to_event_id,
            "label": self.label.value,
            "coherence_score": f"{self.coherence_score:.6f}",
            "temporal_distance_ms": f"{self.temporal_distance_ms:.6f}",
            "character_overlap": f"{self.character_overlap:.6f}",
            "action_continuity": f"{self.action_continuity:.6f}",
            "environment_continuity": f"{self.environment_continuity:.6f}",
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
        }
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# NarrativeEventGroup — group of related narrative events
# ---------------------------------------------------------------------------


class NarrativeEventGroup(BaseModel):
    """A group of related narrative events forming a narrative unit.

    Aggregates multiple NarrativeEvent objects that share:
    - Narrative thread (same characters, continuing story)
    - Temporal proximity
    - Logical story progression
    """

    group_id: str = Field(
        ..., description="Unique group identifier"
    )
    scene_ids: List[str] = Field(
        ..., description="All scene IDs in this group"
    )
    event_ids: List[str] = Field(
        ..., description="Event IDs in this group"
    )
    dominant_event_type: NarrativeEventType = Field(
        ..., description="Most common event type in group"
    )
    dominant_characters: List[str] = Field(
        ..., description="Characters that appear most"
    )
    dominant_environment: Optional[str] = Field(
        default=None,
        description="Primary environment"
    )
    # Group statistics
    event_count: int = Field(
        ..., ge=0,
        description="Number of events in group"
    )
    average_continuity_strength: float = Field(
        ..., ge=0.0, le=1.0,
        description="Average continuity strength [0.0, 1.0]"
    )
    total_temporal_span_sec: float = Field(
        ..., ge=0.0,
        description="Total temporal span (seconds)"
    )
    # Transitions to other groups
    transition_ids: List[str] = Field(
        default_factory=list,
        description="Transitions to other groups"
    )
    # Coherence metrics
    internal_coherence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Internal group coherence [0.0, 1.0]"
    )
    narrative_arc_score: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Narrative arc completion [0.0, 1.0]"
    )
    deterministic_hash: str = Field(
        ..., description="SHA-256 based deterministic hash"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Schema version"
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp (deterministic)"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("scene_ids", "event_ids", "dominant_characters", "transition_ids")
    @classmethod
    def _validate_sorted_ids(cls, v: List[str]) -> List[str]:
        return _sorted_strings(v)

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "group_id": self.group_id,
            "scene_ids": _sorted_strings(self.scene_ids),
            "event_ids": _sorted_strings(self.event_ids),
            "dominant_event_type": self.dominant_event_type.value,
            "dominant_characters": _sorted_strings(self.dominant_characters),
            "dominant_environment": self.dominant_environment,
            "event_count": self.event_count,
            "average_continuity_strength": f"{self.average_continuity_strength:.6f}",
            "total_temporal_span_sec": f"{self.total_temporal_span_sec:.6f}",
            "transition_ids": _sorted_strings(self.transition_ids),
            "internal_coherence": f"{self.internal_coherence:.6f}",
            "narrative_arc_score": f"{self.narrative_arc_score:.6f}",
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
        }
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# Hash generation functions
# ---------------------------------------------------------------------------


def _generate_event_hash(
    event_type: str,
    scene_ids: List[str],
    dominant_characters: List[str],
    continuity_strength: float,
) -> str:
    """Generate deterministic SHA-256 hash for a narrative event.

    Args:
        event_type: Type of event
        scene_ids: Scene IDs involved
        dominant_characters: Primary characters
        continuity_strength: Continuity strength score

    Returns:
        64-character hex digest
    """
    parts = [
        f"type={event_type}",
        f"scenes={','.join(sorted(scene_ids))}",
        f"chars={','.join(sorted(dominant_characters))}",
        f"strength={continuity_strength:.6f}",
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_boundary_hash(
    scene_before: str,
    scene_after: str,
    reason: str,
    confidence: float,
) -> str:
    """Generate deterministic SHA-256 hash for an event boundary.

    Args:
        scene_before: Scene before boundary
        scene_after: Scene after boundary
        reason: Boundary reason
        confidence: Detection confidence

    Returns:
        64-character hex digest
    """
    parts = [
        f"before={scene_before}",
        f"after={scene_after}",
        f"reason={reason}",
        f"conf={confidence:.6f}",
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_transition_hash(
    from_event_id: str,
    to_event_id: str,
    label: str,
    coherence_score: float,
) -> str:
    """Generate deterministic SHA-256 hash for an event transition.

    Args:
        from_event_id: Source event ID
        to_event_id: Target event ID
        label: Transition label
        coherence_score: Coherence score

    Returns:
        64-character hex digest
    """
    parts = [
        f"from={from_event_id}",
        f"to={to_event_id}",
        f"label={label}",
        f"coh={coherence_score:.6f}",
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_group_hash(
    group_id: str,
    scene_ids: List[str],
    event_ids: List[str],
    dominant_event_type: str,
) -> str:
    """Generate deterministic SHA-256 hash for an event group.

    Args:
        group_id: Group identifier
        scene_ids: All scene IDs
        event_ids: All event IDs
        dominant_event_type: Primary event type

    Returns:
        64-character hex digest
    """
    parts = [
        f"group={group_id}",
        f"scenes={','.join(sorted(scene_ids))}",
        f"events={','.join(sorted(event_ids))}",
        f"type={dominant_event_type}",
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# NarrativeEventGroupingResult — result container for grouping operations
# ---------------------------------------------------------------------------


class NarrativeEventGroupingResult(BaseModel):
    """Container for narrative event grouping results.

    Holds all events, groups, boundaries, and transitions from a
    grouping operation.
    """

    events: List[NarrativeEvent] = Field(
        default_factory=list,
        description="All narrative events detected"
    )
    groups: List[NarrativeEventGroup] = Field(
        default_factory=list,
        description="Scene groupings into narrative events"
    )
    boundaries: List[EventBoundary] = Field(
        default_factory=list,
        description="Detected event boundaries"
    )
    transitions: List[EventTransition] = Field(
        default_factory=list,
        description="Transitions between events"
    )
    schema_version: str = Field(
        default_factory=lambda: _schema_version,
        description="Schema version"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "events": [e.to_dict_deterministic() for e in sorted(
                self.events, key=lambda e: e.deterministic_id
            )],
            "groups": [g.to_dict_deterministic() for g in sorted(
                self.groups, key=lambda g: g.group_id
            )],
            "boundaries": [b.to_dict_deterministic() for b in sorted(
                self.boundaries, key=lambda b: b.boundary_id
            )],
            "transitions": [t.to_dict_deterministic() for t in sorted(
                self.transitions, key=lambda t: t.transition_id
            )],
            "schema_version": self.schema_version,
        }
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


__all__ = [
    # Version
    "_schema_version",
    "_sorted_strings",
    "_sorted_floats",
    # Enums
    "NarrativeEventType",
    "TransitionLabel",
    "BoundaryReason",
    # Base
    "BaseEventResult",
    # Schemas
    "NarrativeEvent",
    "EventBoundary",
    "EventTransition",
    "NarrativeEventGroup",
    "NarrativeEventGroupingResult",
    # Hash generators
    "_generate_event_hash",
    "_generate_boundary_hash",
    "_generate_transition_hash",
    "_generate_group_hash",
]
