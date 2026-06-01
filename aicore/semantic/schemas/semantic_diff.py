"""SemanticDiff — structured comparison of two scene versions.

Enables:
- Diff inspection (what changed?)
- Change magnitude calculation (how much changed?)
- Replay verification (patches should produce documented diffs)
- Anomaly detection (unexpected changes between versions)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field


class TextDiff(BaseModel):
    """Line-level diff for dialogue/OCR text."""

    text_a: str = Field(description="Original text")
    text_b: str = Field(description="New text")
    
    lines_added: List[str] = Field(
        default_factory=list,
        description="Lines present in B but not A",
    )
    lines_removed: List[str] = Field(
        default_factory=list,
        description="Lines present in A but not B",
    )
    lines_modified: List[Tuple[str, str]] = Field(
        default_factory=list,
        description="Lines that changed (original, new)",
    )
    
    total_lines_a: int = Field(default=0, ge=0)
    total_lines_b: int = Field(default=0, ge=0)
    
    line_change_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="% of lines that changed",
    )


class EntityChange(BaseModel):
    """Single entity change (added, removed, or modified)."""

    entity_type: str  # "character", "action", "object", etc.
    normalized_name: str
    change_type: str  # "added", "removed", "modified"
    
    old_entity: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Original entity (if removed or modified)",
    )
    new_entity: Optional[Dict[str, Any]] = Field(
        default=None,
        description="New entity (if added or modified)",
    )
    
    confidence_delta: Optional[float] = Field(
        default=None,
        description="Change in confidence score (if modified)",
    )
    provenance_changed: bool = Field(
        default=False,
        description="Did extraction source or version change?",
    )


class SemanticDiff(BaseModel):
    """Structured diff between two semantic states.

    Designed for inspection, logging, and anomaly detection.
    """

    scene_id: str = Field(description="Scene being compared")
    version_a: str = Field(description="First version identifier")
    version_b: str = Field(description="Second version identifier")

    # ── Entity changes ────────────────────────────────────────────
    entity_changes: List[EntityChange] = Field(
        default_factory=list,
        description="All entity adds/removes/modifies",
    )

    # Broken down by type for convenience
    characters_added: int = Field(default=0, ge=0)
    characters_removed: int = Field(default=0, ge=0)
    characters_modified: int = Field(default=0, ge=0)

    actions_added: int = Field(default=0, ge=0)
    actions_removed: int = Field(default=0, ge=0)
    actions_modified: int = Field(default=0, ge=0)

    objects_added: int = Field(default=0, ge=0)
    objects_removed: int = Field(default=0, ge=0)
    objects_modified: int = Field(default=0, ge=0)

    environments_added: int = Field(default=0, ge=0)
    environments_removed: int = Field(default=0, ge=0)
    environments_modified: int = Field(default=0, ge=0)

    emotions_added: int = Field(default=0, ge=0)
    emotions_removed: int = Field(default=0, ge=0)
    emotions_modified: int = Field(default=0, ge=0)

    # ── Text changes ──────────────────────────────────────────────
    dialogue_diff: Optional[TextDiff] = Field(
        default=None,
        description="Dialogue line-level diff",
    )
    ocr_diff: Optional[TextDiff] = Field(
        default=None,
        description="OCR line-level diff",
    )

    # ── Motion changes ────────────────────────────────────────────
    motion_intensity_a: float = Field(default=0.0, ge=0.0, le=1.0)
    motion_intensity_b: float = Field(default=0.0, ge=0.0, le=1.0)
    motion_intensity_changed: bool = Field(default=False)

    motion_direction_a: str = Field(default="static")
    motion_direction_b: str = Field(default="static")
    motion_direction_changed: bool = Field(default=False)

    action_pace_a: str = Field(default="slow")
    action_pace_b: str = Field(default="slow")
    action_pace_changed: bool = Field(default=False)

    # ── Summary statistics ────────────────────────────────────────
    total_entities_a: int = Field(
        default=0,
        ge=0,
        description="Total entities in version A",
    )
    total_entities_b: int = Field(
        default=0,
        ge=0,
        description="Total entities in version B",
    )
    total_entity_changes: int = Field(
        default=0,
        ge=0,
        description="Total add/remove/modify operations",
    )

    entity_change_percentage: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="% of entities affected",
    )

    # ── Metadata ──────────────────────────────────────────────────
    is_empty: bool = Field(
        default=True,
        description="True if no changes between versions",
    )
    change_severity: str = Field(
        default="none",
        description="Categorical: none|minor|moderate|major",
    )

    def summary(self) -> str:
        """Human-readable change summary."""
        if self.is_empty:
            return f"{self.version_a} == {self.version_b} (no changes)"

        parts = []

        if self.characters_added > 0:
            parts.append(f"+{self.characters_added} characters")
        if self.characters_removed > 0:
            parts.append(f"-{self.characters_removed} characters")
        if self.characters_modified > 0:
            parts.append(f"~{self.characters_modified} characters")

        if self.dialogue_diff and self.dialogue_diff.line_change_percentage > 0:
            parts.append(
                f"dialogue: {self.dialogue_diff.line_change_percentage:.0f}% changed"
            )

        if self.motion_intensity_changed or self.motion_direction_changed:
            parts.append("motion changed")

        changes_str = " | ".join(parts) if parts else "unknown changes"

        return (
            f"{self.version_a} → {self.version_b}: "
            f"{changes_str} ({self.entity_change_percentage:.1f}% of entities)"
        )
