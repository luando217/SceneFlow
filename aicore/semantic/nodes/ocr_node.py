"""OcrNode — deterministic mock OCR extraction node.

Extracts text regions from scene frames.
Produces normalized OCR text lines.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode


class OcrNode(BaseSemanticNode):
    """Mock OCR extraction node.

    Processes scene_input["ocr_regions"] list.
    Each region: {"text": str, "confidence": float, "bbox": [...]}
    Produces normalized OCR text.
    """

    node_id: str = "ocr_node_v1"
    node_type: str = "ocr"
    extraction_type: str = "ocr"

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        # Gather OCR regions from input (or use default)
        regions = scene_input.get("ocr_regions", [])
        if not regions:
            return (
                {"text": "", "num_regions": 0, "normalized": ""},
                [],
                1.0,
                ["no ocr regions found in input"],
            )

        extracted_items: List[Dict[str, Any]] = []
        all_text: List[str] = []
        confidences: List[float] = []
        warnings: List[str] = []

        for i, region in enumerate(regions):
            text = str(region.get("text", "")).strip()
            conf = float(region.get("confidence", 1.0))
            bbox = region.get("bbox", [0, 0, 0, 0])

            # Normalize: lowercase, collapse whitespace
            normalized = self._normalize_ocr(text)

            item = {
                "index": i,
                "raw_text": text,
                "normalized": normalized,
                "confidence": min(conf, 1.0),
                "bbox": bbox,
                "length": len(normalized),
            }
            extracted_items.append(item)

            if normalized:
                all_text.append(normalized)
                confidences.append(min(conf, 1.0))
            else:
                warnings.append(f"ocr region {i}: empty after normalization")

        # Merge text
        merged_text = " ".join(all_text)
        num_regions = len(extracted_items)
        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        payload = {
            "text_normalized": merged_text,
            "num_regions": num_regions,
            "avg_confidence": round(avg_confidence, 3),
        }

        return payload, extracted_items, avg_confidence, warnings

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        text = result.payload.get("text_normalized", "")
        num_regions = result.payload.get("num_regions", 0)

        patches = []
        if text:
            patches.append(
                SemanticPatch(
                    source_node=self.node_id,
                    scene_id=result.scene_id,
                    ocr_text=text,
                    num_text_regions=num_regions,
                    patch_order=10,
                    warnings=result.warnings,
                )
            )

        return patches[0] if patches else self._noop_patch(result)

    def _noop_patch(self, result: ExtractionResult) -> SemanticPatch:
        return SemanticPatch(
            source_node=self.node_id,
            scene_id=result.scene_id,
            patch_order=10,
            warnings=result.warnings,
        )

    @staticmethod
    def _normalize_ocr(text: str) -> str:
        """Normalize OCR text: lowercase, collapse whitespace."""
        import re

        text = text.lower().strip()
        text = re.sub(r"\s+", " ", text)
        return text