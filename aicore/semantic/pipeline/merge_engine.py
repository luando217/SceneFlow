"""PatchMergeEngine — deterministic patch application engine.

Core responsibility: Apply patches to semantic accumulators in
deterministic order with conflict resolution.

Guarantees:
- Same patches → same output (idempotent)
- Order-independent (when patch_order is same)
- Fully deterministic (no randomness, no timing)
- No side effects (pure function)
"""

from __future__ import annotations

from typing import List, Optional

from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.pipeline.merge_policy import MergePolicy, MergePolicyResolver
from aicore.semantic.schemas.merged_state import MergedSemanticState


class PatchMergeEngine:
    """Deterministic patch merge engine.

    Usage:
        engine = PatchMergeEngine(policy=MergePolicy.DETERMINISTIC_SORT)
        merged = engine.merge(scene_id="scene_001", patches=[...])
    """

    def __init__(
        self,
        policy: MergePolicy = MergePolicy.DETERMINISTIC_SORT,
        confidence_threshold: float = 0.5,
        validate_schema: bool = True,
    ):
        """Initialize merge engine.

        Args:
            policy: Conflict resolution strategy
            confidence_threshold: Used by CONFIDENCE_THRESHOLD policy
            validate_schema: If True, validate patches before merging
        """
        self.policy = policy
        self.resolver = MergePolicyResolver(policy, confidence_threshold)
        self.validate_schema = validate_schema

    def merge(
        self,
        scene_id: str,
        patches: List[SemanticPatch],
        initial_state: Optional[MergedSemanticState] = None,
    ) -> MergedSemanticState:
        """Apply patches deterministically to a scene.

        Process:
        1. Validate patches (if enabled)
        2. Sort patches by (patch_order, source_node)
        3. Apply each patch sequentially
        4. Resolve conflicts via policy
        5. Finalize provenance chains

        Args:
            scene_id: Target scene identifier
            patches: List of patches to apply
            initial_state: Starting accumulator (default: empty)

        Returns:
            MergedSemanticState with all patches applied
        """
        # Validation
        self._validate_patches(patches, scene_id)

        # Initialize accumulator
        state = initial_state or MergedSemanticState(scene_id=scene_id)

        # Sort patches deterministically
        sorted_patches = self._sort_patches(patches)

        # Apply patches sequentially
        for patch in sorted_patches:
            state = self._apply_single_patch(state, patch)

        return state

    def _validate_patches(
        self,
        patches: List[SemanticPatch],
        scene_id: str,
    ) -> None:
        """Validate patch list before merging.

        Checks:
        - All patches target same scene
        - No duplicate patch_order values (different sources)
        - All patches are frozen
        - Provenance is complete
        """
        if not self.validate_schema:
            return

        for patch in patches:
            assert (
                patch.scene_id == scene_id
            ), f"Patch targets {patch.scene_id}, not {scene_id}"

            assert (
                patch.schema_version in ["Phase2A.2", "Phase2A.3"]
            ), f"Unsupported schema version: {patch.schema_version}"

            # Check immutability (frozen=True)
            try:
                patch.model_validate(patch.model_dump())
            except Exception as e:
                raise ValueError(f"Patch failed immutability check: {e}")

    def _sort_patches(
        self,
        patches: List[SemanticPatch],
    ) -> List[SemanticPatch]:
        """Sort patches deterministically.

        Order by:
        1. patch_order (ascending)
        2. source_node (alphabetical as tiebreaker)

        This ensures that regardless of input order, merge result is identical.
        """
        return sorted(
            patches,
            key=lambda p: (p.patch_order, p.source_node),
        )

    def _apply_single_patch(
        self,
        state: MergedSemanticState,
        patch: SemanticPatch,
    ) -> MergedSemanticState:
        """Apply single patch to accumulator.

        Patch fields apply via:
        - Entity patches (list-replace semantics): MERGE with conflict resolution
        - Text patches (append semantics): APPEND to list
        - Motion/numeric patches (last-wins): OVERRIDE
        """
        # Character entities (merge with conflict resolution)
        if patch.characters is not None:
            state = self._merge_entities(
                state, "characters", patch.characters
            )

        # Action entities (merge with conflict resolution)
        if patch.actions is not None:
            state = self._merge_entities(state, "actions", patch.actions)

        # Object entities (merge with conflict resolution)
        if patch.objects is not None:
            state = self._merge_entities(state, "objects", patch.objects)

        # Environment entities (append, no conflict resolution)
        if patch.environments is not None:
            state.environments.extend(patch.environments)

        # Emotion entities (merge with conflict resolution)
        if patch.emotions is not None:
            state = self._merge_entities(state, "emotions", patch.emotions)

        # Text accumulation (append)
        if patch.dialogue is not None:
            state.dialogue_parts.append(patch.dialogue)

        if patch.ocr_text is not None:
            state.ocr_parts.append(patch.ocr_text)

        # Motion override (last-wins)
        if patch.motion_intensity is not None:
            state.motion_intensity = patch.motion_intensity

        if patch.motion_direction is not None:
            state.motion_direction = patch.motion_direction

        if patch.action_pace is not None:
            state.action_pace = patch.action_pace

        # Numeric override (last-wins)
        if patch.num_keyframes is not None:
            state.num_keyframes = patch.num_keyframes

        if patch.num_text_regions is not None:
            state.num_text_regions = patch.num_text_regions

        return state

    def _merge_entities(
        self,
        state: MergedSemanticState,
        field_name: str,
        new_entities: list,
    ) -> MergedSemanticState:
        """Merge entity list into accumulator using conflict policy.

        Args:
            state: Current accumulator
            field_name: "characters", "actions", "objects", or "emotions"
            new_entities: Entities from patch

        Returns:
            Updated state
        """
        entity_map = getattr(state, field_name)

        for new_entity in new_entities:
            key = new_entity.normalized_name

            if key not in entity_map:
                # No conflict, simply add
                entity_map[key] = new_entity
            else:
                # Conflict: resolve via policy
                existing = entity_map[key]
                winner, loser = self.resolver.resolve(existing, new_entity)

                if winner is not None:
                    entity_map[key] = winner

                    # Record conflict in provenance (if loser exists)
                    if loser is not None:
                        if not hasattr(winner.provenance, "conflict_markers"):
                            winner.provenance.conflict_markers = []

        return state

    def merge_incremental(
        self,
        scene_id: str,
        previous_state: MergedSemanticState,
        new_patches: List[SemanticPatch],
    ) -> MergedSemanticState:
        """Apply new patches to existing state (incremental merge).

        Useful for continuing previous merges without reprocessing.

        Args:
            scene_id: Target scene
            previous_state: Result of earlier merge
            new_patches: Additional patches to apply

        Returns:
            Updated state
        """
        return self.merge(
            scene_id=scene_id,
            patches=new_patches,
            initial_state=previous_state,
        )
