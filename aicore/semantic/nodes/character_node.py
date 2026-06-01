"""CharacterNode — deterministic mock character extraction node.

Detects character appearances and attributes from scene frames.
Produces character entity patches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode
from aicore.semantic.schemas.entities import CharacterEntity


class CharacterNode(BaseSemanticNode):
    """Mock character extraction node.

    Processes scene_input["character_detections"] list of:
    {"name": str, "confidence": float, "emotion": str, "spoken": str}

    Produces character entity patches.
    """

    node_id: str = "character_node_v1"
    node_type: str = "character"
    extraction_type: str = "character_tags"

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        detections: List[Dict[str, Any]] = scene_input.get(
            "character_detections", []
        )
        warnings: List[str] = []

        if not detections:
            return (
                {"characters": [], "num_chars": 0},
                [],
                1.0,
                ["no character detections found in input"],
            )

        extracted_items: List[Dict[str, Any]] = []
        confidences: List[float] = []

        for i, det in enumerate(detections):
            name = str(det.get("name", "")).strip()
            conf = float(det.get("confidence", 1.0))
            emotion = str(det.get("emotion", "")).strip()
            spoken = str(det.get("spoken", "")).strip()

            if not name:
                warnings.append(
                    f"character detection {i}: empty name"
                )
                continue

            item = {
                "index": i,
                "name": name,
                "confidence": min(conf, 1.0),
                "emotion": emotion or "neutral",
                "spoken": spoken,
            }
            extracted_items.append(item)
            confidences.append(min(conf, 1.0))

        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        payload: Dict[str, Any] = {
            "num_chars": len(extracted_items),
            "character_names": sorted(
                e["name"] for e in extracted_items
            ),
        }

        return payload, extracted_items, avg_confidence, warnings

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        characters: List[CharacterEntity] = []

        for item in result.items:
            spoken_lines: List[str] = []
            if item.get("spoken"):
                spoken_lines.append(item["spoken"])

            characters.append(
                CharacterEntity(
                    name=item["name"],
                    confidence=item["confidence"],
                    spoken_lines=spoken_lines,
                )
            )

        return SemanticPatch(
            source_node=self.node_id,
            scene_id=result.scene_id,
            characters=characters if characters else None,
            patch_order=60,
            warnings=result.warnings,
        )