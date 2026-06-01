"""EnvironmentNode — deterministic mock environment extraction node.

Detects environment/background context from scene frames.
Produces environment entity patches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode
from aicore.semantic.schemas.entities import EnvironmentEntity


class EnvironmentNode(BaseSemanticNode):
    """Mock environment extraction node.

    Processes scene_input["environment_tags"] list of:
    {"location": str, "atmosphere": str, "confidence": float}

    Produces environment entity patches.
    """

    node_id: str = "environment_node_v1"
    node_type: str = "environment"
    extraction_type: str = "environment_tags"

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        env_tags: List[Dict[str, Any]] = scene_input.get(
            "environment_tags", []
        )
        warnings: List[str] = []

        if not env_tags:
            return (
                {"environments": [], "num_envs": 0},
                [],
                1.0,
                ["no environment tags found in input"],
            )

        extracted_items: List[Dict[str, Any]] = []
        confidences: List[float] = []

        for i, tag in enumerate(env_tags):
            location = str(tag.get("location", "")).strip()
            atmosphere = str(tag.get("atmosphere", "")).strip()
            conf = float(tag.get("confidence", 1.0))

            if not location:
                warnings.append(f"environment tag {i}: empty location")
                continue

            item = {
                "index": i,
                "location": location,
                "atmosphere": atmosphere or "neutral",
                "confidence": min(conf, 1.0),
            }
            extracted_items.append(item)
            confidences.append(min(conf, 1.0))

        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        payload: Dict[str, Any] = {
            "num_envs": len(extracted_items),
            "locations": sorted(
                e["location"] for e in extracted_items
            ),
        }

        return payload, extracted_items, avg_confidence, warnings

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        environments: List[EnvironmentEntity] = []

        for item in result.items:
            environments.append(
                EnvironmentEntity(
                    name=item["location"],
                    location=item["location"],
                    confidence=item["confidence"],
                )
            )

        return SemanticPatch(
            source_node=self.node_id,
            scene_id=result.scene_id,
            environments=environments if environments else None,
            patch_order=50,
            warnings=result.warnings,
        )