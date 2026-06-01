"""MergedSemanticState — intermediate accumulated state from patch merge.

NOT a final output — this is the working accumulator that PatchMergeEngine
produces before SceneBuilder constructs the final SceneSemantic.

This class is never exposed to downstream consumers; it's internal to the
merge pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)


class MergedSemanticState(BaseModel):
    """Accumulated semantic state from merged patches.

    This is NOT SceneSemantic — it's the intermediate working state.
    SceneBuilder converts this into the final immutable SceneSemantic.

    Properties:
    - Accumulates entity lists during merge
    - Tracks text parts for later concatenation
    - Stores motion overrides
    - NOT frozen (only used internally during merge)
    - Deterministic ordering enforced before output
    """

    scene_id: str = Field(
        ..., description="Target scene ID"
    )

    # ── Entity accumulation (ordered lists for determinism) ──────────
    characters: Dict[str, CharacterEntity] = Field(
        default_factory=dict,
        description="Characters by normalized_name (dict for O(1) lookup)",
    )
    actions: Dict[str, ActionEntity] = Field(
        default_factory=dict,
        description="Actions by normalized_name",
    )
    objects: Dict[str, ObjectEntity] = Field(
        default_factory=dict,
        description="Objects by normalized_name",
    )
    environments: List[EnvironmentEntity] = Field(
        default_factory=list,
        description="Environments (append semantics, ordered list)",
    )
    emotions: Dict[str, EmotionEntity] = Field(
        default_factory=dict,
        description="Emotions by normalized_name",
    )

    # ── Text accumulation (append semantics) ───────────────────────
    dialogue_parts: List[str] = Field(
        default_factory=list,
        description="Dialogue segments (joined later)",
    )
    ocr_parts: List[str] = Field(
        default_factory=list,
        description="OCR text segments (joined later)",
    )

    # ── Motion fields (last-wins semantics) ────────────────────────
    motion_intensity: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Final motion intensity [0, 1]",
    )
    motion_direction: Optional[str] = Field(
        default=None,
        description="Final motion direction",
    )
    action_pace: Optional[str] = Field(
        default=None,
        description="Final action pace",
    )

    # ── Numeric fields (last-wins semantics) ───────────────────────
    num_keyframes: Optional[int] = Field(
        default=None,
        ge=0,
        description="Final keyframe count",
    )
    num_text_regions: Optional[int] = Field(
        default=None,
        ge=0,
        description="Final text region count",
    )

    def finalize_to_lists(self) -> Dict[str, Any]:
        """Convert dict-based accumulators to sorted lists.

        Called before passing to SceneBuilder.
        Ensures deterministic output.
        """
        return {
            "characters": sorted(
                self.characters.values(),
                key=lambda e: e.normalized_name,
            ),
            "actions": sorted(
                self.actions.values(),
                key=lambda e: e.normalized_name,
            ),
            "objects": sorted(
                self.objects.values(),
                key=lambda e: e.normalized_name,
            ),
            "environments": self.environments,  # preserve order
            "emotions": sorted(
                self.emotions.values(),
                key=lambda e: e.normalized_name,
            ),
            "dialogue": " ".join(self.dialogue_parts),
            "ocr_text": " ".join(self.ocr_parts),
            "motion_intensity": self.motion_intensity or 0.0,
            "motion_direction": self.motion_direction or "static",
            "action_pace": self.action_pace or "slow",
            "num_keyframes": self.num_keyframes or 0,
            "num_text_regions": self.num_text_regions or 0,
        }
