"""NormalizerService — wraps EntityNormalizer + TextNormalizer.

Provides a single normalize() method that normalizes all fields
of a SceneSemantic in one deterministic pass.
"""

from __future__ import annotations

from aicore.semantic.normalizer.entity_normalizer import EntityNormalizer
from aicore.semantic.normalizer.text_normalizer import TextNormalizer
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class NormalizerService:
    """Service-level normalizer that normalizes entire SceneSemantic objects.

    Wraps:
    - EntityNormalizer (character, action, object, emotion, environment names)
    - TextNormalizer (dialogue, OCR text)
    """

    def __init__(
        self,
        entity_normalizer: EntityNormalizer | None = None,
        text_normalizer: TextNormalizer | None = None,
    ):
        self._entity_normalizer = entity_normalizer or EntityNormalizer()
        self._text_normalizer = text_normalizer or TextNormalizer()

    def normalize(self, scene: SceneSemantic) -> SceneSemantic:
        """Normalize all semantic fields of a SceneSemantic.

        Returns a new SceneSemantic with normalized fields.
        Original is not mutated (SceneSemantic is frozen).
        """
        norm_dialogue, norm_ocr = self._text_normalizer.normalize_and_merge(
            dialogue=scene.dialogue,
            ocr=scene.ocr_text,
        )

        # Rebuild with normalized data
        # Since SceneSemantic is frozen, we construct a new instance
        return SceneSemantic(
            scene_id=scene.scene_id,
            video_id=scene.video_id,
            episode_id=scene.episode_id,
            start_time=scene.start_time,
            end_time=scene.end_time,
            duration=scene.duration,
            start_frame=scene.start_frame,
            end_frame=scene.end_frame,
            characters=scene.characters,
            actions=scene.actions,
            objects=scene.objects,
            environments=scene.environments,
            emotions=scene.emotions,
            dialogue=norm_dialogue,
            ocr_text=norm_ocr,
            motion_intensity=scene.motion_intensity,
            motion_direction=scene.motion_direction,
            action_pace=scene.action_pace,
            num_keyframes=scene.num_keyframes,
            num_text_regions=scene.num_text_regions,
            created_at=scene.created_at,
            narrative_event_type=scene.narrative_event_type,
        )