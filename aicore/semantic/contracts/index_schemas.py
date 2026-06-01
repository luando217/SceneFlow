"""Retrieval index schemas — immutable deterministic index entries.

These models define the canonical shape of every indexable record in the
retrieval layer.  They contain ONLY normalised matching fields — no prose,
no inference, no hidden state.

Every schema:
- frozen=True — immutable after construction
- extra="forbid" — no surprise fields
- deterministic ordering — stable JSON serialisation
- replay-safe — same data → same serialised form
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aicore.semantic.utils.replay_utils import DeterministicClock


def _default_schema_version() -> str:
    return "Phase3.1"


def _now_timestamp() -> float:
    """Deterministic zero timestamp — never uses wall clock time."""
    return DeterministicClock.zero_timestamp()


# ---------------------------------------------------------------------------
# Internal helpers for deterministic serialisation
# ---------------------------------------------------------------------------


def _sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return a sorted copy of the list (stable across runs)."""
    if items is None:
        return []
    return sorted(items)


def _to_dict_deterministic(
    model: BaseModel,
    *,
    extra_fields: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Produce a deterministically-ordered dict from a pydantic model."""
    base = model.model_dump()
    # Remove None values for canonical form
    cleaned = {k: v for k, v in base.items() if v is not None}
    if extra_fields:
        cleaned.update(extra_fields)
    return dict(sorted(cleaned.items()))


# ---------------------------------------------------------------------------
# 1. SceneIndex — flattened, normalised index entry for a single scene
# ---------------------------------------------------------------------------


class SceneIndex(BaseModel):
    """Immutable deterministic index entry for a single scene.

    Contains ONLY normalised matching fields — no prose, no generated
    descriptions, no AI-inferred content.
    """

    # ── Identity ──────────────────────────────────────────────────────
    scene_id: str = Field(
        ..., description="Unique scene identifier"
    )
    video_id: str = Field(
        ..., description="Source video identifier"
    )
    episode_id: Optional[str] = Field(
        default=None, description="Episode identifier (e.g. episode_01)"
    )

    # ── Temporal window ───────────────────────────────────────────────
    start_time: float = Field(
        ..., ge=0.0, description="Scene start time in seconds"
    )
    end_time: float = Field(
        ..., ge=0.0, description="Scene end time in seconds"
    )
    duration: float = Field(
        default=0.0, ge=0.0, description="Scene duration in seconds"
    )

    # ── Normalised matching fields (sorted for determinism) ───────────
    characters: List[str] = Field(
        default_factory=list,
        description="Normalised character names for matching",
    )
    actions: List[str] = Field(
        default_factory=list,
        description="Normalised action names for matching",
    )
    environments: List[str] = Field(
        default_factory=list,
        description="Normalised environment locations for matching",
    )
    objects: List[str] = Field(
        default_factory=list,
        description="Normalised object names for matching",
    )
    emotions: List[str] = Field(
        default_factory=list,
        description="Normalised emotion labels for matching",
    )
    tags: List[str] = Field(
        default_factory=list,
        description="Normalised WD14-style tags for matching",
    )

    # ── Text snippets (deterministic prefix) ──────────────────────────
    dialogue_snippet: str = Field(
        default="",
        description="First 200 characters of normalised dialogue",
    )
    ocr_snippet: str = Field(
        default="",
        description="First 200 characters of normalised OCR text",
    )

    # ── Motion summary ────────────────────────────────────────────────
    motion_intensity: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Motion intensity [0,1]"
    )
    action_pace: str = Field(
        default="slow",
        description="Action pace (slow|normal|fast|intense)",
    )

    # ── Narrative routing hint ────────────────────────────────────────
    narrative_event_type: Optional[str] = Field(
        default=None,
        description="Narrative classification: combat|dialogue|magic|...",
    )

    # ── Metadata ──────────────────────────────────────────────────────
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Index schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of index entry creation",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering for JSON export."""
        return _to_dict_deterministic(
            self,
            extra_fields={
                "characters": sorted(self.characters),
                "actions": sorted(self.actions),
                "environments": sorted(self.environments),
                "objects": sorted(self.objects),
                "emotions": sorted(self.emotions),
                "tags": sorted(self.tags),
            },
        )

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string with stable key ordering."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# 2. SegmentIndex — index entry for a narrative segment
# ---------------------------------------------------------------------------


class SegmentIndex(BaseModel):
    """Immutable deterministic index entry for a narrative segment.

    Flattened from NarrativeSegment with only normalised matching fields.
    """

    segment_id: str = Field(
        ..., description="Unique segment identifier"
    )
    scene_ids: List[str] = Field(
        default_factory=list,
        description="Ordered scene IDs belonging to this segment",
    )
    dominant_characters: List[str] = Field(
        default_factory=list,
        description="Top-N normalised character names (sorted)",
    )
    dominant_environment: str = Field(
        default="unknown",
        description="Most frequent normalised environment",
    )
    continuity_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Average continuity score within segment",
    )
    transition_type: str = Field(
        default="unknown",
        description="Transition type at segment boundary",
    )
    segment_hash: str = Field(
        default="",
        description="Replay-safe deterministic hash of segment contents",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Index schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of index entry creation",
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
# 3. ContinuityIndex — index entry for a continuity chain
# ---------------------------------------------------------------------------


class ContinuityIndex(BaseModel):
    """Immutable deterministic index entry for a continuity chain.

    Represents a maximal unbroken narrative thread across multiple scenes.
    """

    chain_id: str = Field(
        ..., description="Unique continuity chain identifier"
    )
    scene_ids: List[str] = Field(
        default_factory=list,
        description="Ordered scene IDs in the chain",
    )
    transition_types: List[str] = Field(
        default_factory=list,
        description="Transition types between consecutive scenes",
    )
    scores: List[float] = Field(
        default_factory=list,
        description="Continuity scores between consecutive scenes",
    )
    average_score: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Average continuity score across the chain",
    )
    start_time: float = Field(
        default=0.0, ge=0.0,
        description="Start time of the first scene in the chain",
    )
    end_time: float = Field(
        default=0.0, ge=0.0,
        description="End time of the last scene in the chain",
    )
    dominant_characters: List[str] = Field(
        default_factory=list,
        description="Normalised character names across the chain (sorted)",
    )
    dominant_environment: str = Field(
        default="unknown",
        description="Most frequent normalised environment in chain",
    )
    chain_hash: str = Field(
        default="",
        description="Replay-safe deterministic hash of chain contents",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Index schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of index entry creation",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return _to_dict_deterministic(
            self,
            extra_fields={
                "scores": [round(s, 6) for s in self.scores],
            },
        )

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# 4. CharacterIndex — per-character aggregated index entry
# ---------------------------------------------------------------------------


class CharacterIndex(BaseModel):
    """Immutable deterministic index entry for a single character.

    Aggregates character appearance data across all scenes for retrieval.
    """

    normalized_name: str = Field(
        ..., description="Canonical normalised character name"
    )
    aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names or nicknames (sorted)",
    )
    scene_ids: List[str] = Field(
        default_factory=list,
        description="Scene IDs where this character appears (sorted)",
    )
    first_appearance: float = Field(
        default=0.0, ge=0.0,
        description="Timestamp of first appearance in seconds",
    )
    last_appearance: float = Field(
        default=0.0, ge=0.0,
        description="Timestamp of last appearance in seconds",
    )
    appearance_count: int = Field(
        default=0, ge=0,
        description="Total number of scenes this character appears in",
    )
    average_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Average detection confidence across all appearances",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Index schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of index entry creation",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return _to_dict_deterministic(
            self,
            extra_fields={
                "aliases": sorted(self.aliases),
                "scene_ids": sorted(self.scene_ids),
            },
        )

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# 5. EnvironmentIndex — per-environment aggregated index entry
# ---------------------------------------------------------------------------


class EnvironmentIndex(BaseModel):
    """Immutable deterministic index entry for a single environment."""

    normalized_name: str = Field(
        ..., description="Canonical normalised environment name"
    )
    location: str = Field(
        default="unknown",
        description="General location class (indoors, outdoors, battle_arena)",
    )
    time_of_day: str = Field(
        default="unknown",
        description="Detected time of day (day, night, sunset)",
    )
    weather: str = Field(
        default="unknown",
        description="Detected weather condition (clear, rain, storm)",
    )
    scene_ids: List[str] = Field(
        default_factory=list,
        description="Scene IDs where this environment appears (sorted)",
    )
    appearance_count: int = Field(
        default=0, ge=0,
        description="Total number of scenes with this environment",
    )
    average_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Average detection confidence across all appearances",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Index schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of index entry creation",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return _to_dict_deterministic(
            self,
            extra_fields={
                "scene_ids": sorted(self.scene_ids),
            },
        )

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# 6. ActionIndex — per-action aggregated index entry
# ---------------------------------------------------------------------------


class ActionIndex(BaseModel):
    """Immutable deterministic index entry for a single action/verb."""

    normalized_name: str = Field(
        ..., description="Canonical normalised action name"
    )
    scene_ids: List[str] = Field(
        default_factory=list,
        description="Scene IDs where this action appears (sorted)",
    )
    appearance_count: int = Field(
        default=0, ge=0,
        description="Total number of scenes with this action",
    )
    average_intensity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Average motion intensity across appearances",
    )
    total_duration_frames: int = Field(
        default=0, ge=0,
        description="Total frame duration across all appearances",
    )
    average_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Average detection confidence across all appearances",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Index schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of index entry creation",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return _to_dict_deterministic(
            self,
            extra_fields={
                "scene_ids": sorted(self.scene_ids),
            },
        )

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# Aggregate index registry — for type dispatch
# ---------------------------------------------------------------------------

# Ordered list of all index type names for deterministic iteration
INDEX_TYPE_NAMES: List[str] = [
    "scene",
    "segment",
    "continuity",
    "character",
    "environment",
    "action",
]

# Mapping from index type name to model class
INDEX_TYPE_MAP: Dict[str, type[BaseModel]] = {
    "scene": SceneIndex,
    "segment": SegmentIndex,
    "continuity": ContinuityIndex,
    "character": CharacterIndex,
    "environment": EnvironmentIndex,
    "action": ActionIndex,
}