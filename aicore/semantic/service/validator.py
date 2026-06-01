"""SemanticValidator — validation rules for deterministic SceneSemantic integrity.

Checks:
- Required fields are present and non-empty
- Temporal consistency (start <= end)
- Confidence scores in [0, 1]
- Entity lists are sorted (deterministic ordering)
- No duplicate normalized names within the same entity list
- Motion direction and action pace are valid enum values
"""

from __future__ import annotations

from typing import Any, List, Optional

from aicore.semantic.schemas.scene_semantic import SceneSemantic


class ValidationError(ValueError):
    """Raised when a SceneSemantic fails validation."""

    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(f"[{field}] {message}" if field else message)


class SemanticValidator:
    """Validates SceneSemantic instances for structural/semantic integrity."""

    VALID_MOTION_DIRECTIONS = {
        "left", "right", "up", "down", "circular", "static"
    }
    VALID_ACTION_PACES = {"slow", "normal", "fast", "intense"}

    def validate(self, scene: SceneSemantic) -> List[str]:
        """Validate a SceneSemantic instance.

        Returns a list of error messages (empty = valid).
        """
        errors: List[str] = []

        # Required string fields
        if not scene.scene_id:
            errors.append("scene_id must not be empty")
        if not scene.video_id:
            errors.append("video_id must not be empty")

        # Temporal consistency
        if scene.start_time < 0:
            errors.append("start_time must be >= 0")
        if scene.end_time < 0:
            errors.append("end_time must be >= 0")
        if scene.start_time > scene.end_time:
            errors.append("start_time must be <= end_time")
        if scene.start_frame < 0:
            errors.append("start_frame must be >= 0")
        if scene.end_frame < 0:
            errors.append("end_frame must be >= 0")
        if scene.start_frame > scene.end_frame:
            errors.append("start_frame must be <= end_frame")

        # Duration consistency
        expected_duration = scene.end_time - scene.start_time
        if abs(scene.duration - expected_duration) > 0.001:
            errors.append(
                f"duration {scene.duration} != end_time - start_time "
                f"({expected_duration})"
            )

        # Motion
        if not (0.0 <= scene.motion_intensity <= 1.0):
            errors.append("motion_intensity must be in [0, 1]")
        if scene.motion_direction not in self.VALID_MOTION_DIRECTIONS:
            errors.append(
                f"motion_direction '{scene.motion_direction}' "
                f"not in {self.VALID_MOTION_DIRECTIONS}"
            )
        if scene.action_pace not in self.VALID_ACTION_PACES:
            errors.append(
                f"action_pace '{scene.action_pace}' "
                f"not in {self.VALID_ACTION_PACES}"
            )

        # Entity list validation
        errors.extend(
            self._validate_entity_list(scene.characters, "characters")
        )
        errors.extend(
            self._validate_entity_list(scene.actions, "actions")
        )
        errors.extend(
            self._validate_entity_list(scene.objects, "objects")
        )
        errors.extend(
            self._validate_entity_list(scene.environments, "environments")
        )
        errors.extend(
            self._validate_entity_list(scene.emotions, "emotions")
        )

        # Metadata
        if scene.num_keyframes < 0:
            errors.append("num_keyframes must be >= 0")
        if scene.num_text_regions < 0:
            errors.append("num_text_regions must be >= 0")

        # Schema version
        if not scene.schema_version:
            errors.append("schema_version must not be empty")

        return errors

    def validate_or_raise(
        self, scene: SceneSemantic
    ) -> SceneSemantic:
        """Validate and raise on first error."""
        errors = self.validate(scene)
        if errors:
            msg = "; ".join(errors[:3])
            raise ValidationError(f"Validation failed: {msg}")
        return scene

    def is_valid(self, scene: SceneSemantic) -> bool:
        """Quick validity check (no error messages)."""
        return len(self.validate(scene)) == 0

    # ── Internal ─────────────────────────────────────────────────────

    def _validate_entity_list(
        self,
        entities: List[Any],
        field_name: str,
    ) -> List[str]:
        """Validate a list of entities for common issues."""
        errors: List[str] = []
        seen_names: set = set()

        for i, entity in enumerate(entities):
            # Must have normalized_name
            name = getattr(entity, "normalized_name", None)
            if not name:
                errors.append(f"{field_name}[{i}]: missing normalized_name")

            # Check duplicates
            if name and name in seen_names:
                errors.append(
                    f"{field_name}: duplicate normalized_name '{name}'"
                )
            seen_names.add(name)

            # Confidence must be in [0, 1]
            confidence = getattr(entity, "confidence", 1.0)
            if not (0.0 <= confidence <= 1.0):
                errors.append(
                    f"{field_name}[{i}] '{name}': "
                    f"confidence {confidence} not in [0, 1]"
                )

        return errors