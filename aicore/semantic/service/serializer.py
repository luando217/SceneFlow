"""Deterministic JSON serializer for SceneSemantic and entity schemas.

Provides stable, inspectable serialization with deterministic field ordering.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from aicore.semantic.schemas.scene_semantic import SceneSemantic


class SemanticSerializer:
    """Deterministic JSON serializer for semantic schema objects."""

    def serialize_scene(
        self,
        scene: SceneSemantic,
        indent: int = 2,
    ) -> str:
        """Serialize a SceneSemantic to a deterministic JSON string."""
        return scene.to_json(indent=indent)

    def serialize_scene_batch(
        self,
        scenes: List[SceneSemantic],
        indent: int = 2,
    ) -> str:
        """Serialize multiple SceneSemantic instances to a JSON array.

        Scenes are sorted by scene_id for deterministic ordering.
        """
        sorted_scenes = sorted(scenes, key=lambda s: s.scene_id)
        dicts = [s.to_dict_deterministic() for s in sorted_scenes]
        return json.dumps(dicts, indent=indent, default=str)

    def serialize_to_dict(self, scene: SceneSemantic) -> Dict[str, Any]:
        """Serialize to a dict with deterministic key ordering."""
        return scene.to_dict_deterministic()