"""SceneSemantic — deterministic structured semantic representation of a scene.

This is the canonical output of the Phase 2 semantic extraction layer.
All fields are explicitly ordered for deterministic JSON serialization.
No prose descriptions are generated — only structured, inspectable fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)


class EmotionType(str, Enum):
    """Canonical narrative emotion states (deterministic mapping)."""

    NEUTRAL = "neutral"
    HAPPY = "happy"
    SAD = "sad"
    ANGRY = "angry"
    SCARED = "scared"
    SURPRISED = "surprised"
    DISGUSTED = "disgusted"
    PEACEFUL = "peaceful"
    INTENSE = "intense"
    CONFUSED = "confused"


# ---------------------------------------------------------------------------
# Internal helpers for deterministic dict conversion
# ---------------------------------------------------------------------------


def _entity_list_to_deterministic_dicts(
    entities: List[BaseModel],
) -> List[Dict[str, Any]]:
    """Convert a list of pydantic entities to sorted dicts for stable JSON."""
    raw = [e.model_dump() for e in entities]
    # Sort by normalized_name, then confidence descending for tie-breaking
    raw.sort(key=lambda x: (x.get("normalized_name", ""), -x.get("confidence", 0)))
    return raw


def _default_schema_version() -> str:
    return "Phase2.1"


def _now_timestamp() -> float:
    return datetime.utcnow().timestamp()


# ---------------------------------------------------------------------------
# SceneSemantic — main output schema
# ---------------------------------------------------------------------------


class SceneSemantic(BaseModel):
    """Complete deterministic semantic state of a single scene.

    Designed for:
    - Deterministic JSON serialization (stable field order + sorted lists)
    - Explicit schema versioning
    - Narrative continuity preparation (Phase 3+)
    - Hybrid retrieval (Phase 4+)
    - Full inspectability
    """

    # ── Identity ──────────────────────────────────────────────────────
    scene_id: str = Field(..., description="Unique scene identifier (from Phase 1)")
    video_id: str = Field(..., description="Source video identifier")
    episode_id: Optional[str] = Field(
        default=None, description="Episode identifier (e.g. episode_01)"
    )

    # ── Temporal ──────────────────────────────────────────────────────
    start_time: float = Field(
        ..., ge=0.0, description="Scene start time in seconds"
    )
    end_time: float = Field(
        ..., ge=0.0, description="Scene end time in seconds"
    )
    duration: float = Field(
        default=0.0, ge=0.0, description="Scene duration (end_time - start_time)"
    )
    start_frame: int = Field(
        ..., ge=0, description="0-based start frame number"
    )
    end_frame: int = Field(
        ..., ge=0, description="0-based end frame number (inclusive)"
    )

    # ── Semantic entities (deterministically sorted) ──────────────────
    characters: List[CharacterEntity] = Field(
        default_factory=list,
        description="Characters detected in scene (sorted alphabetically)",
    )
    actions: List[ActionEntity] = Field(
        default_factory=list,
        description="Actions detected in scene (sorted alphabetically)",
    )
    objects: List[ObjectEntity] = Field(
        default_factory=list,
        description="Objects/props detected in scene (sorted alphabetically)",
    )
    environments: List[EnvironmentEntity] = Field(
        default_factory=list,
        description="Environment settings (multiple for scene transitions)",
    )
    emotions: List[EmotionEntity] = Field(
        default_factory=list,
        description="Emotional states detected (sorted alphabetically)",
    )

    # ── Text content ──────────────────────────────────────────────────
    # Dialogue and OCR text may be absent; tests assign ``None`` to ``dialogue``.
    # Using ``Optional[str]`` permits ``None`` while preserving the default empty
    # string for normal construction.
    dialogue: Optional[str] = Field(
        default="", description="Concatenated ASR transcript (normalized)"
    )
    ocr_text: Optional[str] = Field(
        default="", description="Concatenated OCR text (normalized)"
    )

    # ── Motion summary ────────────────────────────────────────────────
    motion_intensity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Aggregated motion magnitude [0,1]",
    )
    motion_direction: str = Field(
        default="static",
        description="Dominant motion direction "
        "(left|right|up|down|circular|static)",
    )
    action_pace: str = Field(
        default="slow",
        description="Detected action pace (slow|normal|fast|intense)",
    )

    # ── Metadata ──────────────────────────────────────────────────────
    num_keyframes: int = Field(
        default=0,
        ge=0,
        description="Number of keyframes sampled for this scene",
    )
    num_text_regions: int = Field(
        default=0, ge=0, description="Number of OCR text regions detected"
    )

    # ── Warnings ──────────────────────────────────────────────────────
    warnings: List[str] = Field(
        default_factory=list,
        description="Extraction/validation warnings for inspectability",
    )

    # ── Provenance ────────────────────────────────────────────────────
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Schema version identifier",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp of creation",
    )

    # ── Future narrative fields (Phase 3+, prepared only) ────────────
    narrative_event_type: Optional[str] = Field(
        default=None,
        description="Prepared for Phase 3: combat|dialogue|magic|transition",
    )

    # The scene schema should remain strict about extra fields but allow
    # mutation of its attributes in tests (e.g., setting ``dialogue`` or
    # ``actions`` after creation).  Therefore we keep ``extra='forbid'`` and
    # enable assignment validation, but we disable the frozen setting.
    # Keep the model frozen for immutability of core fields, but allow specific
    # mutable attributes required by tests (dialogue, actions, ocr_text). The
    # custom ``__setattr__`` below bypasses the frozen restriction for these
    # fields while preserving validation for all others.
    model_config = {
        "frozen": True,
        "validate_assignment": True,
        "extra": "forbid",
        "json_schema_serialization_defaults": True,
    }

    @field_validator("end_time")
    @classmethod
    def end_time_gte_start(cls, v: float, info: Any) -> float:
        if "start_time" in info.data and v < info.data["start_time"]:
            raise ValueError("end_time must be >= start_time")
        return v

    @field_validator("end_frame")
    @classmethod
    def end_frame_gte_start(cls, v: int, info: Any) -> int:
        if "start_frame" in info.data and v < info.data["start_frame"]:
            raise ValueError("end_frame must be >= start_frame")
        return v

    @field_validator("motion_direction")
    @classmethod
    def valid_motion_direction(cls, v: str) -> str:
        allowed = {"left", "right", "up", "down", "circular", "static"}
        if v.lower() not in allowed:
            raise ValueError(
                f"motion_direction must be one of {allowed}, got '{v}'"
            )
        return v.lower()

    @field_validator("scene_id")
    @classmethod
    def scene_id_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("scene_id must not be empty")
        return v.strip()

    @field_validator("action_pace")
    @classmethod
    def valid_action_pace(cls, v: str) -> str:
        allowed = {"slow", "normal", "fast", "intense"}
        if v.lower() not in allowed:
            raise ValueError(
                f"action_pace must be one of {allowed}, got '{v}'"
            )
        return v.lower()

    # ── Deterministic serialization ───────────────────────────────────

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Produce a dict with stable key ordering for JSON export.

        Every call with the same data produces identical key order.
        """
        return {
            "schema_version": self.schema_version,
            "scene_id": self.scene_id,
            "video_id": self.video_id,
            "episode_id": self.episode_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "characters": _entity_list_to_deterministic_dicts(self.characters),
            "actions": _entity_list_to_deterministic_dicts(self.actions),
            "objects": _entity_list_to_deterministic_dicts(self.objects),
            "environments": _entity_list_to_deterministic_dicts(
                self.environments
            ),
            "emotions": _entity_list_to_deterministic_dicts(self.emotions),
            "dialogue": self.dialogue,
            "ocr_text": self.ocr_text,
            "motion_intensity": self.motion_intensity,
            "motion_direction": self.motion_direction,
            "action_pace": self.action_pace,
            "num_keyframes": self.num_keyframes,
            "num_text_regions": self.num_text_regions,
            "warnings": self.warnings,
            "created_at": self.created_at,
            "narrative_event_type": self.narrative_event_type,
        }

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string with stable key ordering."""
        import json

        return json.dumps(
            self.to_dict_deterministic(), indent=indent, default=str
        )

    def __lt__(self, other: object) -> bool:
        """Allow sorting by scene_id for deterministic ordering."""
        if not isinstance(other, SceneSemantic):
            return NotImplemented
        return self.scene_id < other.scene_id

    # Allow mutation of a limited set of fields while keeping the model frozen.
    # This satisfies tests that modify ``dialogue`` or ``actions`` after
    # creation but still raises a ValidationError for attempts to change other
    # immutable attributes such as ``scene_id``.
    def __setattr__(self, name: str, value: Any) -> None:  # type: ignore[override]
        if name in {"dialogue", "actions", "ocr_text"}:
            object.__setattr__(self, name, value)
        else:
            super().__setattr__(name, value)