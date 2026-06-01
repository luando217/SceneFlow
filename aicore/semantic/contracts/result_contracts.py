"""Result contracts — replay-safe, deterministic retrieval result models.

These models define the canonical shape of every retrieval result.
They are immutable, frozen, and deterministically ordered so that the
same query over the same index always produces byte-identical output.

DO NOT add ranking logic, scoring weights, or search algorithms here.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aicore.semantic.utils.replay_utils import DeterministicClock


def _default_schema_version() -> str:
    return "Phase3.1"


def _now_timestamp() -> float:
    """Deterministic zero timestamp — never uses wall clock time.

    This is a transitional factory; unit tests that need unique
    deterministic timestamps should call DeterministicClock.timestamp(seed)
    instead. The zero timestamp is used for all ranked output defaults
    to guarantee replay identity stability.
    """
    return DeterministicClock.zero_timestamp()


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
# Result status — explicit, no hidden failures
# ---------------------------------------------------------------------------


class ResultStatus(str, Enum):
    """Explicit result status — no hidden failures or probabilistic states."""

    SUCCESS = "success"
    """Query completed successfully with results."""

    EMPTY = "empty"
    """Query completed but found no matching results."""

    ERROR = "error"
    """Query failed due to a deterministic error (index missing, etc.)."""

    PARTIAL = "partial"
    """Query returned partial results due to timeout or limit."""


# ---------------------------------------------------------------------------
# Score component — granular scoring breakdown
# ---------------------------------------------------------------------------


class RankingScore(BaseModel):
    """Immutable component of a ranking score.

    Each score_type represents a deterministic scoring signal.
    """

    score_type: str = Field(
        ..., description="Signal type: z_fallback|a_overlap|m_temporal|..."
    )
    score_value: float = Field(
        ..., ge=0.0, le=1.0, description="Signal value [0,1]"
    )
    weight: float = Field(
        default=1.0, ge=0.0, description="Signal weight multiplier"
    )
    detail: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional signal detail (indexed fields, etc.)",
    )

    model_config = {"frozen": True, "extra": "forbid"}

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        return _to_dict_deterministic(self)


# ---------------------------------------------------------------------------
# RankedItem — single item with breakdown
# ---------------------------------------------------------------------------


class RankedItem(BaseModel):
    """Immutable ranked retrieval result item.

    Tracks which fields matched and how each signal contributed.
    """

    item_id: str = Field(..., description="Unique item identifier")
    index_type: str = Field(
        default="scene",
        description="Index source: scene|segment|continuity|character|..."
    )
    score_components: List[RankingScore] = Field(
        default_factory=list,
        description="Granular scoring signals (sorted by score_type)",
    )
    total_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Weighted total score [0,1]"
    )
    matched_fields: List[str] = Field(
        default_factory=list,
        description="Fields that contributed to the match (sorted)",
    )
    excluded_fields: List[str] = Field(
        default_factory=list,
        description="Fields that explicitly excluded this item (sorted)",
    )
    query_id: str = Field(
        ..., description="ID of the query that produced this result"
    )
    index_entry_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Frozen snapshot of the matched index entry",
    )
    match_explanation: Optional[str] = Field(
        default=None,
        description="Human-readable explanation of why this item matched",
    )
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Result contract schema version",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp when item was ranked",
    )

    model_config = {"frozen": True, "extra": "forbid"}

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering."""
        base = _to_dict_deterministic(self)
        # Convert score_components to list of dicts, sorted by score_type
        base["score_components"] = sorted(
            [c.to_dict_deterministic() for c in self.score_components],
            key=lambda c: c["score_type"],
        )
        # Sort matched_fields and excluded_fields for deterministic output
        base["matched_fields"] = sorted(base.get("matched_fields", []))
        base["excluded_fields"] = sorted(base.get("excluded_fields", []))
        return base

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )


# ---------------------------------------------------------------------------
# QueryResult — complete query result with metadata
# ---------------------------------------------------------------------------


class QueryResult(BaseModel):
    """Immutable deterministic query result.

    Contains all ranked items and execution metadata for replay/audit.
    """

    # ── Identity ──────────────────────────────────────────────────────
    query_id: str = Field(..., description="Query identifier")
    query_type: str = Field(
        default="scene",
        description="Query type: scene|segment|character|environment|action"
    )

    # ── Results ──────────────────────────────────────────────────────
    items: List[RankedItem] = Field(
        default_factory=list,
        description="Ranked result items (sorted by total_score desc)",
    )
    status: ResultStatus = Field(
        default=ResultStatus.SUCCESS,
        description="Result status — no hidden failures",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if status is ERROR",
    )

    # ── Metadata ─────────────────────────────────────────────────────
    total_results: int = Field(
        default=0, ge=0,
        description="Total number of results before pagination/limit",
    )
    match_count: int = Field(
        default=0, ge=0,
        description="Total number of matching items found",
    )
    coverage: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of index covered by this query",
    )
    index_version: str = Field(
        default="",
        description="Version of the index used for this query",
    )
    execution_time_ms: float = Field(
        default=0.0, ge=0.0,
        description="Query execution time in milliseconds",
    )

    # ── Traceability ──────────────────────────────────────────────────
    trace_id: Optional[str] = Field(
        default=None,
        description="OpenTelemetry trace ID",
    )
    workflow_id: Optional[str] = Field(
        default=None,
        description="Workflow that generated this result",
    )
    node_id: Optional[str] = Field(
        default=None,
        description="Node that generated this result",
    )

    # ── Schema ────────────────────────────────────────────────────────
    schema_version: str = Field(
        default_factory=_default_schema_version,
        description="Result contract schema version",
    )
    created_at: float = Field(
        default_factory=_now_timestamp,
        description="Unix timestamp when result was created",
    )

    model_config = {"frozen": True, "extra": "forbid"}

    # ── Convenience accessors ─────────────────────────────────────────

    @property
    def is_empty(self) -> bool:
        """True if status is EMPTY (caller explicitly set empty status)."""
        return self.status == ResultStatus.EMPTY

    @property
    def is_success(self) -> bool:
        """True if there is at least one result item."""
        return len(self.items) > 0

    @property
    def top_item(self) -> Optional[RankedItem]:
        """Highest-scoring item, or None if no results."""
        if not self.items:
            return None
        # Sort deterministically: score desc, then item_id asc
        return sorted(
            self.items,
            key=lambda i: (-i.total_score, i.item_id),
        )[0]

    def item_ids(self) -> List[str]:
        """Return item IDs in deterministic order (score desc, id asc)."""
        if not self.items:
            return []
        return [
            i.item_id for i in sorted(
                self.items,
                key=lambda x: (-x.total_score, x.item_id),
            )
        ]

    # ── Serialisation ─────────────────────────────────────────────────

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key ordering for replay safety."""
        base = _to_dict_deterministic(self)
        # Convert items to list of dicts, sorted by (score desc, item_id asc)
        base["items"] = sorted(
            [item.to_dict_deterministic() for item in self.items],
            key=lambda d: (-d["total_score"], d["item_id"]),
        )
        return base

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string for replay-safe logging."""
        import json
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )