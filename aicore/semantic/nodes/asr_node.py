"""AsrNode — deterministic mock ASR/dialogue extraction node.

Extracts dialogue segments from scene audio.
Produces normalized dialogue text with speaker annotations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode


class AsrNode(BaseSemanticNode):
    """Mock ASR extraction node.

    Processes scene_input["dialogue_segments"] list.
    Each segment: speaker, text, confidence, start fields.
    Produces normalized dialogue text.
    """

    node_id: str = "asr_node_v1"
    node_type: str = "asr"
    extraction_type: str = "dialogue"

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        segments = scene_input.get("dialogue_segments", [])
        if not segments:
            return (
                {"dialogue": "", "num_segments": 0, "normalized": ""},
                [],
                1.0,
                ["no dialogue segments found in input"],
            )

        extracted_items: List[Dict[str, Any]] = []
        all_dialogue: List[str] = []
        confidences: List[float] = []
        warnings: List[str] = []

        for i, seg in enumerate(segments):
            speaker = str(seg.get("speaker", "unknown")).strip()
            text = str(seg.get("text", "")).strip()
            conf = float(seg.get("confidence", 1.0))
            seg_start = seg.get("start", 0.0)

            # Normalize dialogue
            normalized = self._normalize_dialogue(text)

            item = {
                "index": i,
                "speaker": speaker,
                "raw_text": text,
                "normalized": normalized,
                "confidence": min(conf, 1.0),
                "start_time": seg_start,
                "length": len(normalized),
            }
            extracted_items.append(item)

            if normalized:
                dialogue_line = f"[{speaker}] {normalized}"
                all_dialogue.append(dialogue_line)
                confidences.append(min(conf, 1.0))
            else:
                warnings.append(
                    f"dialogue segment {i}: empty after normalization"
                )

        merged_dialogue = "\n".join(all_dialogue)
        num_segments = len(extracted_items)
        avg_confidence = (
            sum(confidences) / len(confidences) if confidences else 0.0
        )

        payload = {
            "dialogue_normalized": merged_dialogue,
            "num_segments": num_segments,
            "avg_confidence": round(avg_confidence, 3),
        }
        return payload, extracted_items, avg_confidence, warnings

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        dialogue = result.payload.get("dialogue_normalized", "")

        if not dialogue:
            return SemanticPatch(
                source_node=self.node_id,
                scene_id=result.scene_id,
                patch_order=20,
                warnings=result.warnings,
            )

        return SemanticPatch(
            source_node=self.node_id,
            scene_id=result.scene_id,
            dialogue=dialogue,
            patch_order=20,
            warnings=result.warnings,
        )

    @staticmethod
    def _normalize_dialogue(text: str) -> str:
        """Normalize dialogue: strip extra whitespace, preserve case."""
        import re

        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text