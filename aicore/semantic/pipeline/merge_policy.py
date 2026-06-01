"""MergePolicy — strategies for resolving semantic conflicts during patch merge.

Policies determine:
- Which entity "wins" when two patches define the same entity
- How to handle confidence score conflicts
- How extraction source priority is used
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from aicore.semantic.schemas.entities import BaseEntity


class MergePolicy(str, Enum):
    """Enumeration of available merge conflict resolution policies."""

    DETERMINISTIC_SORT = "deterministic_sort"
    """Keep highest-confidence entity; break ties by source priority."""

    LAST_PATCH_WINS = "last_patch_wins"
    """Keep entity from later patch in sequence."""

    FIRST_PATCH_WINS = "first_patch_wins"
    """Keep entity from earlier patch in sequence."""

    UNION_ALL = "union_all"
    """Keep all unique entities (no deduplication)."""

    CONFIDENCE_THRESHOLD = "confidence_threshold"
    """Only merge entities above threshold; keep highest-confidence version."""


class SourcePriority(int, Enum):
    """Deterministic priority ordering for extraction sources.

    Used to break ties when two entities have same confidence.
    Higher number = higher priority.
    """

    WD14 = 100
    """Vision-based, highest reliability."""

    OCR = 80
    """Text-based, domain-specific."""

    ASR = 70
    """Audio-based speech extraction."""

    MOTION = 60
    """Motion analysis, lower semantic content."""

    RULE = 50
    """Deterministic rules, conservative."""

    MANUAL = 40
    """Human annotation, low priority."""

    UNKNOWN = 10
    """Unknown source, last resort."""

    @classmethod
    def for_source(cls, source_name: str) -> int:
        """Get priority for a source name string.

        Args:
            source_name: e.g. "wd14", "ocr", etc.

        Returns:
            Priority value (higher = more important)
        """
        mapping = {
            "wd14": cls.WD14,
            "ocr": cls.OCR,
            "asr": cls.ASR,
            "motion": cls.MOTION,
            "rule": cls.RULE,
            "manual": cls.MANUAL,
        }
        return mapping.get(source_name.lower(), cls.UNKNOWN)


class ConflictResolution:
    """Implements individual merge policy strategies."""

    @staticmethod
    def resolve_deterministic_sort(
        existing_entity: BaseEntity,
        new_entity: BaseEntity,
    ) -> tuple[BaseEntity, BaseEntity]:
        """Deterministic sort: keep highest confidence, then highest source priority.

        Returns:
            (winner, loser) tuple
        """
        # Higher confidence wins
        if new_entity.confidence > existing_entity.confidence:
            return new_entity, existing_entity

        if existing_entity.confidence > new_entity.confidence:
            return existing_entity, new_entity

        # Tied confidence: use source priority
        existing_priority = SourcePriority.for_source(
            existing_entity.provenance.source.value
        )
        new_priority = SourcePriority.for_source(
            new_entity.provenance.source.value
        )

        if new_priority > existing_priority:
            return new_entity, existing_entity

        # Fallback: keep existing if all else tied
        return existing_entity, new_entity

    @staticmethod
    def resolve_last_patch_wins(
        existing_entity: BaseEntity,
        new_entity: BaseEntity,
    ) -> tuple[BaseEntity, BaseEntity]:
        """Last patch wins: new entity always overrides.

        Returns:
            (winner, loser) tuple
        """
        return new_entity, existing_entity

    @staticmethod
    def resolve_first_patch_wins(
        existing_entity: BaseEntity,
        new_entity: BaseEntity,
    ) -> tuple[BaseEntity, BaseEntity]:
        """First patch wins: existing entity never overridden.

        Returns:
            (winner, loser) tuple
        """
        return existing_entity, new_entity

    @staticmethod
    def resolve_union_all(
        existing_entity: BaseEntity,
        new_entity: BaseEntity,
    ) -> Optional[tuple[BaseEntity, BaseEntity]]:
        """Union all: keep both (no conflict).

        Returns:
            None (signal to keep both)
        """
        return None

    @staticmethod
    def resolve_confidence_threshold(
        existing_entity: BaseEntity,
        new_entity: BaseEntity,
        threshold: float = 0.5,
    ) -> tuple[BaseEntity, BaseEntity]:
        """Confidence threshold: filter + keep highest.

        Returns:
            (winner, loser) tuple or (None, None) if both below threshold
        """
        if existing_entity.confidence < threshold:
            if new_entity.confidence < threshold:
                # Both below threshold
                return None, None

            # Only new_entity passes threshold
            return new_entity, existing_entity

        if new_entity.confidence < threshold:
            # Only existing_entity passes threshold
            return existing_entity, new_entity

        # Both pass threshold: use confidence sort
        return ConflictResolution.resolve_deterministic_sort(
            existing_entity, new_entity
        )


class MergePolicyResolver:
    """Applies merge policy to entity conflicts."""

    def __init__(
        self,
        policy: MergePolicy = MergePolicy.DETERMINISTIC_SORT,
        confidence_threshold: float = 0.5,
    ):
        self.policy = policy
        self.confidence_threshold = confidence_threshold

    def resolve(
        self,
        existing_entity: BaseEntity,
        new_entity: BaseEntity,
    ) -> tuple[Optional[BaseEntity], Optional[BaseEntity]]:
        """Resolve conflict between two entities.

        Args:
            existing_entity: Entity already in accumulator
            new_entity: Entity from current patch

        Returns:
            (winner, loser) where winner is kept and loser is recorded in
            conflict markers. Either can be None depending on policy.
        """
        if self.policy == MergePolicy.DETERMINISTIC_SORT:
            return ConflictResolution.resolve_deterministic_sort(
                existing_entity, new_entity
            )

        elif self.policy == MergePolicy.LAST_PATCH_WINS:
            return ConflictResolution.resolve_last_patch_wins(
                existing_entity, new_entity
            )

        elif self.policy == MergePolicy.FIRST_PATCH_WINS:
            return ConflictResolution.resolve_first_patch_wins(
                existing_entity, new_entity
            )

        elif self.policy == MergePolicy.UNION_ALL:
            return ConflictResolution.resolve_union_all(
                existing_entity, new_entity
            )

        elif self.policy == MergePolicy.CONFIDENCE_THRESHOLD:
            return ConflictResolution.resolve_confidence_threshold(
                existing_entity, new_entity, self.confidence_threshold
            )

        else:
            raise ValueError(f"Unknown merge policy: {self.policy}")
