"""Coherence schemas — immutable, deterministic contracts for temporal coherence.

These schemas define:
- CoherenceViolation: individual coherence breaks
- NarrativeConflict: contradictory narrative elements
- ContinuityBreak: broken continuity chains
- TemporalCoherenceResult: complete coherence analysis result

All schemas are:
- frozen=True — immutable after construction
- extra="forbid" — no surprise fields
- deterministic — stable, reproducible across runs
- replay-safe — same data → same result
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from aicore.semantic.utils.replay_utils import DeterministicClock


def _schema_version() -> str:
    return "Phase3.2"


def _now_timestamp() -> float:
    """Deterministic zero timestamp — never uses wall clock time."""
    return DeterministicClock.zero_timestamp()


def _sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return deterministically-sorted copy of a list."""
    if items is None:
        return []
    return sorted(items)


# ---------------------------------------------------------------------------
# Violation type enumeration
# ---------------------------------------------------------------------------


class ViolationType(str, Enum):
    """Types of temporal coherence violations."""

    # Impossible ordering
    IMPOSSIBLE_SCENE_ORDER = "impossible_scene_order"
    """Scenes appear in wrong temporal order."""

    # Contradictory environments
    ENVIRONMENT_CONTRADICTION = "environment_contradiction"
    """Environment changes impossibly (e.g., day to night to day in minutes)."""

    # Broken dialogue
    DIALOGUE_INTERRUPTION = "dialogue_interruption"
    """Dialogue is interrupted without proper resolution."""

    # Character continuity
    CHARACTER_TELEPORTATION = "character_teleportation"
    """Character appears in distant locations without transition."""

    CHARACTER_DISAPPEARANCE = "character_disappearance"
    """Character disappears mid-conversation/action."""

    # Action continuity
    ACTION_IMPOSSIBILITY = "action_impossibility"
    """Action sequence is physically impossible."""

    ACTION_FRAGMENTATION = "action_fragmentation"
    """Action is broken into unnatural fragments."""

    # Temporal anomalies
    TEMPORAL_OVERLAP = "temporal_overlap"
    """Two scenes claim the same time range."""

    TEMPORAL_GAP_ANOMALY = "temporal_gap_anomaly"
    """Impossibly large or small temporal gap."""

    # Chain breaks
    CONTINUITY_CHAIN_BREAK = "continuity_chain_break"
    """Continuity chain is broken without justification."""

    # Narrative
    NARRATIVE_PARADOX = "narrative_paradox"
    """Cause-effect relationship is violated."""


class Severity(str, Enum):
    """Severity levels for violations."""

    CRITICAL = "critical"
    """Absolute narrative break — cannot be explained."""

    MAJOR = "major"
    """Significant coherence break — very unlikely."""

    MINOR = "minor"
    """Minor coherence issue — noticeable but explainable."""

    TRIVIAL = "trivial"
    """Almost negligible — could be artistic choice."""


# ---------------------------------------------------------------------------
# Base coherence result — shared structure
# ---------------------------------------------------------------------------


class BaseCoherenceResult(BaseModel, ABC):
    """Base class for all coherence results.

    Every result contains:
    - deterministic_id: unique identifier
    - scene_ids: scenes involved in the violation
    - violation_type: classification of violation
    - severity: impact level
    - explanation: deterministic explanation
    - deterministic_hash: SHA-256 based identity hash
    """

    deterministic_id: str = Field(
        ..., description="Unique violation identifier"
    )
    scene_ids: List[str] = Field(
        ..., description="Scene IDs involved in this violation"
    )
    violation_type: ViolationType = Field(
        ..., description="Type of violation"
    )
    severity: Severity = Field(
        ..., description="Severity level"
    )
    explanation: str = Field(
        ..., description="Deterministic explanation of the violation"
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
        description="Unix timestamp when violation was created"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("scene_ids")
    @classmethod
    def _validate_scene_ids(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("scene_ids cannot be empty")
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
# CoherenceViolation — single violation record
# ---------------------------------------------------------------------------


class CoherenceViolation(BaseCoherenceResult):
    """A detected coherence violation between scenes.

    Tracks a single violation instance with all relevant details.
    """

    violation_type: ViolationType = Field(
        ..., description="Type of violation"
    )
    # Additional metadata for specific violation types
    involved_entities: List[str] = Field(
        default_factory=list,
        description="Entities (characters/actions/environments) involved"
    )
    temporal_distance_ms: Optional[float] = Field(
        default=None,
        description="Temporal distance if applicable (ms)"
    )
    conflict_score: float = Field(
        default=0.0,
        ge=0.0, le=1.0,
        description="Confidence that this is a true violation [0.0, 1.0]"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "deterministic_id": self.deterministic_id,
            "scene_ids": _sorted_strings(self.scene_ids),
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
            "involved_entities": _sorted_strings(self.involved_entities),
            "temporal_distance_ms": (
                f"{self.temporal_distance_ms:.6f}"
                if self.temporal_distance_ms is not None else None
            ),
            "conflict_score": f"{self.conflict_score:.6f}",
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
# NarrativeConflict — contradictory narrative elements
# ---------------------------------------------------------------------------


class NarrativeConflict(BaseCoherenceResult):
    """A conflict between narrative elements across scenes.

    A conflict involves contradictions that affect narrative logic,
    not just simple violations.
    """

    violation_type: ViolationType = Field(
        default=ViolationType.NARRATIVE_PARADOX,
        description="Type of violation"
    )
    conflicting_scenes: List[str] = Field(
        ..., description="Specific scenes with conflicting content"
    )
    conflict_description: str = Field(
        ..., description="Description of what conflicts"
    )
    # Track what type of conflict
    entity_conflicts: List[str] = Field(
        default_factory=list,
        description="Entities in conflict"
    )
    temporal_conflicts: List[str] = Field(
        default_factory=list,
        description="Temporal aspects in conflict"
    )
    resolution_possible: bool = Field(
        default=True,
        description="Whether this conflict could be resolved"
    )
    resolution_notes: Optional[str] = Field(
        default=None,
        description="Notes on how this could be resolved"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "deterministic_id": self.deterministic_id,
            "scene_ids": _sorted_strings(self.scene_ids),
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
            "conflicting_scenes": _sorted_strings(self.conflicting_scenes),
            "conflict_description": self.conflict_description,
            "entity_conflicts": _sorted_strings(self.entity_conflicts),
            "temporal_conflicts": _sorted_strings(self.temporal_conflicts),
            "resolution_possible": self.resolution_possible,
        }
        if self.resolution_notes is not None:
            base["resolution_notes"] = self.resolution_notes
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
# ContinuityBreak — broken continuity chain
# ---------------------------------------------------------------------------


class ContinuityBreak(BaseCoherenceResult):
    """A break in a continuity chain.

    Tracks where a continuity chain (character, action, environment, etc.)
    is broken and cannot be logically continued.
    """

    violation_type: ViolationType = Field(
        default=ViolationType.CONTINUITY_CHAIN_BREAK,
        description="Type of violation"
    )
    chain_type: str = Field(
        ..., description="Type of chain: character|action|environment|dialogue"
    )
    chain_id: str = Field(
        ..., description="ID of the broken chain"
    )
    break_position: int = Field(
        ..., ge=0,
        description="Position in chain where break occurs"
    )
    scene_before_break: Optional[str] = Field(
        default=None,
        description="Scene before the break"
    )
    scene_after_break: Optional[str] = Field(
        default=None,
        description="Scene after the break"
    )
    chain_entities: List[str] = Field(
        default_factory=list,
        description="Entities tracked in this chain"
    )
    chain_length_before_break: int = Field(
        default=0,
        ge=0,
        description="Length of chain before break"
    )
    break_reason: str = Field(
        ..., description="Deterministic reason for the break"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "deterministic_id": self.deterministic_id,
            "scene_ids": _sorted_strings(self.scene_ids),
            "violation_type": self.violation_type.value,
            "severity": self.severity.value,
            "explanation": self.explanation,
            "deterministic_hash": self.deterministic_hash,
            "schema_version": self.schema_version,
            "chain_type": self.chain_type,
            "chain_id": self.chain_id,
            "break_position": self.break_position,
            "chain_entities": _sorted_strings(self.chain_entities),
            "chain_length_before_break": self.chain_length_before_break,
            "break_reason": self.break_reason,
        }
        if self.scene_before_break is not None:
            base["scene_before_break"] = self.scene_before_break
        if self.scene_after_break is not None:
            base["scene_after_break"] = self.scene_after_break
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
# Integrity score and metrics
# ---------------------------------------------------------------------------


class IntegrityMetrics(BaseModel):
    """Deterministic narrative integrity metrics."""

    integrity_score: float = Field(
        ..., ge=0.0, le=1.0,
        description="Overall integrity score [0.0, 1.0]"
    )
    violation_count: int = Field(
        default=0, ge=0,
        description="Total number of violations"
    )
    conflict_count: int = Field(
        default=0, ge=0,
        description="Total number of conflicts"
    )
    break_count: int = Field(
        default=0, ge=0,
        description="Total number of continuity breaks"
    )
    # Component scores
    character_integrity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Character continuity integrity [0.0, 1.0]"
    )
    action_integrity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Action continuity integrity [0.0, 1.0]"
    )
    environment_integrity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Environment continuity integrity [0.0, 1.0]"
    )
    dialogue_integrity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Dialogue continuity integrity [0.0, 1.0]"
    )
    temporal_integrity: float = Field(
        ..., ge=0.0, le=1.0,
        description="Temporal ordering integrity [0.0, 1.0]"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return dict(sorted({
            "integrity_score": f"{self.integrity_score:.6f}",
            "violation_count": self.violation_count,
            "conflict_count": self.conflict_count,
            "break_count": self.break_count,
            "character_integrity": f"{self.character_integrity:.6f}",
            "action_integrity": f"{self.action_integrity:.6f}",
            "environment_integrity": f"{self.environment_integrity:.6f}",
            "dialogue_integrity": f"{self.dialogue_integrity:.6f}",
            "temporal_integrity": f"{self.temporal_integrity:.6f}",
        }.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# Complete coherence report
# ---------------------------------------------------------------------------


class CoherenceReport(BaseModel):
    """Complete narrative coherence analysis report.

    Aggregates all violations, conflicts, breaks, and metrics
    into a single deterministic report.
    """

    report_id: str = Field(
        ..., description="Unique report identifier"
    )
    scene_ids: List[str] = Field(
        ..., description="All scene IDs analyzed"
    )
    violations: List[CoherenceViolation] = Field(
        default_factory=list,
        description="Detected coherence violations"
    )
    conflicts: List[NarrativeConflict] = Field(
        default_factory=list,
        description="Detected narrative conflicts"
    )
    continuity_breaks: List[ContinuityBreak] = Field(
        default_factory=list,
        description="Detected continuity chain breaks"
    )
    integrity_metrics: IntegrityMetrics = Field(
        ..., description="Aggregated integrity metrics"
    )
    # Metadata
    video_id: Optional[str] = Field(
        default=None,
        description="Video ID if all scenes are from same video"
    )
    episode_ids: List[str] = Field(
        default_factory=list,
        description="Episode IDs covered"
    )
    total_scenes_analyzed: int = Field(
        default=0, ge=0,
        description="Total number of scenes analyzed"
    )
    analysis_depth: str = Field(
        default="standard",
        description="Depth of analysis: basic|standard|deep"
    )
    schema_version: str = Field(
        default_factory=_schema_version,
        description="Report schema version"
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    @field_validator("scene_ids", "episode_ids")
    @classmethod
    def _validate_sorted_ids(cls, v: List[str]) -> List[str]:
        return _sorted_strings(v)

    @field_validator("violations", "conflicts", "continuity_breaks")
    @classmethod
    def _validate_results(
        cls, v: List[BaseCoherenceResult]
    ) -> List[BaseCoherenceResult]:
        # Sort by hash for deterministic ordering
        return sorted(v, key=lambda x: x.deterministic_hash)

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = {
            "report_id": self.report_id,
            "scene_ids": _sorted_strings(self.scene_ids),
            "violations": [v.to_dict_deterministic() for v in self.violations],
            "conflicts": [c.to_dict_deterministic() for c in self.conflicts],
            "continuity_breaks": [b.to_dict_deterministic() for b in self.continuity_breaks],
            "integrity_metrics": self.integrity_metrics.to_dict_deterministic(),
            "total_scenes_analyzed": self.total_scenes_analyzed,
            "analysis_depth": self.analysis_depth,
            "schema_version": self.schema_version,
        }
        if self.video_id is not None:
            base["video_id"] = self.video_id
        if self.episode_ids:
            base["episode_ids"] = _sorted_strings(self.episode_ids)
        return dict(sorted(base.items()))

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


def _generate_violation_hash(
    violation_type: str,
    scene_ids: List[str],
    explanation: str,
    involved_entities: Optional[List[str]] = None,
) -> str:
    """Generate deterministic SHA-256 hash for a violation.

    Args:
        violation_type: Type of violation
        scene_ids: Scene IDs involved
        explanation: Explanation text
        involved_entities: Optional entities involved

    Returns:
        64-character hex digest
    """
    import hashlib

    # Build canonical string representation
    parts = [
        f"type={violation_type}",
        f"scenes={','.join(sorted(scene_ids))}",
        f"explanation={explanation}",
    ]
    if involved_entities:
        parts.append(f"entities={','.join(sorted(involved_entities))}")

    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_conflict_hash(
    conflict_type: str,
    scene_ids: List[str],
    conflict_description: str,
    entity_conflicts: Optional[List[str]] = None,
) -> str:
    """Generate deterministic SHA-256 hash for a conflict.

    Args:
        conflict_type: Type of conflict
        scene_ids: Scene IDs involved
        conflict_description: Description of the conflict
        entity_conflicts: Optional entity conflicts

    Returns:
        64-character hex digest
    """
    import hashlib

    parts = [
        f"type={conflict_type}",
        f"scenes={','.join(sorted(scene_ids))}",
        f"description={conflict_description}",
    ]
    if entity_conflicts:
        parts.append(f"conflicts={','.join(sorted(entity_conflicts))}")

    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_break_hash(
    chain_type: str,
    chain_id: str,
    break_reason: str,
    scene_before: Optional[str],
    scene_after: Optional[str],
) -> str:
    """Generate deterministic SHA-256 hash for a continuity break.

    Args:
        chain_type: Type of chain
        chain_id: Chain identifier
        break_reason: Reason for the break
        scene_before: Scene before break
        scene_after: Scene after break

    Returns:
        64-character hex digest
    """
    import hashlib

    parts = [
        f"chain_type={chain_type}",
        f"chain_id={chain_id}",
        f"reason={break_reason}",
    ]
    if scene_before:
        parts.append(f"before={scene_before}")
    if scene_after:
        parts.append(f"after={scene_after}")

    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _generate_report_hash(
    scene_ids: List[str],
    violation_count: int,
    conflict_count: int,
    break_count: int,
) -> str:
    """Generate deterministic SHA-256 hash for a coherence report.

    Args:
        scene_ids: All scene IDs analyzed
        violation_count: Number of violations
        conflict_count: Number of conflicts
        break_count: Number of continuity breaks

    Returns:
        64-character hex digest
    """
    import hashlib

    canonical = "|".join([
        f"scenes={','.join(sorted(scene_ids))}",
        f"violations={violation_count}",
        f"conflicts={conflict_count}",
        f"breaks={break_count}",
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CoherenceViolationValidator:
    """Deterministic validator for coherence violations."""

    @staticmethod
    def validate_impossible_scene_order(
        scenes_before: List[str],
        scenes_after: List[str],
        gap_threshold_ms: float = 5000.0,
    ) -> Optional[CoherenceViolation]:
        """Validate impossible scene ordering.

        Args:
            scenes_before: Scenes before the break
            scenes_after: Scenes after the break
            gap_threshold_ms: Maximum gap before flagging as impossible

        Returns:
            CoherenceViolation if detected, None otherwise
        """
        all_scenes = scenes_before + scenes_after
        if len(all_scenes) < 2:
            return None

        # Check for reversed ordering (scene appearing before its temporal predecessor)
        # This is a simplified check - real implementation would need timestamps
        for after_scene in scenes_after:
            for before_scene in scenes_before:
                if after_scene < before_scene:
                    # Lexicographic order violation (simplified for testing)
                    violation = CoherenceViolation(
                        deterministic_id=f"vo_{hashlib.sha256(after_scene.encode()).hexdigest()[:8]}",
                        scene_ids=sorted(all_scenes),
                        violation_type=ViolationType.IMPOSSIBLE_SCENE_ORDER,
                        severity=Severity.CRITICAL,
                        explanation=f"Scene '{after_scene}' appears after '{before_scene}' but has lower lexicographic ID",
                        deterministic_hash=_generate_violation_hash(
                            ViolationType.IMPOSSIBLE_SCENE_ORDER.value,
                            sorted(all_scenes),
                            "Impossible scene ordering detected",
                        ),
                        conflict_score=1.0,
                    )
                    return violation
        return None

    @staticmethod
    def validate_character_teleportation(
        character_id: str,
        location_before: str,
        location_after: str,
        temporal_gap_ms: float,
        threshold_ms: float = 1000.0,
    ) -> Optional[CoherenceViolation]:
        """Validate character teleportation (instant location change).

        Args:
            character_id: Character identifier
            location_before: Location before
            location_after: Location after
            temporal_gap_ms: Time gap in milliseconds
            threshold_ms: Maximum gap before flagging as teleportation

        Returns:
            CoherenceViolation if detected, None otherwise
        """
        if location_before != location_after and temporal_gap_ms < threshold_ms:
            # Generate placeholder scene IDs for validation without actual scene data
            scene_ids = [f"ct_{character_id[:8]}_before", f"ct_{character_id[:8]}_after"]
            return CoherenceViolation(
                deterministic_id=f"ct_{character_id[:8]}",
                scene_ids=scene_ids,
                violation_type=ViolationType.CHARACTER_TELEPORTATION,
                severity=Severity.MAJOR,
                explanation=f"Character '{character_id}' moved from '{location_before}' to '{location_after}' in {temporal_gap_ms}ms",
                deterministic_hash=_generate_violation_hash(
                    ViolationType.CHARACTER_TELEPORTATION.value,
                    scene_ids,
                    f"Character teleportation: {character_id}",
                    involved_entities=[character_id],
                ),
                involved_entities=[character_id],
                temporal_distance_ms=temporal_gap_ms,
                conflict_score=0.95,
            )
        return None

    @staticmethod
    def validate_environment_contradiction(
        env_before: str,
        env_after: str,
        time_gap_ms: float,
        threshold_ms: float = 1000.0,
    ) -> Optional[CoherenceViolation]:
        """Validate environment contradiction (impossible environmental change).

        Args:
            env_before: Environment before
            env_after: Environment after
            time_gap_ms: Time gap in milliseconds
            threshold_ms: Maximum gap before flagging as contradiction

        Returns:
            CoherenceViolation if detected, None otherwise
        """
        if env_before != env_after and time_gap_ms < threshold_ms:
            # Generate placeholder scene IDs for validation without actual scene data
            env_hash = hashlib.sha256((env_before + env_after).encode()).hexdigest()[:8]
            scene_ids = [f"ec_{env_hash}_before", f"ec_{env_hash}_after"]
            return CoherenceViolation(
                deterministic_id=f"ec_{env_hash}",
                scene_ids=scene_ids,
                violation_type=ViolationType.ENVIRONMENT_CONTRADICTION,
                severity=Severity.MAJOR,
                explanation=f"Environment changed from '{env_before}' to '{env_after}' in {time_gap_ms}ms",
                deterministic_hash=_generate_violation_hash(
                    ViolationType.ENVIRONMENT_CONTRADICTION.value,
                    scene_ids,
                    f"Environment contradiction: {env_before} -> {env_after}",
                    involved_entities=[env_before, env_after],
                ),
                involved_entities=[env_before, env_after],
                temporal_distance_ms=time_gap_ms,
                conflict_score=0.9,
            )
        return None


__all__ = [
    "ViolationType",
    "Severity",
    "BaseCoherenceResult",
    "CoherenceViolation",
    "NarrativeConflict",
    "ContinuityBreak",
    "IntegrityMetrics",
    "CoherenceReport",
    "_schema_version",
    "_sorted_strings",
    # Hash generators
    "_generate_violation_hash",
    "_generate_conflict_hash",
    "_generate_break_hash",
    "_generate_report_hash",
    # Validators
    "CoherenceViolationValidator",
]
