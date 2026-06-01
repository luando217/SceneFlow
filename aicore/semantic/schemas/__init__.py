"""Canonical schema definitions for semantic extraction layer."""

from .entities import (
    SemanticEntity,
    CharacterEntity,
    ObjectEntity,
    ActionEntity,
    EmotionEntity,
    EnvironmentEntity,
)
from .scene_semantic import SceneSemantic, EmotionType
from .narrative import NarrativeContinuityMarkers
from .provenance import (
    ConflictMarker,
    ExtractionSource,
    ProvenanceInfo,
    SourcePriority,
)

__all__ = [
    "SemanticEntity",
    "CharacterEntity",
    "ObjectEntity",
    "ActionEntity",
    "EmotionEntity",
    "EnvironmentEntity",
    "SceneSemantic",
    "EmotionType",
    "NarrativeContinuityMarkers",
    "ConflictMarker",
    "ExtractionSource",
    "ProvenanceInfo",
    "SourcePriority",
]
