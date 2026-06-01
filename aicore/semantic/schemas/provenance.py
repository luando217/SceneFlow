"""Provenance tracking schemas for deterministic extraction lineage.

Every semantic entity carries provenance information so that downstream
consumers can trace which extraction engine produced each field.

Phase 2A.3 additions:
- ConflictMarker for explicit conflict recording
- Updated ProvenanceInfo with conflict_markers list
- SourcePriority enum for deterministic tie-breaking
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _now_timestamp() -> float:
    return datetime.utcnow().timestamp()


class ExtractionSource(str, Enum):
    """Known extraction engines that can produce semantic data."""

    WD14 = "wd14"
    OCR = "ocr"
    ASR = "asr"
    MOTION = "motion"
    RULE = "rule"
    MANUAL = "manual"
    UNKNOWN = "unknown"


class SourcePriority(Enum):
    """Deterministic source ranking for confidence ties.

    Higher number = higher priority when confidence is equal.
    """

    WD14 = 100
    OCR = 80
    ASR = 70
    MOTION = 60
    RULE = 50
    MANUAL = 40
    UNKNOWN = 10

    @staticmethod
    def from_source(source: ExtractionSource) -> int:
        """Get priority value for a given extraction source."""
        mapping = {
            ExtractionSource.WD14: SourcePriority.WD14.value,
            ExtractionSource.OCR: SourcePriority.OCR.value,
            ExtractionSource.ASR: SourcePriority.ASR.value,
            ExtractionSource.MOTION: SourcePriority.MOTION.value,
            ExtractionSource.RULE: SourcePriority.RULE.value,
            ExtractionSource.MANUAL: SourcePriority.MANUAL.value,
            ExtractionSource.UNKNOWN: SourcePriority.UNKNOWN.value,
        }
        return mapping.get(source, SourcePriority.UNKNOWN.value)


class ConflictMarker(BaseModel):
    """Explicit conflict resolution record.

    Recorded when two patches provide conflicting values for the same
    semantic field and a deterministic resolution policy is applied.
    """

    conflict_type: str = Field(
        ...,
        description=(
            "Conflict type: entity_merge |"
            " text_collision | motion_override"
        ),
    )
    winner_raw_name: str = Field(
        ..., description="Raw name of the winning entity"
    )
    winner_source: str = Field(
        ..., description="Extraction source of the winner"
    )
    winner_confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence of the winner"
    )
    loser_raw_names: List[str] = Field(
        default_factory=list, description="Raw names of losing entities"
    )
    resolution_policy: str = Field(
        ...,
        description=(
            "Policy used: deterministic_sort | last_wins"
            " | first_wins | union_all | confidence_threshold"
        ),
    )
    timestamp: float = Field(
        default_factory=_now_timestamp,
        description="Unix seconds when conflict resolved",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Stable dict ordering for deterministic JSON."""
        return dict(sorted(self.model_dump().items()))


class ProvenanceInfo(BaseModel):
    """Tracks the origin and processing history of a semantic entity.

    Every entity MUST carry provenance so that extraction lineage is
    fully inspectable and replay-safe.
    """

    source: ExtractionSource = Field(
        default=ExtractionSource.UNKNOWN,
        description="Extraction engine that produced this entity",
    )
    source_version: str = Field(
        default="",
        description="Version identifier of the extraction engine",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score from the extraction engine [0, 1]",
    )
    extraction_timestamp: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp when extraction occurred",
    )
    normalizer_version: str = Field(
        default="Phase2.1",
        description="Version of normalizer applied",
    )
    normalized_at: Optional[float] = Field(
        default=None,
        description="Unix timestamp when normalization was applied",
    )
    parent_entity_id: Optional[str] = Field(
        default=None,
        description="ID of the parent entity this was derived from",
    )

    # Phase 2A.3: conflict tracking
    conflict_markers: List[ConflictMarker] = Field(
        default_factory=list,
        description="Conflicts encountered during merge (Phase 2A.3)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
        "json_schema_serialization_defaults": True,
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Stable dict ordering for deterministic JSON.

        Sorts keys alphabetically, omits None values, rounds floats.
        """
        raw = self.model_dump()
        # Round timestamps to 4 decimal places
        if raw.get("extraction_timestamp") is not None:
            raw["extraction_timestamp"] = round(raw["extraction_timestamp"], 4)
        if raw.get("normalized_at") is not None:
            raw["normalized_at"] = round(raw["normalized_at"], 4)
        # Round confidence to 2 decimal places
        if raw.get("confidence") is not None:
            raw["confidence"] = round(raw["confidence"], 4)
        # Omit None values for canonical form
        return dict(sorted(
            {k: v for k, v in raw.items() if v is not None}.items()
        ))