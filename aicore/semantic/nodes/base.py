"""BaseSemanticNode — abstract contract for all semantic extraction nodes.

Every node:
- Receives a scene_input (dict with scene metadata)
- Produces ExtractionResult + SemanticPatch
- Is deterministic given the same input
- Never mutates SceneSemantic directly
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Tuple

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.node_metadata import NodeMetadata
from aicore.semantic.contracts.semantic_patch import SemanticPatch


class BaseSemanticNode(ABC):
    """Abstract base for all semantic extraction nodes.

    Subclasses must implement:
    - node_id        (class attr)
    - node_type      (class attr)
    - extraction_type (class attr)
    - _extract()     (returns payload dict + items list + confidence)
    - _build_patch() (returns SemanticPatch from extraction output)
    """

    node_id: str = "base_node"
    node_type: str = "base"
    extraction_type: str = "base_extraction"

    def __init__(self, extractor_version: str = "mock-v1") -> None:
        self._extractor_version = extractor_version

    # ── Public API ────────────────────────────────────────────────────

    def execute(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[ExtractionResult, SemanticPatch]:
        """Execute extraction and return (result, patch).

        Deterministic for same scene_input.
        No side effects — pure data transformation.
        """
        scene_id = scene_input.get("scene_id", "unknown")
        time_range = self._build_time_range(scene_input)

        # Create metadata
        meta = NodeMetadata(
            node_id=self.node_id,
            node_type=self.node_type,
            extraction_type=self.extraction_type,
            input_scene_id=scene_id,
            input_scene_time_range=time_range,
            extractor_version=self._extractor_version,
        )

        # Extract
        payload, items, confidence, warnings = self._extract(scene_input)

        # Build result
        result = ExtractionResult(
            source_node=self.node_id,
            extraction_type=self.extraction_type,
            scene_id=scene_id,
            confidence=confidence,
            payload=payload,
            items=items,
            warnings=warnings,
            metadata=meta.finish(),
        )

        # Build patch
        patch = self._build_patch(result, scene_input)

        return result, patch

    # ── Hooks ─────────────────────────────────────────────────────────

    @abstractmethod
    def _extract(
        self, scene_input: Dict[str, Any]
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]], float, List[str]]:
        """Perform extraction logic.

        Returns (payload_dict, items_list, confidence, warnings).
        Pure data — no side effects.
        """
        ...

    @abstractmethod
    def _build_patch(
        self,
        result: ExtractionResult,
        scene_input: Dict[str, Any],
    ) -> SemanticPatch:
        """Build a SemanticPatch from extraction result.

        This is the ONLY way nodes affect SceneSemantic.
        """
        ...

    # ── Helpers ──────────────────────────────────────────────────────

    def _build_time_range(self, scene_input: Dict[str, Any]) -> str:
        start = scene_input.get("start_time", "?")
        end = scene_input.get("end_time", "?")
        return f"{start}→{end}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(node_id={self.node_id}, type={self.node_type})"
        )