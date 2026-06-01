"""ExtractionResult — typed payload from a single semantic extraction node.

Every node produces exactly one ExtractionResult.
Results are NOT merged directly — they feed into SemanticPatch objects
that the AggregationNode consumes.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from aicore.semantic.contracts.node_metadata import NodeMetadata


class ExtractionResult(BaseModel):
    """Deterministic typed payload from a single node execution.

    This is the OUTPUT contract for every BaseSemanticNode subclass.
    Nodes never mutate SceneSemantic directly.

    Designed for:
    - Deterministic serialization
    - Reproducible replay
    - Cache-safe storage
    - Debug inspection
    """

    # ── Identity ──────────────────────────────────────────────────────
    source_node: str = Field(
        ..., description="Node identifier that produced this result"
    )
    extraction_type: str = Field(
        ..., description="Type of extraction (ocr|asr|vision_tag|...)"
    )
    scene_id: str = Field(
        ..., description="Scene ID this extraction targets"
    )
    schema_version: str = Field(
        default="Phase2A.2",
        description="Extraction result contract version",
    )

    # ── Payload ───────────────────────────────────────────────────────
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Aggregated confidence across all extracted items",
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Typed extraction data. "
            "Structure depends on extraction_type. "
            "See node docs for per-type schemas."
        ),
    )

    # ── Items ────────────────────────────────────────────────────────
    items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered list of extracted items (lines, segments, "
        "detections)",
    )

    # ── Warnings ─────────────────────────────────────────────────────
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings during extraction",
    )

    # ── Metadata ──────────────────────────────────────────────────────
    metadata: NodeMetadata = Field(
        ..., description="Execution metadata for this result"
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def payload_summary(self) -> str:
        """Generate a human-readable payload summary."""
        n_items = len(self.items)
        ptype = self.extraction_type
        if n_items > 0:
            return f"{ptype}: {n_items} items @ {self.confidence:.2f}"
        return f"{ptype}: empty @ {self.confidence:.2f}"

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key order for JSON export."""
        return {
            "schema_version": self.schema_version,
            "source_node": self.source_node,
            "extraction_type": self.extraction_type,
            "scene_id": self.scene_id,
            "confidence": self.confidence,
            "payload": dict(sorted(self.payload.items())),
            "items": self.items,
            "warnings": sorted(self.warnings),
            "metadata": self.metadata.model_dump(),
        }