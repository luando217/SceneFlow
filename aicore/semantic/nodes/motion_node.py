"""MotionNode — deterministic mock motion semantic extraction node.

Analyzes scene motion intensity, direction, and pace.
Produces motion-related semantic patches.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.nodes.base import BaseSemanticNode


class MotionNode(BaseSemanticNode):
    """Mock motion extraction node.

    Processes scene_input["motion_data"] dict with:
    - intensity: float (0.0–1.0)
    - direction: str (e.g. "pan_left", "zoom_in", "static")
    - action_pace: str (e.g. "slow", "medium", "fast")
    - keyframe_count: int
    """

    node_id: str = "motion_node_v1"
    node_type: str = "motion"
    extraction_type: str = "motion"

    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        motion: Dict[str, Any] = scene_input.get("motion_data", {})
        warnings: List[str] = []

        if not motion:
            return (
                {
                    "intensity": 0.0,
                    "direction": "unknown",
                    "action_pace": "unknown",
                    "keyframe_count": 0,
                },
                [],
                1.0,
                ["no motion data found in input"],
            )

        intensity = float(motion.get("intensity", 0.0))
        intensity = max(0.0, min(1.0, intensity))

        direction = str(motion.get("direction", "static")).strip()
        if not direction:
            direction = "static"
            warnings.append("motion direction empty, defaulted to static")

        action_pace = str(motion.get("action_pace", "medium")).strip()
        if action_pace not in ("slow", "medium", "fast"):
            action_pace = "medium"
            warnings.append(
                "invalid action_pace, defaulted to medium"
            )

        keyframe_count = int(motion.get("keyframe_count", 0))

        items = [
            {
                "intensity": intensity,
                "direction": direction,
                "action_pace": action_pace,
                "keyframe_count": keyframe_count,
            }
        ]

        payload = {
            "intensity": intensity,
            "direction": direction,
            "action_pace": action_pace,
            "keyframe_count": keyframe_count,
        }

        return payload, items, intensity, warnings

    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        p = result.payload

        return SemanticPatch(
            source_node=self.node_id,
            scene_id=result.scene_id,
            motion_intensity=p.get("intensity"),
            motion_direction=p.get("direction"),
            action_pace=p.get("action_pace"),
            num_keyframes=p.get("keyframe_count", 0),
            patch_order=40,
            warnings=result.warnings,
        )