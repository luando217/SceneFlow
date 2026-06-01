"""PatchValidator — validates semantic patches before merge.

Checks:
- Schema compliance
- Provenance completeness
- Confidence bounds
- Entity name validity
- No conflicting patch_order values
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import ValidationError

from aicore.semantic.contracts.semantic_patch import SemanticPatch


class PatchValidationError(Exception):
    """Raised when patch validation fails."""

    def __init__(self, patch_id: str, errors: List[str]):
        self.patch_id = patch_id
        self.errors = errors
        super().__init__(f"Validation failed for {patch_id}: {errors}")


class PatchValidator:
    """Validates semantic patches before merge."""

    def __init__(self, strict: bool = True):
        """Initialize validator.

        Args:
            strict: If True, raise on first error. If False, collect all errors.
        """
        self.strict = strict

    def validate_all(self, patches: List[SemanticPatch]) -> dict:
        """Validate all patches in a list.

        Args:
            patches: List of patches to validate

        Returns:
            {
                "valid": int,  # number of valid patches
                "invalid": int,
                "errors": [  # detailed error list
                    {"patch_id": str, "errors": [str]}
                ]
            }
        """
        results = {
            "valid": 0,
            "invalid": 0,
            "errors": [],
        }

        for i, patch in enumerate(patches):
            try:
                self.validate_single(patch)
                results["valid"] += 1
            except PatchValidationError as e:
                results["invalid"] += 1
                results["errors"].append({
                    "patch_index": i,
                    "patch_id": str(patch.source_node),
                    "errors": e.errors,
                })

                if self.strict:
                    raise

        return results

    def validate_single(self, patch: SemanticPatch) -> None:
        """Validate single patch.

        Raises:
            PatchValidationError if validation fails
        """
        errors = []

        # Schema validation (Pydantic already does this on construction)
        try:
            patch.model_validate(patch.model_dump())
        except ValidationError as e:
            errors.append(f"Schema validation failed: {str(e)}")

        # Immutability check (frozen=True)
        if not patch.model_config.get("frozen"):
            errors.append("Patch is not frozen (frozen=True required)")

        # Source node must be non-empty
        if not patch.source_node or not patch.source_node.strip():
            errors.append("source_node cannot be empty")

        # Scene ID must be non-empty
        if not patch.scene_id or not patch.scene_id.strip():
            errors.append("scene_id cannot be empty")

        # Schema version must be recognized
        if patch.schema_version not in ["Phase2A.2", "Phase2A.3"]:
            errors.append(f"Unknown schema_version: {patch.schema_version}")

        # Patch order must be non-negative
        if patch.patch_order < 0:
            errors.append(f"patch_order cannot be negative: {patch.patch_order}")

        # Confidence bounds (if provided)
        if patch.motion_intensity is not None:
            if not (0.0 <= patch.motion_intensity <= 1.0):
                errors.append(
                    f"motion_intensity out of bounds: {patch.motion_intensity}"
                )

        # Entity validation
        if patch.characters is not None:
            for entity in patch.characters:
                errors.extend(self._validate_entity(entity, "character"))

        if patch.actions is not None:
            for entity in patch.actions:
                errors.extend(self._validate_entity(entity, "action"))

        if patch.objects is not None:
            for entity in patch.objects:
                errors.extend(self._validate_entity(entity, "object"))

        if patch.environments is not None:
            for entity in patch.environments:
                errors.extend(self._validate_entity(entity, "environment"))

        if patch.emotions is not None:
            for entity in patch.emotions:
                errors.extend(self._validate_entity(entity, "emotion"))

        if errors:
            raise PatchValidationError(patch.source_node, errors)

    def _validate_entity(self, entity: object, entity_type: str) -> List[str]:
        """Validate single entity.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check required fields
        if not hasattr(entity, "raw_name") or not entity.raw_name:
            errors.append(f"{entity_type}: raw_name cannot be empty")

        if not hasattr(entity, "normalized_name") or not entity.normalized_name:
            errors.append(f"{entity_type}: normalized_name cannot be empty")

        if not hasattr(entity, "confidence"):
            errors.append(f"{entity_type}: confidence required")
        elif not (0.0 <= entity.confidence <= 1.0):
            errors.append(
                f"{entity_type}: confidence out of bounds: {entity.confidence}"
            )

        # Check provenance
        if not hasattr(entity, "provenance") or entity.provenance is None:
            errors.append(f"{entity_type}: provenance required")
        else:
            prov_errors = self._validate_provenance(entity.provenance, entity_type)
            errors.extend(prov_errors)

        return errors

    def _validate_provenance(self, provenance: object, entity_type: str) -> List[str]:
        """Validate provenance info.

        Returns:
            List of error messages
        """
        errors = []

        if not hasattr(provenance, "source"):
            errors.append(f"{entity_type}: provenance.source required")

        if not hasattr(provenance, "source_version"):
            errors.append(f"{entity_type}: provenance.source_version required")

        if not hasattr(provenance, "confidence"):
            errors.append(f"{entity_type}: provenance.confidence required")
        elif not (0.0 <= provenance.confidence <= 1.0):
            errors.append(
                f"{entity_type}: provenance.confidence out of bounds: "
                f"{provenance.confidence}"
            )

        if not hasattr(provenance, "extraction_timestamp"):
            errors.append(f"{entity_type}: provenance.extraction_timestamp required")

        return errors

    def validate_patch_sequence(
        self,
        patches: List[SemanticPatch],
    ) -> dict:
        """Validate entire patch sequence for consistency.

        Checks:
        - All patches target same scene
        - No patch_order conflicts (different sources should have different orders)
        - Monotonic patch_order (optional warning)

        Returns:
            {
                "valid": bool,
                "warnings": [str],
                "errors": [str]
            }
        """
        results = {
            "valid": True,
            "warnings": [],
            "errors": [],
        }

        if not patches:
            return results

        # All patches must target same scene
        scene_id = patches[0].scene_id
        for i, patch in enumerate(patches[1:], 1):
            if patch.scene_id != scene_id:
                results["errors"].append(
                    f"Patch {i} targets {patch.scene_id}, "
                    f"but patches[0] targets {scene_id}"
                )
                results["valid"] = False

        # Check patch_order distribution
        order_source_map = {}
        for patch in patches:
            key = patch.patch_order
            if key not in order_source_map:
                order_source_map[key] = []
            order_source_map[key].append(patch.source_node)

        # Multiple sources at same order could indicate grouping for parallel execution
        for order, sources in order_source_map.items():
            if len(sources) > 1:
                results["warnings"].append(
                    f"Multiple sources at patch_order {order}: {sources}. "
                    "These will be sorted alphabetically by source_node."
                )

        return results
