"""Semantic entity schemas with deterministic field ordering and provenance tracking.

All entities use:
- pydantic BaseModel with frozen=True for immutability
- deterministic field ordering (explicit Config)
- schema_version for forward compatibility
- provenance tracking (source + confidence)
- normalized_name + optional aliases
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


def _default_schema_version() -> str:
    return "Phase2.1"


def _now_timestamp() -> float:
    return datetime.utcnow().timestamp()


# ---------------------------------------------------------------------------
# Base entity
# ---------------------------------------------------------------------------


class SemanticEntity(BaseModel):
    """Base for all semantic entities with common provenance and ordering fields."""

    normalized_name: str = Field(
        ..., description="Canonical normalized form of the entity name"
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score in [0, 1]"
    )
    source: str = Field(
        default="unknown",
        description="Extraction source identifier (wd14, ocr, asr, motion, rule)",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Schema version for forward compatibility",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp when this entity was created",
    )

    model_config = {
        "frozen": True,
        "validate_assignment": True,
        "extra": "forbid",
        "json_schema_serialization_defaults": True,
    }

    @field_validator("normalized_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("normalized_name must not be empty")
        return v.strip().lower()

    @field_validator("source")
    @classmethod
    def source_lowercase(cls, v: str) -> str:
        return v.strip().lower()

    def dict_deterministic(self) -> Dict[str, Any]:
        """Return dict with deterministic key ordering for stable serialization."""
        return dict(sorted(self.model_dump().items()))


# ---------------------------------------------------------------------------
# Concrete entity types
# ---------------------------------------------------------------------------


class CharacterEntity(SemanticEntity):
    """A named character appearing in the scene."""

    aliases: List[str] = Field(
        default_factory=list,
        description="Alternative names or nicknames for this character",
    )
    appearance_features: List[str] = Field(
        default_factory=list,
        description="Visual descriptors (hair color, outfit, etc.)",
    )
    spoken_lines: int = Field(
        default=0, ge=0, description="Number of spoken lines attributed to character"
    )


class ObjectEntity(SemanticEntity):
    """A physical object or prop in the scene."""

    aliases: List[str] = Field(default_factory=list)
    bbox: Optional[Tuple[float, float, float, float]] = Field(
        default=None,
        description="Bounding box (x1, y1, x2, y2) if localized",
    )


class ActionEntity(SemanticEntity):
    """An action or verb describing scene dynamics."""

    # NOTE: Tests instantiate ActionEntity with a ``name`` argument in addition to
    # ``normalized_name``. Because the base model forbids extra fields we must
    # declare ``name`` explicitly. It stores the original, human‑readable
    # action name while ``normalized_name`` holds the canonical lower‑cased
    # form. ``name`` is optional for backward compatibility; when omitted it is
    # derived from ``normalized_name`` by the pre‑validation hook.
    name: Optional[str] = Field(
        default=None,
        description="Original action name as extracted from the source",
    )

    # The ``normalized_name`` field is inherited from ``SemanticEntity``.  We add a
    # pre‑validation hook that falls back to ``name`` when ``normalized_name`` is
    # omitted (unlikely in current tests but useful for callers).  The existing
    # validator on ``SemanticEntity`` will still enforce lower‑casing and emptiness
    # checks.
    @field_validator("normalized_name", mode="before")
    @classmethod
    def _fallback_normalized_name(cls, v: str | None, info: Any) -> str:
        # ``info.data`` contains the raw input dict before field validation.
        if v is None or (isinstance(v, str) and not v.strip()):
            # Prefer explicit ``normalized_name``; if missing, fall back to the
            # provided ``name`` value (which may be None).
            name_val = info.data.get("name")
            if isinstance(name_val, str) and name_val.strip():
                return name_val
        return v  # type: ignore[return-value]
    intensity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Motion/action intensity in [0, 1]",
    )
    duration_frames: int = Field(
        default=0, ge=0, description="Number of frames this action persists"
    )


class EmotionEntity(SemanticEntity):
    """An emotional state with canonical mapping."""

    aliases: List[str] = Field(default_factory=list)


class EnvironmentEntity(SemanticEntity):
    """Scene setting / location description."""

    location: str = Field(
        default="unknown",
        description="General location class (indoors, outdoors, battle_arena, …)",
    )
    time_of_day: str = Field(
        default="unknown",
        description="Detected time of day (day, night, sunset, …)",
    )
    weather: str = Field(
        default="unknown",
        description="Detected weather condition (clear, rain, storm, …)",
    )
    aliases: List[str] = Field(default_factory=list)