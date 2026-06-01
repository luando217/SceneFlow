"""
SceneExporter — structured JSON export with provenance tracking.

Produces inspectable, reproducible scene metadata files.
Each export includes:
- Full scene list with frame indices and timestamps
- Per-frame feature summaries
- Ingestion provenance (pipeline version, workflow ID, file hash)
- Keyframe index
"""

from __future__ import annotations

import json
import os
import datetime
from pathlib import Path
from typing import Optional

from .schemas import (
    SceneInfo,
    FrameFeatures,
    FrameInfo,
    VideoMetadata,
    IngestionProvenance,
    SceneMetadata,
)


class SceneExporter:
    """
    Exports scene/frame metadata to structured JSON files.

    All output is deterministic, inspectable, and reproducible.
    """

    def __init__(self, output_dir: str = "scene_export") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._last_scenes_json: Optional[str] = None
        self._last_provenance_json: Optional[str] = None

    # ------------------------------------------------------------------
    # Export methods
    # ------------------------------------------------------------------

    def export_scenes(
        self,
        scenes: list[SceneInfo],
        video_meta: VideoMetadata,
        provenance: IngestionProvenance,
        output_dir: Optional[str] = None,
        filename: str = "scenes.json",
    ) -> str:
        """
        Export scene list to JSON.
        Returns the path to the written file.
        """
        out_dir = Path(output_dir) if output_dir else self._output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "0.1.0",
            "schema": "aicore_ingestion_scenes_v1",
            "exported_at": datetime.datetime.utcnow().isoformat() + "Z",
            "provenance": provenance.to_dict(),
            "video_metadata": video_meta.to_dict(),
            "total_scenes": len(scenes),
            "scenes": [s.to_dict() for s in scenes],
        }

        path = out_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._last_scenes_json = str(path)
        return str(path)

    def export_scene_details(
        self,
        scene_metadata_list: list[SceneMetadata],
        output_dir: Optional[str] = None,
        prefix: str = "scene_",
    ) -> list[str]:
        """
        Export per-scene metadata files.
        Each scene gets its own file for granular inspection.

        Returns list of written file paths.
        """
        out_dir = Path(output_dir) if output_dir else self._output_dir
        out_dir = out_dir / "scene_details"
        out_dir.mkdir(parents=True, exist_ok=True)

        paths: list[str] = []
        for sm in scene_metadata_list:
            data = sm.to_dict()
            data["exported_at"] = datetime.datetime.utcnow().isoformat() + "Z"

            path = out_dir / f"{prefix}{sm.features.index:04d}.json"
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            paths.append(str(path))

        return paths

    def export_frame_index(
        self,
        frames: list[FrameInfo],
        output_dir: Optional[str] = None,
        filename: str = "frame_index.json",
    ) -> str:
        """
        Export frame index (list of all extracted frames with metadata).
        """
        out_dir = Path(output_dir) if output_dir else self._output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "0.1.0",
            "total_frames": len(frames),
            "frames": [f.to_dict() for f in frames],
        }

        path = out_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self._last_frame_index = str(path)
        return str(path)

    def export_provenance(
        self,
        provenance: IngestionProvenance,
        output_dir: Optional[str] = None,
        filename: str = "provenance.json",
    ) -> str:
        """
        Export provenance separately for cache/trace inspection.
        """
        out_dir = Path(output_dir) if output_dir else self._output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        path = out_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(provenance.to_dict(), f, indent=2, ensure_ascii=False)

        self._last_provenance_json = str(path)
        return str(path)

    # ------------------------------------------------------------------
    # Load / round-trip
    # ------------------------------------------------------------------

    @staticmethod
    def load_scenes(path: str) -> tuple[list[SceneInfo], IngestionProvenance]:
        """
        Load scenes from exported JSON.
        Returns (scenes, provenance).
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        scenes = [SceneInfo.from_dict(s) for s in data["scenes"]]
        provenance = IngestionProvenance.from_dict(data["provenance"])
        return scenes, provenance

    # ------------------------------------------------------------------
    # Debug
    # ------------------------------------------------------------------

    @property
    def last_scenes_file(self) -> Optional[str]:
        return self._last_scenes_json

    @property
    def last_provenance_file(self) -> Optional[str]:
        return self._last_provenance_json