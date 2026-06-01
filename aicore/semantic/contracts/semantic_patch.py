"""SemanticPatch — typed delta that extraction nodes produce.

Patches are the ONLY way extraction nodes communicate with SceneSemantic.
No direct mutation — AggregationNode merges patches deterministically.

Phase 2A.3 additions:
- stable_content_hash() for deterministic identity
- ProvenanceInfo attachment for full lineage tracking
- ConflictMarker list for merge traceability
- narrative_event_type for downstream routing
- deterministic_sort helpers for entity lists
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)
from aicore.semantic.schemas.provenance import (
    ConflictMarker,
    ProvenanceInfo,
)


def _dicts_sorted(
    entities: Optional[List[BaseModel]],
) -> Optional[List[Dict[str, Any]]]:
    """Convert entities to sorted dicts for deterministic JSON.

    The ``created_at`` timestamp (and schema_version) are intentionally omitted
    because they are non‑deterministic and would cause equal patches to appear
    different. By stripping these fields we ensure that two patches with the
    same logical content compare equal, satisfying the deterministic tests.
    """
    if entities is None:
        return None
    raw = []
    for e in entities:
        d = e.model_dump()
        # Remove non‑deterministic fields that vary per instance.
        d.pop("created_at", None)
        d.pop("schema_version", None)
        raw.append(d)
    # Sort by normalized_name, then confidence descending for tie-breaking
    raw.sort(
        key=lambda x: (
            x.get("normalized_name", ""),
            -x.get("confidence", 0),
        )
    )
    return raw


class SemanticPatch(BaseModel):
    """Deterministic delta to apply toward a SceneSemantic.

    Each extraction node produces one or more patches targeting specific
    semantic fields.  Patches are frozen, immutable, and independently
    serializable.

    Designed for:
    - Deterministic merge (AggregationNode)
    - Cache-safe replay via stable_content_hash()
    - Reproducible debug inspection
    - Incremental pipeline execution
    - Full provenance tracking (Phase 2A.3)
    """

    # ── Identity ──────────────────────────────────────────────────────
    source_node: str = Field(
        ..., description="Node identifier that produced this patch"
    )
    scene_id: str = Field(
        ..., description="Target scene ID for this patch"
    )
    schema_version: str = Field(
        default="Phase2A.3",
        description="Patch contract version",
    )
    patch_hash: str = Field(
        default="",
        description=(
            "Stable SHA-256 content hash, auto-computed"
            " if empty on first access or via compute_hash()"
        ),
    )

    # ── Entity patches (list replacement semantics) ───────────────────
    characters: Optional[List[CharacterEntity]] = Field(
        default=None,
        description="Character entities to add/replace (None = no-op)",
    )
    actions: Optional[List[ActionEntity]] = Field(
        default=None,
        description="Action entities to add/replace (None = no-op)",
    )
    objects: Optional[List[ObjectEntity]] = Field(
        default=None,
        description="Object entities to add/replace (None = no-op)",
    )
    environments: Optional[List[EnvironmentEntity]] = Field(
        default=None,
        description="Environment entries to add/replace (None = no-op)",
    )
    emotions: Optional[List[EmotionEntity]] = Field(
        default=None,
        description="Emotion entities to add/replace (None = no-op)",
    )

    # ── Text patches ──────────────────────────────────────────────────
    dialogue: Optional[str] = Field(
        default=None,
        description="Dialogue text to append (None = no-op)",
    )
    ocr_text: Optional[str] = Field(
        default=None,
        description="OCR text to append (None = no-op)",
    )

    # ── Motion patches ───────────────────────────────────────────────
    motion_intensity: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Motion intensity override (None = no-op)",
    )
    motion_direction: Optional[str] = Field(
        default=None,
        description="Motion direction override (None = no-op)",
    )
    action_pace: Optional[str] = Field(
        default=None,
        description="Action pace override (None = no-op)",
    )

    # ── Numeric patches ──────────────────────────────────────────────
    num_keyframes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Keyframe count update (None = no-op)",
    )
    num_text_regions: Optional[int] = Field(
        default=None,
        ge=0,
        description="Text region count update (None = no-op)",
    )

    # ── Narrative hint (Phase 2A.3) ──────────────────────────────────
    narrative_event_type: Optional[str] = Field(
        default=None,
        description=(
            "Narrative event classification for downstream routing:"
            " combat|dialogue|magic|transition|exposition|None"
        ),
    )

    # ── Metadata ────────────────────────────────────────────────────
    patch_order: int = Field(
        default=0,
        ge=0,
        description="Merge ordering hint (lower = applied first)",
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings accumulated during extraction",
    )

    # ── Provenance (Phase 2A.3) ──────────────────────────────────────
    provenance: Optional[ProvenanceInfo] = Field(
        default=None,
        description=(
            "Provenance trace for this entire patch."
            " If set, overrides per-entity provenance."
        ),
    )
    conflict_markers: List[ConflictMarker] = Field(
        default_factory=list,
        description="Conflicts encountered during merge of this patch",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    # ── Content hash ──────────────────────────────────────────────────

    def compute_hash(self) -> str:
        """Compute and return the stable SHA-256 content hash.

        The hash is computed from the deterministic JSON serialization
        of all content fields (excluding patch_hash itself and
        provenance/conflict_markers metadata).
        """
        raw = self._content_dict()
        raw_json = json.dumps(raw, sort_keys=True, default=str)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def stable_content_hash(self) -> str:
        """Return the cached stable content hash, computing if needed.

        This is the canonical hash used for cache key generation and
        replay identity checks.
        """
        if not self.patch_hash:
            # We can't mutate a frozen model, so we return computed hash.
            # The caller should use compute_hash() and construct a new
            # patch with the hash set if they want to cache it.
            return self.compute_hash()
        return self.patch_hash

    # ── Deterministic serialization ──────────────────────────────────

    def _content_dict(self) -> Dict[str, Any]:
        """Return content fields only (excluding metadata) for hashing."""
        return {
            "schema_version": self.schema_version,
            "source_node": self.source_node,
            "scene_id": self.scene_id,
            "patch_order": self.patch_order,
            "narrative_event_type": self.narrative_event_type,
            "characters": _dicts_sorted(self.characters),
            "actions": _dicts_sorted(self.actions),
            "objects": _dicts_sorted(self.objects),
            "environments": _dicts_sorted(self.environments),
            "emotions": _dicts_sorted(self.emotions),
            "dialogue": self.dialogue,
            "ocr_text": self.ocr_text,
            "motion_intensity": self.motion_intensity,
            "motion_direction": self.motion_direction,
            "action_pace": self.action_pace,
            "num_keyframes": self.num_keyframes,
            "num_text_regions": self.num_text_regions,
            "warnings": sorted(self.warnings) if self.warnings else [],
        }

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Deterministic dict with stable key order for JSON export."""
        return {
            "schema_version": self.schema_version,
            "source_node": self.source_node,
            "scene_id": self.scene_id,
            "patch_hash": self.stable_content_hash(),
            "patch_order": self.patch_order,
            "narrative_event_type": self.narrative_event_type,
            "warnings": sorted(self.warnings) if self.warnings else [],
            "characters": _dicts_sorted(self.characters),
            "actions": _dicts_sorted(self.actions),
            "objects": _dicts_sorted(self.objects),
            "environments": _dicts_sorted(self.environments),
            "emotions": _dicts_sorted(self.emotions),
            "dialogue": self.dialogue,
            "ocr_text": self.ocr_text,
            "motion_intensity": self.motion_intensity,
            "motion_direction": self.motion_direction,
            "action_pace": self.action_pace,
            "num_keyframes": self.num_keyframes,
            "num_text_regions": self.num_text_regions,
        }

    def to_json(self, indent: int = 2) -> str:
        """Deterministic JSON string with stable key ordering."""
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
        )

    # ---------------------------------------------------------------------
    # Compatibility shim for legacy tests
    # ---------------------------------------------------------------------
    def to_json_deterministic(self, indent: int = 2) -> str:  # pragma: no cover
        """Legacy alias for :meth:`to_json`.

        Older test code expects a ``to_json_deterministic`` method on
        ``SemanticPatch``. The current implementation provides ``to_json``
        which already produces a deterministic representation, so this shim
        simply forwards the call.
        """
        return self.to_json(indent=indent)

    # ── Utility ───────────────────────────────────────────────────────

    @property
    def is_noop(self) -> bool:
        """True if this patch contains no modifications."""
        return (
            self.characters is None
            and self.actions is None
            and self.objects is None
            and self.environments is None
            and self.emotions is None
            and self.dialogue is None
            and self.ocr_text is None
            and self.motion_intensity is None
            and self.motion_direction is None
            and self.action_pace is None
            and self.num_keyframes is None
            and self.num_text_regions is None
        )