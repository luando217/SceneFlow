"""Narrative continuity preparation schema (Phase 3+ design, prepared only).

This module defines data structures for future narrative boundary detection.
DO NOT implement narrative inference here — only define the data contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _now_timestamp() -> float:
    return datetime.utcnow().timestamp()


class NarrativeContinuityMarkers(BaseModel):
    """Pre-computed (deterministic) continuity signals between scenes.

    Designed for Phase 3 narrative boundary detection.
    All fields are computed via deterministic rules, NOT AI inference.
    """

    # ── Scene pair identity ───────────────────────────────────────────
    source_scene_id: str = Field(
        ..., description="Earlier scene in the pair"
    )
    target_scene_id: str = Field(
        ..., description="Later scene in the pair"
    )

    # ── Continuity signals (0-1, higher = more continuity) ────────────
    character_overlap: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of shared characters between scenes",
    )
    action_overlap: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of shared actions between scenes",
    )
    environment_continuity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Whether environment/location is the same",
    )
    temporal_proximity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Normalized temporal distance (closer = higher)",
    )
    dialogue_continuity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Whether dialogue thread continues across scenes",
    )

    # ── Event classification (rule-based, no AI) ──────────────────────
    event_type: str = Field(
        default="unknown",
        description="Deterministic event classification: "
        "combat|dialogue|transition|magic|emotion|unknown",
    )
    event_intensity: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Aggregated intensity score for the event pair",
    )

    # ── Prepared Phase 3+ fields ──────────────────────────────────────
    is_combat_scene: bool = Field(default=False)
    combat_participants: List[str] = Field(default_factory=list)
    combat_intensity: float = Field(default=0.0, ge=0.0, le=1.0)

    is_dialogue_scene: bool = Field(default=False)
    dialogue_participants: List[str] = Field(default_factory=list)
    dialogue_topic: Optional[str] = Field(default=None)

    emotional_tone: str = Field(
        default="neutral",
        description="Canonical emotion for the scene pair",
    )
    emotional_intensity: float = Field(default=0.0, ge=0.0, le=1.0)

    # ── Story progression markers (Phase 3+) ─────────────────────────
    narrative_event_type: str = Field(
        default="transition",
        description="setup|climax|resolution|transition",
    )
    story_beat: Optional[str] = Field(
        default=None,
        description="Prepared for Phase 3 narrative grouping",
    )

    # ── Metadata ──────────────────────────────────────────────────────
    schema_version: str = Field(default="Phase2.1")
    created_at: float = Field(default_factory=_now_timestamp)

    model_config = {
        "frozen": True,
        "extra": "forbid",
        "json_schema_serialization_defaults": True,
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Stable dict ordering for deterministic JSON."""
        return dict(sorted(self.model_dump().items()))