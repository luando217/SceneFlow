"""NodeMetadata — deterministic metadata for every extraction node execution.

Tracks provenance, timing, versioning for full inspectability.
No mutable state — each execution produces its own metadata record.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class NodeMetadata(BaseModel):
    """Immutable execution metadata for a single node invocation.

    Designed for:
    - Deterministic serialization
    - Execution traceability
    - Cache key generation
    - Debug inspection
    - Provenance tracking
    """

    node_id: str = Field(
        ..., description="Unique node identifier (e.g. ocr_node_v1)"
    )
    node_type: str = Field(
        ..., description="Node category (ocr|asr|vision|motion|...)"
    )
    schema_version: str = Field(
        default="Phase2A.2",
        description="Extraction node contract schema version",
    )

    # ── Timing ───────────────────────────────────────────────────────
    execution_start: float = Field(
        default_factory=lambda: datetime.utcnow().timestamp(),
        description="Unix timestamp when execution began",
    )
    execution_end: float = Field(
        default=0.0,
        ge=0.0,
        description="Unix timestamp when execution ended",
    )
    execution_time_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Wall-clock execution duration in milliseconds",
    )

    # ── Input provenance ─────────────────────────────────────────────
    input_scene_id: str = Field(
        ..., description="Scene ID that was passed as input"
    )
    input_scene_time_range: str = Field(
        default="",
        description="start_time→end_time of input scene for traceability",
    )

    # ── Output summary ───────────────────────────────────────────────
    extraction_type: str = Field(
        ..., description="Type of extraction performed (ocr|asr|tags|...)"
    )
    payload_summary: str = Field(
        default="",
        description="Human-readable summary of extracted payload",
    )
    payload_size: int = Field(
        default=0, ge=0, description="Number of extracted items or chars"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Aggregated confidence"
    )

    # ── Warnings ─────────────────────────────────────────────────────
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings during extraction",
    )

    # ── Versioning ───────────────────────────────────────────────────
    extractor_version: str = Field(
        default="mock-v1",
        description="Extractor implementation version (for future AI plugins)",
    )
    model_version: Optional[str] = Field(
        default=None,
        description="AI model version if applicable (null for mock)",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def finish(self) -> NodeMetadata:
        """Record execution end time and compute duration.

        Returns self (for chaining).  Does NOT mutate — creates a new
        instance with the finalised timing fields.
        """
        end = datetime.utcnow().timestamp()
        start = self.execution_start
        elapsed_ms = round((end - start) * 1000, 3)
        # Pydantic frozen — reconstruct with finalised timing
        return NodeMetadata(
            **{
                **self.model_dump(),
                "execution_end": end,
                "execution_time_ms": elapsed_ms,
            }
        )