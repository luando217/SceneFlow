"""VisionNode — deterministic mock vision tag extraction node.

Extracts characters, actions, objects, emotions from scene frames.
Produces structured entity patches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode
from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    ObjectEntity,
)


class VisionNode(BaseSemanticNode):
    """Mock vision tag extraction node.

    Processes scene_input["vision_tags"] dict with:
    - characters: List[{"name": str, "confidence": float}]
    - actions:    List[{"action": str, "confidence": float}]
    - objects:    List[{"object": str, "confidence": float}]
    - emotions:   List[{"emotion": str, "confidence": float}]

    Produces typed entity patches.
    """

    node_id: str = "vision_node_v1"
    node_type: str = "vision"
    extraction_type: str = "vision_tags"

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        tags: Dict[str, Any] = scene_input.get("vision_tags", {})
        if not tags:
            return (
                {"detected_types": [], "num_detections": 0},
                [],
                1.0,
                ["no vision tags found in input"],
            )

        extracted_items: List[Dict[str, Any]] = []
        confidences: List[float] = []
        warnings: List[str] = []
        detected_types: List[str] = []

        # Process each entity type
        for entity_type in ("characters", "actions", "objects", "emotions"):
            entries = tags.get(entity_type, [])
            if not entries:
                continue
            detected_types.append(entity_type)

            for i, entry in enumerate(entries):
                name = str(
                    entry.get("name")
                    or entry.get("action")
                    or entry.get("object")
                    or entry.get("emotion")
                    or ""
                ).strip()
                conf = float(entry.get("confidence", 1.0))

                if not name:
                    warnings.append(
                        f"{entity_type}[{i}]: empty name"
                    )
                    continue

                item = {
                    "type": entity_type.rstrip("s"),
                    "name": name,
                    "confidence": min(conf, 1.0),
                    "index": len(extracted_items),
                }
                extracted_items.append(item)
                confidences.append(min(conf, 1.0))

        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        payload = {
            "detected_types": sorted(detected_types),
            "num_detections": len(extracted_items),
            "avg_confidence": round(avg_confidence, 3),
        }

        return payload, extracted_items, avg_confidence, warnings

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        chars: List[CharacterEntity] = []
        actions: List[ActionEntity] = []
        objects: List[ObjectEntity] = []
        emotions: List[EmotionEntity] = []

        for item in result.items:
            name = item["name"]
            conf = item["confidence"]
            etype = item["type"]

            if etype == "character":
                chars.append(
                    CharacterEntity(
                        name=name, confidence=conf
                    )
                )
            elif etype == "action":
                actions.append(
                    ActionEntity(
                        name=name, confidence=conf
                    )
                )
            elif etype == "object":
                objects.append(
                    ObjectEntity(
                        name=name, confidence=conf
                    )
                )
            elif etype == "emotion":
                emotions.append(
                    EmotionEntity(
                        name=name, confidence=conf
                    )
                )

        return SemanticPatch(
            source_node=self.node_id,
            scene_id=result.scene_id,
            characters=chars if chars else None,
            actions=actions if actions else None,
            objects=objects if objects else None,
            emotions=emotions if emotions else None,
            patch_order=30,
            warnings=result.warnings,
        )