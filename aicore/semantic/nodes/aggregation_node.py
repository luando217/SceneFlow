"""AggregationNode — deterministic semantic merge node.

Receives multiple SemanticPatch instances from upstream extraction nodes.
Merges them deterministically into a single SceneSemantic via SceneBuilder.

This is the ONLY component that constructs SceneSemantic from patches.
No direct mutation — pure function merge semantics.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aicore.semantic.builder.scene_builder import SceneBuilder
from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode
from aicore.semantic.schemas.scene_semantic import SceneSemantic
from aicore.semantic.service.normalizer_service import NormalizerService
from aicore.semantic.service.validator import SemanticValidator


class AggregationNode(BaseSemanticNode):
    """Deterministic aggregation node.

    Takes a list of SemanticPatch objects, sorts by patch_order,
    and merges them into a SceneSemantic using SceneBuilder.

    This node has NO _extract logic — it aggregates instead.
    """

    node_id: str = "aggregation_node_v1"
    node_type: str = "aggregation"
    extraction_type: str = "semantic_merge"

    def __init__(
        self,
        normalizer: Optional[NormalizerService] = None,
        validator: Optional[SemanticValidator] = None,
        extractor_version: str = "mock-v1",
    ) -> None:
        super().__init__(extractor_version=extractor_version)
        self._normalizer = normalizer
        self._validator = validator

    # ── Public API ────────────────────────────────────────────────────

    def aggregate(
        self,
        scene_input: Dict[str, Any],
        patches: List[SemanticPatch],
    ) -> SceneSemantic:
        """Merge patches into a single SceneSemantic.

        Steps:
        1. Sort patches by patch_order (deterministic)
        2. Extract raw entity names and fields from patches
        3. Build SceneSemantic via SceneBuilder.build()
        4. Optionally normalize and validate
        """
        # Sort deterministically by patch_order, then source_node
        sorted_patches = sorted(
            patches,
            key=lambda p: (p.patch_order, p.source_node),
        )

        # Accumulate raw entity names for SceneBuilder
        raw_characters: List[str] = []
        raw_actions: List[str] = []
        raw_objects: List[str] = []
        raw_environments: List[str] = []
        raw_emotions: List[str] = []

        # Text fields (append)
        dialogue_parts: List[str] = []
        ocr_parts: List[str] = []

        # Motion fields (last non-None wins)
        motion_intensity: Optional[float] = None
        motion_direction: Optional[str] = None
        action_pace: Optional[str] = None
        num_keyframes: Optional[int] = None
        num_text_regions: Optional[int] = None

        all_warnings: List[str] = []

        for patch in sorted_patches:
            # Entity names from patches
            if patch.characters:
                for c in patch.characters:
                    if c.normalized_name:
                        raw_characters.append(c.normalized_name)
            if patch.actions:
                for a in patch.actions:
                    if a.normalized_name:
                        raw_actions.append(a.normalized_name)
            if patch.objects:
                for o in patch.objects:
                    if o.normalized_name:
                        raw_objects.append(o.normalized_name)
            if patch.environments:
                for e in patch.environments:
                    if e.normalized_name:
                        raw_environments.append(e.normalized_name)
            if patch.emotions:
                for e in patch.emotions:
                    if e.normalized_name:
                        raw_emotions.append(e.normalized_name)

            # Text
            if patch.dialogue:
                dialogue_parts.append(patch.dialogue)
            if patch.ocr_text:
                ocr_parts.append(patch.ocr_text)

            # Motion: last wins
            if patch.motion_intensity is not None:
                motion_intensity = patch.motion_intensity
            if patch.motion_direction is not None:
                motion_direction = patch.motion_direction
            if patch.action_pace is not None:
                action_pace = patch.action_pace
            if patch.num_keyframes is not None:
                num_keyframes = patch.num_keyframes
            if patch.num_text_regions is not None:
                num_text_regions = patch.num_text_regions

            all_warnings.extend(patch.warnings)

        # Merge dialogue / OCR
        merged_dialogue = "\n".join(
            d for d in dialogue_parts if d
        )
        merged_ocr = "\n".join(o for o in ocr_parts if o)

        # Build via SceneBuilder (with warnings)
        builder = SceneBuilder()
        scene_semantic = builder.build(
            scene_id=scene_input.get("scene_id", "unknown"),
            video_id=scene_input.get("video_id", "unknown"),
            start_time=float(
                scene_input.get("start_time", 0.0)
            ),
            end_time=float(scene_input.get("end_time", 0.0)),
            start_frame=int(
                scene_input.get("start_frame", 0)
            ),
            end_frame=int(
                scene_input.get("end_frame", 0)
            ),
            raw_characters=raw_characters or None,
            raw_actions=raw_actions or None,
            raw_objects=raw_objects or None,
            raw_environments=raw_environments or None,
            raw_emotions=raw_emotions or None,
            dialogue=merged_dialogue,
            ocr_text=merged_ocr,
            motion_intensity=motion_intensity or 0.0,
            motion_direction=motion_direction or "static",
            action_pace=action_pace or "slow",
            episode_id=scene_input.get("episode_id"),
            num_keyframes=num_keyframes or 0,
            num_text_regions=num_text_regions or 0,
            warnings=all_warnings or None,
        )

        # Optionally normalize
        if self._normalizer:
            scene_semantic = (
                self._normalizer.normalize(scene_semantic)
            )

        # Optionally validate (warnings come from SceneBuilder already)
        if self._validator:
            errors = self._validator.validate(scene_semantic)
            if errors:
                # SceneSemantic is frozen — rebuild with validation warnings
                validation_warnings = list(
                    scene_semantic.warnings
                )
                validation_warnings.extend(
                    f"validation: {e}" for e in errors
                )
                scene_semantic = SceneSemantic(
                    **{
                        **scene_semantic.model_dump(),
                        "warnings": validation_warnings,
                    }
                )

        return scene_semantic

    # ── BaseSemanticNode stubs ────────────────────────────────────────

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Any:
        """Not used — aggregation uses aggregate() directly."""
        raise NotImplementedError(
            "AggregationNode does not use _extract. "
            "Call aggregate(scene_input, patches) instead."
        )

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        """Not used — aggregation produces SceneSemantic, not patches."""
        raise NotImplementedError(
            "AggregationNode does not produce patches. "
            "It produces SceneSemantic directly."
        )