"""Aggregation module — deterministic scene merging and patch orchestration.

This module orchestrates the merging of multiple SceneSemantic objects
into semantic patch groups with preserved provenance and stable ordering.

Core components:
- AggregationEngine: Orchestrates merging based on continuity/rules
- ContinuityDetector: Detects semantic continuity between scenes
- MergeRule/MergeRuleSet: Explicit merge policies
- AggregationGroup: Represents a group of merged scenes
- PatchReplay: Verification and replay of patches
- CoherenceSchemas: Deterministic coherence validation schemas
- TemporalCoherenceEngine: Deterministic temporal coherence detection
- NarrativeEventBuilder: Deterministic narrative event grouping
- EventBoundaryDetector: Deterministic event boundary detection
- EventGroupBuilder: Deterministic event group formation
- TransitionAnalyzer: Deterministic transition analysis

All operations are:
- Deterministic (same input → same output)
- Immutable (no mutation after creation)
- Replay-safe (can be serialized/deserialized indefinitely)
- Provenance-tracked (complete lineage)
"""

from .aggregation_engine import AggregationEngine, AggregationGroup
from .continuity_detector import ContinuityDetector
from .merge_rule import MergeRule, MergeRuleSet, MergeRuleType, MergeRuleResult
from .patch_replay import PatchReplay
from .continuity_chain_hasher import ContinuityChainHasher
from .temporal_coherence_engine import (
    TemporalCoherenceEngine,
    TemporalCoherenceResult,
    ContinuityChain,
    FlowBreak,
    TemporalGroup,
    TransitionType,
    FlowBreakType,
)
from .coherence_schemas import (
    ViolationType,
    Severity,
    CoherenceViolation,
    NarrativeConflict,
    ContinuityBreak,
    IntegrityMetrics,
    CoherenceReport,
    _generate_violation_hash,
    _generate_conflict_hash,
    _generate_break_hash,
    _generate_report_hash,
    CoherenceViolationValidator,
)
from .narrative_event_schemas import (
    NarrativeEventType,
    TransitionLabel,
    BoundaryReason,
    NarrativeEvent,
    EventBoundary,
    EventTransition,
    NarrativeEventGroup,
    _generate_event_hash,
    _generate_boundary_hash,
    _generate_transition_hash,
    _generate_group_hash,
)
from .narrative_event_builder import (
    NarrativeEventBuilder,
    EventBoundaryDetector,
    NarrativeTransitionAnalyzer,
    NarrativeEventGroupingEngine,
)

__all__ = [
    # Aggregation engine
    "AggregationEngine",
    "AggregationGroup",
    # Continuity
    "ContinuityDetector",
    "MergeRule",
    "MergeRuleSet",
    "MergeRuleType",
    "MergeRuleResult",
    "PatchReplay",
    "ContinuityChainHasher",
    # Temporal coherence
    "TemporalCoherenceEngine",
    "TemporalCoherenceResult",
    "ContinuityChain",
    "FlowBreak",
    "TemporalGroup",
    "TransitionType",
    "FlowBreakType",
    # Coherence schemas
    "ViolationType",
    "Severity",
    "CoherenceViolation",
    "NarrativeConflict",
    "ContinuityBreak",
    "IntegrityMetrics",
    "CoherenceReport",
    # Hash generators
    "_generate_violation_hash",
    "_generate_conflict_hash",
    "_generate_break_hash",
    "_generate_report_hash",
    # Validators
    "CoherenceViolationValidator",
    # Narrative event schemas
    "NarrativeEventType",
    "TransitionLabel",
    "BoundaryReason",
    "NarrativeEvent",
    "EventBoundary",
    "EventTransition",
    "NarrativeEventGroup",
    "_generate_event_hash",
    "_generate_boundary_hash",
    "_generate_transition_hash",
    "_generate_group_hash",
    # Narrative event builder
    "NarrativeEventBuilder",
    "EventBoundaryDetector",
    "NarrativeTransitionAnalyzer",
    "NarrativeEventGroupingEngine",
]