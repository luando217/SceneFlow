"""Scene builder — assembles canonical SceneSemantic from raw extraction data.

The builder is the main orchestration entrypoint for Phase 2A.2.
It takes raw extraction output, normalizes it, and produces a
deterministic SceneSemantic instance.
"""

from .scene_builder import SceneBuilder

__all__ = [
    "SceneBuilder",
]