"""Continuity chain schemas — immutable, deterministic chain contracts.

Each chain represents an ordered sequence of scenes that share semantic
continuity (characters, actions, environment, or dialogue).

All chains are:
- frozen=True — immutable after construction
- extra="forbid" — no surprise fields
- deterministic — stable, reproducible across runs
- replay-safe — same data → same chain
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from aicore.semantic.utils.replay_utils import DeterministicClock


def _schema_version() -> str:
    return "Phase3.1d"


def _now_timestamp() -> float:
    """Deterministic zero timestamp — never uses wall clock time."""
    return DeterministicClock.zero_timestamp()


def _sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return deterministically-sorted copy of a list."""
    if items is None:
        return []
    return sorted(items)


def _sorted_floats(items: Optional[List[float]]) -> List[float]:
    """Return deterministically-sorted copy of a float list."""
    if items is None:
        return []
    return sorted(items)


# ---------------------------------------------------------------------------
# Chain type enumeration
# ---------------------------------------------------------------------------


class ChainType(str, Enum):
    """Types of continuity chains."""

    CHARACTER = "character"
    """Chain of scenes connected by shared characters."""

    ACTION = "action"
    """Chain of scenes connected by shared actions."""

    ENVIRONMENT = "environment"
    """Chain of scenes connected by shared environment."""

    DIALOGUE = "dialogue"
    """Chain of scenes connected by dialogue continuation."""


# ---------------------------------------------------------------------------
# Base chain — shared structure for all chain types
# ---------------------------------------------------------------------------


class BaseContinuityChain(BaseModel, ABC):
    """Base class for all continuity chains.

    Every chain contains:
    - chain_id: unique identifier
    - ordered scene_ids: temporally ordered scene sequence
    - start_scene_id: first scene in chain
    - end_scene_id: last scene in chain
    - continuity_score: aggregation of pairwise continuity scores
    - temporal_span: total time covered by chain
    - deterministic_hash: SHA-256 based identity hash
    """

    chain_id: str = Field(
        ..., description="Unique chain identifier"
    )
    chain_type: ChainType = Field(
        ..., description="Type of continuity chain"
    )
    ordered_scene_ids: List[str] = Field(
        ..., description="Temporally ordered scene IDs in chain"
    )
    start_scene_id: str = Field(
        ..., description="First scene ID in chain"
    )
    end_scene_id: str = Field(
        ..., description="Last scene ID in chain"
    )
    continuity_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Aggregated continuity score [0.0, 1.0]"
    )
    dominant_entities: List[str] = Field(
        default_factory=list,
        description="Dominant entities (characters/actions/environments) in chain"
    )
    temporal_span: float = Field(
        ..., ge=0.0,
        description="Total time span covered by chain (seconds)"
    )
    deterministic_hash: str = Field(
        ..., description="SHA-256 based deterministic hash"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Chain schema version"
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp when chain was created"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("ordered_scene_ids")
    @classmethod
    def _validate_scene_ids(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("ordered_scene_ids cannot be empty")
        # Ensure deterministic ordering
        return sorted(v)

    @field_validator("dominant_entities")
    @classmethod
    def _validate_entities(cls, v: List[str]) -> List[str]:
        return _sorted_strings(v)

    @abstractmethod
    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Produce deterministically-ordered dict."""
        ...

    @abstractmethod
    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        ...

    def _base_to_dict(self) -> Dict[str, Any]:
        """Base deterministic dict without derived fields."""
        return {
            "chain_id": self.chain_id,
            "chain_type": self.chain_type.value,
            "ordered_scene_ids": self.ordered_scene_ids,
            "start_scene_id": self.start_scene_id,
            "end_scene_id": self.end_scene_id,
            "continuity_score": f"{self.continuity_score:.6f}",
            "dominant_entities": self.dominant_entities,
            "temporal_span": f"{self.temporal_span:.6f}",
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
        }


# ---------------------------------------------------------------------------
# 1. CharacterContinuityChain — character-driven continuity
# ---------------------------------------------------------------------------


class CharacterContinuityChain(BaseContinuityChain):
    """Chain of scenes connected by shared character presence.

    Tracks when the same characters appear in consecutive scenes,
    maintaining narrative character threads.
    """

    chain_type: ChainType = Field(
        default=ChainType.CHARACTER,
        description="Chain type: character"
    )
    characters: List[str] = Field(
        default_factory=list,
        description="All characters present in this chain (sorted)"
    )
    character_transitions: List[str] = Field(
        default_factory=list,
        description="Character transitions between scenes (sorted)"
    )
    min_appearances: int = Field(
        default=1, ge=1,
        description="Minimum appearances for character to be tracked"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = self._base_to_dict()
        base["characters"] = _sorted_strings(self.characters)
        base["character_transitions"] = _sorted_strings(self.character_transitions)
        base["min_appearances"] = self.min_appearances
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )

    @classmethod
    def create(
        cls,
        chain_id: str,
        ordered_scene_ids: List[str],
        characters: List[str],
        continuity_score: float,
        temporal_span: float,
        deterministic_hash: str,
    ) -> CharacterContinuityChain:
        """Factory method for deterministic creation."""
        return cls(
            chain_id=chain_id,
            chain_type=ChainType.CHARACTER,
            ordered_scene_ids=ordered_scene_ids,
            start_scene_id=ordered_scene_ids[0] if ordered_scene_ids else "",
            end_scene_id=ordered_scene_ids[-1] if ordered_scene_ids else "",
            continuity_score=continuity_score,
            dominant_entities=_sorted_strings(characters),
            temporal_span=temporal_span,
            deterministic_hash=deterministic_hash,
            characters=_sorted_strings(characters),
        )


# ---------------------------------------------------------------------------
# 2. ActionContinuityChain — action-driven continuity
# ---------------------------------------------------------------------------


class ActionContinuityChain(BaseContinuityChain):
    """Chain of scenes connected by shared action presence.

    Tracks when the same actions appear in consecutive scenes,
    maintaining action threads like combat sequences.
    """

    chain_type: ChainType = Field(
        default=ChainType.ACTION,
        description="Chain type: action"
    )
    actions: List[str] = Field(
        default_factory=list,
        description="All actions present in this chain (sorted)"
    )
    action_intensity_scores: List[float] = Field(
        default_factory=list,
        description="Action intensity per scene (sorted by scene order)"
    )
    action_pace: Optional[str] = Field(
        default=None,
        description="Overall action pace: slow|normal|fast|intense"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("action_intensity_scores")
    @classmethod
    def _validate_scores(cls, v: List[float]) -> List[float]:
        return _sorted_floats(v)

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = self._base_to_dict()
        base["actions"] = _sorted_strings(self.actions)
        base["action_intensity_scores"] = [f"{s:.6f}" for s in self.action_intensity_scores]
        if self.action_pace is not None:
            base["action_pace"] = self.action_pace
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )

    @classmethod
    def create(
        cls,
        chain_id: str,
        ordered_scene_ids: List[str],
        actions: List[str],
        continuity_score: float,
        temporal_span: float,
        deterministic_hash: str,
        action_intensity_scores: Optional[List[float]] = None,
        action_pace: Optional[str] = None,
    ) -> ActionContinuityChain:
        """Factory method for deterministic creation."""
        return cls(
            chain_id=chain_id,
            chain_type=ChainType.ACTION,
            ordered_scene_ids=ordered_scene_ids,
            start_scene_id=ordered_scene_ids[0] if ordered_scene_ids else "",
            end_scene_id=ordered_scene_ids[-1] if ordered_scene_ids else "",
            continuity_score=continuity_score,
            dominant_entities=_sorted_strings(actions),
            temporal_span=temporal_span,
            deterministic_hash=deterministic_hash,
            actions=_sorted_strings(actions),
            action_intensity_scores=action_intensity_scores or [],
            action_pace=action_pace,
        )


# ---------------------------------------------------------------------------
# 3. EnvironmentContinuityChain — environment-driven continuity
# ---------------------------------------------------------------------------


class EnvironmentContinuityChain(BaseContinuityChain):
    """Chain of scenes connected by shared environment/location.

    Tracks when scenes occur in the same location,
    maintaining spatial continuity.
    """

    chain_type: ChainType = Field(
        default=ChainType.ENVIRONMENT,
        description="Chain type: environment"
    )
    environments: List[str] = Field(
        default_factory=list,
        description="All environments/locations in this chain (sorted)"
    )
    location_class: Optional[str] = Field(
        default=None,
        description="Location class: indoors|outdoors|battle_arena|..."
    )
    time_of_day: Optional[str] = Field(
        default=None,
        description="Time of day: day|night|sunset|..."
    )
    weather: Optional[str] = Field(
        default=None,
        description="Weather: clear|rain|storm|..."
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = self._base_to_dict()
        base["environments"] = _sorted_strings(self.environments)
        if self.location_class is not None:
            base["location_class"] = self.location_class
        if self.time_of_day is not None:
            base["time_of_day"] = self.time_of_day
        if self.weather is not None:
            base["weather"] = self.weather
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )

    @classmethod
    def create(
        cls,
        chain_id: str,
        ordered_scene_ids: List[str],
        environments: List[str],
        continuity_score: float,
        temporal_span: float,
        deterministic_hash: str,
        location_class: Optional[str] = None,
        time_of_day: Optional[str] = None,
        weather: Optional[str] = None,
    ) -> EnvironmentContinuityChain:
        """Factory method for deterministic creation."""
        return cls(
            chain_id=chain_id,
            chain_type=ChainType.ENVIRONMENT,
            ordered_scene_ids=ordered_scene_ids,
            start_scene_id=ordered_scene_ids[0] if ordered_scene_ids else "",
            end_scene_id=ordered_scene_ids[-1] if ordered_scene_ids else "",
            continuity_score=continuity_score,
            dominant_entities=_sorted_strings(environments),
            temporal_span=temporal_span,
            deterministic_hash=deterministic_hash,
            environments=_sorted_strings(environments),
            location_class=location_class,
            time_of_day=time_of_day,
            weather=weather,
        )


# ---------------------------------------------------------------------------
# 4. DialogueContinuityChain — dialogue-driven continuity
# ---------------------------------------------------------------------------


class DialogueContinuityChain(BaseContinuityChain):
    """Chain of scenes connected by dialogue continuation.

    Tracks when dialogue flows across consecutive scenes,
    maintaining conversation threads.
    """

    chain_type: ChainType = Field(
        default=ChainType.DIALOGUE,
        description="Chain type: dialogue"
    )
    speakers: List[str] = Field(
        default_factory=list,
        description="All speakers in this chain (sorted)"
    )
    dialogue_lengths: List[int] = Field(
        default_factory=list,
        description="Dialogue length per scene (sorted by scene order)"
    )
    dialogue_context: Optional[str] = Field(
        default=None,
        description="Deterministic summary of dialogue topic/theme"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = self._base_to_dict()
        base["speakers"] = _sorted_strings(self.speakers)
        base["dialogue_lengths"] = sorted(self.dialogue_lengths)
        if self.dialogue_context is not None:
            base["dialogue_context"] = self.dialogue_context
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )

    @classmethod
    def create(
        cls,
        chain_id: str,
        ordered_scene_ids: List[str],
        speakers: List[str],
        continuity_score: float,
        temporal_span: float,
        deterministic_hash: str,
        dialogue_lengths: Optional[List[int]] = None,
        dialogue_context: Optional[str] = None,
    ) -> DialogueContinuityChain:
        """Factory method for deterministic creation."""
        return cls(
            chain_id=chain_id,
            chain_type=ChainType.DIALOGUE,
            ordered_scene_ids=ordered_scene_ids,
            start_scene_id=ordered_scene_ids[0] if ordered_scene_ids else "",
            end_scene_id=ordered_scene_ids[-1] if ordered_scene_ids else "",
            continuity_score=continuity_score,
            dominant_entities=_sorted_strings(speakers),
            temporal_span=temporal_span,
            deterministic_hash=deterministic_hash,
            speakers=_sorted_strings(speakers),
            dialogue_lengths=dialogue_lengths or [],
            dialogue_context=dialogue_context,
        )


# ---------------------------------------------------------------------------
# Chain type registry — for deterministic dispatch
# ---------------------------------------------------------------------------

CHAIN_TYPE_NAMES: List[str] = [
    "character",
    "action",
    "environment",
    "dialogue",
]

CHAIN_TYPE_MAP: Dict[str, type[BaseContinuityChain]] = {
    "character": CharacterContinuityChain,
    "action": ActionContinuityChain,
    "environment": EnvironmentContinuityChain,
    "dialogue": DialogueContinuityChain,
}


# ---------------------------------------------------------------------------
# ContinuityChainResult — container for all chain types
# ---------------------------------------------------------------------------


class ContinuityChainResult(BaseModel):
    """Container for all continuity chains from a scene sequence.

    Holds the result of building chains from a sequence of scenes.
    """

    character_chains: List[CharacterContinuityChain] = Field(
        default_factory=list,
        description="Character-driven continuity chains"
    )
    action_chains: List[ActionContinuityChain] = Field(
        default_factory=list,
        description="Action-driven continuity chains"
    )
    environment_chains: List[EnvironmentContinuityChain] = Field(
        default_factory=list,
        description="Environment-driven continuity chains"
    )
    dialogue_chains: List[DialogueContinuityChain] = Field(
        default_factory=list,
        description="Dialogue-driven continuity chains"
    )
    total_chains: int = Field(
        default=0, ge=0,
        description="Total number of chains"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Schema version"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator(
        "character_chains",
        "action_chains",
        "environment_chains",
        "dialogue_chains",
    )
    @classmethod
    def _validate_sorted_chains(cls, v: List) -> List:
        return sorted(v, key=lambda x: x.chain_id)

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return {
            "character_chains": [
                c.to_dict_deterministic() for c in self.character_chains
            ],
            "action_chains": [
                c.to_dict_deterministic() for c in self.action_chains
            ],
            "environment_chains": [
                c.to_dict_deterministic() for c in self.environment_chains
            ],
            "dialogue_chains": [
                c.to_dict_deterministic() for c in self.dialogue_chains
            ],
            "total_chains": self.total_chains,
            "schema_version": self.schema_version,
        }

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


__all__ = [
    "BaseContinuityChain",
    "CharacterContinuityChain",
    "ActionContinuityChain",
    "EnvironmentContinuityChain",
    "DialogueContinuityChain",
    "ContinuityChainResult",
    "ChainType",
    "CHAIN_TYPE_NAMES",
    "CHAIN_TYPE_MAP",
    "_schema_version",
    "_sorted_strings",
    "_sorted_floats",
]
