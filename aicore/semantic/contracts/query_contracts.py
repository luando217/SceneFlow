"""Query contracts — immutable, deterministic query schemas.

These models define the canonical shape of every retrieval query.
They contain ONLY normalised matching fields — no prose, no free-text
search, no AI-generated interpretations.

Every query contract:
- frozen=True — immutable after construction
- extra="forbid" — no surprise fields
- deterministic — stable, reproducible across runs
- replay-safe — same query → same serialised form

DO NOT add ranking weights, scoring algorithms, or retrieval logic here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def _default_schema_version() -> str:
    return "Phase3.1"


def _now_timestamp() -> float:
    return datetime.utcnow().timestamp()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return a deterministically-sorted copy of a list."""
    if items is None:
        return []
    return sorted(items)


def _to_dict_deterministic(model: BaseModel) -> Dict[str, Any]:
    """Produce a deterministically-ordered dict from a pydantic model."""
    raw = model.model_dump()
    cleaned = {k: v for k, v in raw.items() if v is not None}
    return dict(sorted(cleaned.items()))


# ---------------------------------------------------------------------------
# Query modes — explicit matching modes, no probabilistic inference
# ---------------------------------------------------------------------------


class QueryMode(str, Enum):
    """Explicit query matching modes.

    No "smart" inference — caller must specify the mode explicitly.
    """

    EXACT = "exact"
    """Normalised exact match on entity names."""

    OVERLAP = "overlap"
    """Match any item in the query set against index fields."""

    UNION = "union"
    """Match all items in the query set (OR semantics)."""

    INTERSECTION = "intersection"
    """Match only items present in all query fields (AND semantics)."""

    TEMPORAL_RANGE = "temporal_range"
    """Time-based window query (start_time, end_time)."""

    NARRATIVE_TYPE = "narrative_type"
    """Filter by narrative_event_type classification."""


# ---------------------------------------------------------------------------
# Base query — shared fields for all query types
# ---------------------------------------------------------------------------


class BaseQuery(BaseModel):
    """Base class for all query contracts.

    Every query carries:
    - a unique query_id for traceability
    - schema_version for forward compatibility
    - created_at for audit/ordering
    """

    query_id: str = Field(
        ..., description="Unique query identifier (caller-supplied or generated)"
    )
    mode: QueryMode = Field(
        default=QueryMode.OVERLAP,
        description="Query matching mode",
    )
    video_id: Optional[str] = Field(
        default=None,
        description="Scope query to a specific video",
    )
    episode_id: Optional[str] = Field(
        default=None,
        description="Scope query to a specific episode",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Query contract schema version",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp when query was created",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return _to_dict_deterministic(self)

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# 1. CharacterQuery — query by character entity names
# ---------------------------------------------------------------------------


class CharacterQuery(BaseQuery):
    """Query for scenes/segments featuring specific characters.

    All fields are normalised entity names — no prose, no free text.
    """

    characters: List[str] = Field(
        default_factory=list,
        description="Normalised character names to match (sorted internally)",
    )
    min_appearances: int = Field(
        default=1, ge=1,
        description="Minimum number of appearances for a match",
    )
    temporal_range: Optional[TemporalRange] = Field(
        default=None,
        description="Optional time window constraint",
    )
    exclude_characters: List[str] = Field(
        default_factory=list,
        description="Normalised character names to exclude (sorted)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = BaseQuery.to_dict_deterministic(self)
        base["characters"] = _sorted_strings(self.characters)
        base["exclude_characters"] = _sorted_strings(self.exclude_characters)
        if self.temporal_range is not None:
            base["temporal_range"] = self.temporal_range.model_dump()
        return base


# Re-define TemporalRange after BaseQuery but before use in CharacterQuery.
# (Forward reference resolved by declaring the field Optional above.)


class TemporalRange(BaseModel):
    """Immutable time window for temporal queries."""

    start_time: float = Field(
        ..., ge=0.0, description="Start time in seconds"
    )
    end_time: float = Field(
        ..., ge=0.0, description="End time in seconds"
    )

    model_config = {"frozen": True, "extra": "forbid"}

    @field_validator("end_time")
    @classmethod
    def end_gte_start(cls, v: float, info: Any) -> float:
        if "start_time" in info.data and v < info.data["start_time"]:
            raise ValueError("end_time must be >= start_time")
        return v

    def to_dict_deterministic(self) -> Dict[str, Any]:
        return dict(sorted(self.model_dump().items()))


# ---------------------------------------------------------------------------
# 2. EnvironmentQuery — query by environment/location
# ---------------------------------------------------------------------------


class EnvironmentQuery(BaseQuery):
    """Query for scenes/segments by environment or location.

    All fields are normalised — no prose descriptions.
    """

    environments: List[str] = Field(
        default_factory=list,
        description="Normalised environment/location names (sorted)",
    )
    location_class: Optional[str] = Field(
        default=None,
        description="Filter by location class: indoors|outdoors|battle_arena|...",
    )
    time_of_day: Optional[str] = Field(
        default=None,
        description="Filter by time of day: day|night|sunset|...",
    )
    weather: Optional[str] = Field(
        default=None,
        description="Filter by weather: clear|rain|storm|...",
    )
    exclude_environments: List[str] = Field(
        default_factory=list,
        description="Normalised environments to exclude (sorted)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = BaseQuery.to_dict_deterministic(self)
        base["environments"] = _sorted_strings(self.environments)
        base["exclude_environments"] = _sorted_strings(self.exclude_environments)
        return base


# ---------------------------------------------------------------------------
# 3. ActionQuery — query by action/verb entities
# ---------------------------------------------------------------------------


class ActionQuery(BaseQuery):
    """Query for scenes/segments by action or verb entities.

    All fields are normalised action names — no prose, no embeddings.
    """

    actions: List[str] = Field(
        default_factory=list,
        description="Normalised action names to match (sorted)",
    )
    min_intensity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum action/motion intensity for a match",
    )
    action_pace: Optional[str] = Field(
        default=None,
        description="Filter by pace: slow|normal|fast|intense",
    )
    exclude_actions: List[str] = Field(
        default_factory=list,
        description="Normalised actions to exclude (sorted)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = BaseQuery.to_dict_deterministic(self)
        base["actions"] = _sorted_strings(self.actions)
        base["exclude_actions"] = _sorted_strings(self.exclude_actions)
        return base


# ---------------------------------------------------------------------------
# 4. TemporalQuery — query by time window or ordering
# ---------------------------------------------------------------------------


class TemporalQuery(BaseQuery):
    """Query for scenes/segments by temporal constraints.

    All fields are exact timestamps — no inference.
    """

    temporal_range: TemporalRange = Field(
        ..., description="Exact time window for query"
    )
    include_adjacent: bool = Field(
        default=False,
        description="Include scenes immediately before/after range",
    )
    gap_tolerance_ms: float = Field(
        default=500.0, ge=0.0,
        description="Maximum gap (ms) to include adjacent scenes",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = BaseQuery.to_dict_deterministic(self)
        base["temporal_range"] = self.temporal_range.to_dict_deterministic()
        return base


# ---------------------------------------------------------------------------
# 5. NarrativeSegmentQuery — query for narrative segments by content
# ---------------------------------------------------------------------------


class NarrativeSegmentQuery(BaseQuery):
    """Query for narrative segments matching semantic content.

    Flattened from NarrativeSegment — normalised fields only.
    """

    characters: List[str] = Field(
        default_factory=list,
        description="Normalised character names that must be in segment (sorted)",
    )
    environments: List[str] = Field(
        default_factory=list,
        description="Normalised environments that must be in segment (sorted)",
    )
    narrative_event_type: Optional[str] = Field(
        default=None,
        description="Filter by narrative type: combat|dialogue|magic|transition|...",
    )
    min_continuity_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum continuity score threshold",
    )
    transition_types: List[str] = Field(
        default_factory=list,
        description="Allowed transition types (sorted)",
    )
    exclude_segments: List[str] = Field(
        default_factory=list,
        description="Segment IDs to exclude (sorted)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = BaseQuery.to_dict_deterministic(self)
        base["characters"] = _sorted_strings(self.characters)
        base["environments"] = _sorted_strings(self.environments)
        base["transition_types"] = _sorted_strings(self.transition_types)
        base["exclude_segments"] = _sorted_strings(self.exclude_segments)
        return base


# ---------------------------------------------------------------------------
# 6. CombinedQuery — multi-field query for complex retrieval
# ---------------------------------------------------------------------------


class CombinedQuery(BaseQuery):
    """Multi-field query combining character, action, environment constraints.

    All conditions are ANDed together — no probabilistic scoring.
    """

    characters: List[str] = Field(
        default_factory=list,
        description="Normalised character names (sorted)",
    )
    actions: List[str] = Field(
        default_factory=list,
        description="Normalised action names (sorted)",
    )
    environments: List[str] = Field(
        default_factory=list,
        description="Normalised environment names (sorted)",
    )
    narrative_event_type: Optional[str] = Field(
        default=None,
        description="Narrative classification filter",
    )
    motion_intensity_min: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Minimum motion intensity for a match",
    )
    temporal_range: Optional[TemporalRange] = Field(
        default=None,
        description="Optional time window constraint",
    )
    exclude_scene_ids: List[str] = Field(
        default_factory=list,
        description="Scene IDs to explicitly exclude (sorted)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = BaseQuery.to_dict_deterministic(self)
        base["characters"] = _sorted_strings(self.characters)
        base["actions"] = _sorted_strings(self.actions)
        base["environments"] = _sorted_strings(self.environments)
        base["exclude_scene_ids"] = _sorted_strings(self.exclude_scene_ids)
        if self.temporal_range is not None:
            base["temporal_range"] = self.temporal_range.to_dict_deterministic()
        return base


# ---------------------------------------------------------------------------
# Query type registry — for deterministic dispatch
# ---------------------------------------------------------------------------

QUERY_TYPE_NAMES: List[str] = [
    "character",
    "environment",
    "action",
    "temporal",
    "narrative_segment",
    "combined",
]

QUERY_TYPE_MAP: Dict[str, type[BaseQuery]] = {
    "character": CharacterQuery,
    "environment": EnvironmentQuery,
    "action": ActionQuery,
    "temporal": TemporalQuery,
    "narrative_segment": NarrativeSegmentQuery,
    "combined": CombinedQuery,
}