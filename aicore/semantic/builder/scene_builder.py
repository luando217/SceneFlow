
"""SceneBuilder — assembles canonical SceneSemantic from raw extraction inputs.

Takes raw extraction output from Phase 1 (scene detection, OCR, ASR, motion,
tagging) and produces a fully validated, deterministic SceneSemantic instance.

Usage:
    builder = SceneBuilder()
    semantic = builder.build(
        scene_id="scene_001",
        video_id="episode_01",
        start_time=12.5,
        end_time=45.0,
        start_frame=312,
        end_frame=1125,
        raw_characters=["Naruto", "Sasuke"],
        raw_actions=["running", "punching"],
        raw_objects=["kunai"],
        raw_environments=["forest"],
        raw_emotions=["determined"],
        dialogue="I will never give up!",
        ocr_text="Episode 1: The Beginning",
        motion_intensity=0.7,
        motion_direction="right",
        action_pace="fast",
        num_keyframes=8,
        num_text_regions=1,
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from aicore.semantic.normalizer.entity_normalizer import EntityNormalizer
from aicore.semantic.normalizer.text_normalizer import TextNormalizer
from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class SceneBuilder:
    """Builder that normalizes raw extraction data into SceneSemantic.

    Stateless — all normalization is deterministic per-instance.
    Thread-safe (no mutable state).
    """

    def __init__(
        self,
        entity_normalizer: Optional[EntityNormalizer] = None,
        text_normalizer: Optional[TextNormalizer] = None,
    ):
        self._entity_normalizer = entity_normalizer or EntityNormalizer()
        self._text_normalizer = text_normalizer or TextNormalizer()

    # ── Public API ───────────────────────────────────────────────────

    def build(
        self,
        scene_id: str,
        video_id: str,
        start_time: float,
        end_time: float,
        start_frame: int,
        end_frame: int,
        # Optional extraction inputs
        raw_characters: Optional[List[str]] = None,
        raw_actions: Optional[List[str]] = None,
        raw_objects: Optional[List[str]] = None,
        raw_environments: Optional[List[str]] = None,
        raw_emotions: Optional[List[str]] = None,
        dialogue: str = "",
        ocr_text: str = "",
        motion_intensity: float = 0.0,
        motion_direction: str = "static",
        action_pace: str = "slow",
        episode_id: Optional[str] = None,
        num_keyframes: int = 0,
        num_text_regions: int = 0,
        warnings: Optional[List[str]] = None,
    ) -> SceneSemantic:
        """Build a fully validated SceneSemantic from raw extraction data.

        Args:
            scene_id: Unique scene identifier.
            video_id: Source video identifier.
            start_time: Scene start time in seconds.
            end_time: Scene end time in seconds.
            start_frame: 0-based start frame number.
            end_frame: 0-based end frame number.
            raw_characters: List of raw character names.
            raw_actions: List of raw action descriptors.
            raw_objects: List of raw object names.
            raw_environments: List of raw environment descriptors.
            raw_emotions: List of raw emotion descriptors.
            dialogue: Raw ASR transcript.
            ocr_text: Raw OCR text.
            motion_intensity: Aggregated motion magnitude [0, 1].
            motion_direction: Dominant motion direction.
            action_pace: Detected action pace.
            episode_id: Optional episode identifier.
            num_keyframes: Number of keyframes sampled.
            num_text_regions: Number of OCR text regions detected.

        Returns:
            Fully validated SceneSemantic instance.
        """
        # Normalize text
        norm_dialogue, norm_ocr = self._text_normalizer.normalize_and_merge(
            dialogue=dialogue,
            ocr=ocr_text,
        )

        # Normalize entities
        characters = self._normalize_characters(raw_characters or [])
        actions = self._normalize_actions(raw_actions or [])
        objects = self._normalize_objects(raw_objects or [])
        environments = self._normalize_environments(raw_environments or [])
        emotions = self._normalize_emotions(raw_emotions or [])

        # Compute duration
        duration = end_time - start_time

        # Build SceneSemantic
        scene = SceneSemantic(
            scene_id=scene_id,
            video_id=video_id,
            episode_id=episode_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            start_frame=start_frame,
            end_frame=end_frame,
            characters=characters,
            actions=actions,
            objects=objects,
            environments=environments,
            emotions=emotions,
            dialogue=norm_dialogue,
            ocr_text=norm_ocr,
            motion_intensity=motion_intensity,
            motion_direction=motion_direction,
            action_pace=action_pace,
            num_keyframes=num_keyframes,
            num_text_regions=num_text_regions,
            warnings=warnings or [],
        )

        return scene

    def build_from_dict(self, data: Dict[str, Any]) -> SceneSemantic:
        """Build a SceneSemantic from a dictionary (e.g. JSON config).

        Supports all fields accepted by ``build()`` with identical keys.
        """
        return self.build(
            scene_id=data["scene_id"],
            video_id=data["video_id"],
            start_time=float(data["start_time"]),
            end_time=float(data["end_time"]),
            start_frame=int(data["start_frame"]),
            end_frame=int(data["end_frame"]),
            raw_characters=data.get("raw_characters"),
            raw_actions=data.get("raw_actions"),
            raw_objects=data.get("raw_objects"),
            raw_environments=data.get("raw_environments"),
            raw_emotions=data.get("raw_emotions"),
            dialogue=data.get("dialogue", ""),
            ocr_text=data.get("ocr_text", ""),
            motion_intensity=float(data.get("motion_intensity", 0.0)),
            motion_direction=data.get("motion_direction", "static"),
            action_pace=data.get("action_pace", "slow"),
            episode_id=data.get("episode_id"),
            num_keyframes=int(data.get("num_keyframes", 0)),
            num_text_regions=int(data.get("num_text_regions", 0)),
            warnings=data.get("warnings"),
        )

    # ── Internal helpers ─────────────────────────────────────────────

    def _normalize_characters(
        self, raw_names: List[str]
    ) -> List[CharacterEntity]:
        """Normalize and deduplicate character names."""
        return self._entity_normalizer.normalize_character_batch(raw_names)

    def _normalize_actions(
        self, raw_actions: List[str]
    ) -> List[ActionEntity]:
        """Normalize action descriptors."""
        seen: set = set()
        entities: List[ActionEntity] = []
        for raw in raw_actions:
            if raw and raw not in seen:
                seen.add(raw)
                entities.append(
                    self._entity_normalizer.normalize_action(
                        raw, confidence=0.7
                    )
                )
        entities.sort(key=lambda e: e.normalized_name)
        return entities

    def _normalize_objects(
        self, raw_objects: List[str]
    ) -> List[ObjectEntity]:
        """Normalize object names."""
        seen: set = set()
        entities: List[ObjectEntity] = []
        for raw in raw_objects:
            if raw and raw not in seen:
                seen.add(raw)
                entities.append(
                    self._entity_normalizer.normalize_object(
                        raw, confidence=0.7
                    )
                )
        entities.sort(key=lambda e: e.normalized_name)
        return entities

    def _normalize_environments(
        self, raw_environments: List[str]
    ) -> List[EnvironmentEntity]:
        """Normalize environment descriptors."""
        seen: set = set()
        entities: List[EnvironmentEntity] = []
        for raw in raw_environments:
            if raw and raw not in seen:
                seen.add(raw)
                entities.append(
                    self._entity_normalizer.normalize_environment(
                        raw, location=raw, confidence=0.7
                    )
                )
        entities.sort(key=lambda e: e.normalized_name)
        return entities

    def _normalize_emotions(
        self, raw_emotions: List[str]
    ) -> List[EmotionEntity]:
        """Normalize and deduplicate emotion descriptors."""
        seen: set = set()
        entities: List[EmotionEntity] = []
        for raw in raw_emotions:
            if not raw:
                continue
            normalized = self._entity_normalizer.normalize_name(raw)
            if normalized and normalized not in seen:
                seen.add(normalized)
                entities.append(
                    self._entity_normalizer.normalize_emotion(
                        raw, confidence=0.7
                    )
                )
        entities.sort(key=lambda e: e.normalized_name)
        return entities
