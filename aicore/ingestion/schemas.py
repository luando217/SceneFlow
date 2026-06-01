"""
Phase 1A/1B dataclasses — typed, inspectable, serializable.

All frame-level and scene-level metadata is structured, never prose.
Phase 1B adds audio-aware export metadata fields.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def frame_time_str(seconds: float) -> str:
    """Format float seconds → HH:MM:SS.mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _compute_hash(data: dict) -> str:
    raw = json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Frame-level
# ---------------------------------------------------------------------------

@dataclass
class FrameInfo:
    """
    Metadata for a single extracted frame (keyframe or sampled).
    Stored on disk, referenced by index.
    """
    index: int                    # 0-based frame index in source video
    timestamp_sec: float          # absolute time in seconds
    timestamp_str: str            # HH:MM:SS.mmm formatted
    file_path: str                # relative path to stored frame image
    width: int = 0
    height: int = 0
    is_keyframe: bool = False
    scene_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> FrameInfo:
        return cls(**d)


@dataclass
class FrameFeatures:
    """
    Deterministic frame-level features — no AI, entirely heuristic.
    """
    frame_index: int
    timestamp_sec: float
    # --- Colour ---
    mean_brightness: float = 0.0        # 0-1
    mean_saturation: float = 0.0        # 0-1
    dominant_color_rgb: tuple[int, int, int] = (0, 0, 0)
    # --- Histogram ---
    histogram_bins: list[int] = field(default_factory=list)  # 256-bin grey histogram
    histogram_diff_to_prev: float = 0.0   # correlation diff from previous frame
    # --- Activity ---
    motion_magnitude: float = 0.0        # mean optical flow magnitude (if computed)
    edge_density: float = 0.0            # proportion of edge pixels (0-1)
    dark_pixel_ratio: float = 0.0        # pixels below threshold
    is_black_frame: bool = False         # near-black frame detection
    # --- Text / sub ---
    letterbox_ratio: float = 0.0         # detected letterbox/pillarbox ratio
    # --- Hashes (deterministic perceptual) ---
    dhash: str = ""                      # difference hash (64-bit hex)
    phash: str = ""                      # perceptual hash (64-bit hex)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dominant_color_rgb"] = list(self.dominant_color_rgb)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> FrameFeatures:
        if isinstance(d.get("dominant_color_rgb"), list):
            d["dominant_color_rgb"] = tuple(d["dominant_color_rgb"])
        return cls(**d)


# ---------------------------------------------------------------------------
# Scene-level
# ---------------------------------------------------------------------------

@dataclass
class SceneInfo:
    """
    A detected scene — contiguous segment with shared visual context.
    """
    scene_id: str                      # e.g. "scene_0001"
    index: int                         # 0-based scene index
    start_frame: int                   # first frame index (inclusive)
    end_frame: int                     # last frame index (inclusive)
    start_timestamp_sec: float
    end_timestamp_sec: float
    duration_sec: float
    start_timestamp_str: str = ""
    end_timestamp_str: str = ""
    keyframe_indices: list[int] = field(default_factory=list)
    frame_count: int = 0
    # --- Aggregate features ---
    avg_brightness: float = 0.0
    avg_saturation: float = 0.0
    avg_motion: float = 0.0
    # --- Detection flags ---
    is_intro: bool = False              # heuristic intro detection
    is_outro: bool = False              # heuristic outro detection
    is_black: bool = False              # fully black segment
    is_static: bool = False             # no camera / object motion
    # --- Provenance ---
    detection_method: str = ""          # "color_histogram" | "optical_flow" | "ffprobe_scene"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SceneInfo:
        return cls(**d)


@dataclass
class SceneMetadata:
    """
    Rich scene metadata — aggregates all frame-level features.
    Attached to each scene for retrieval without re-extraction.
    """
    scene_id: str
    video_path: str
    features: SceneInfo
    frames: list[FrameInfo] = field(default_factory=list)
    frame_features: list[FrameFeatures] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "video_path": self.video_path,
            "features": self.features.to_dict(),
            "frames": [f.to_dict() for f in self.frames],
            "frame_features": [ff.to_dict() for ff in self.frame_features],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SceneMetadata:
        return cls(
            scene_id=d["scene_id"],
            video_path=d["video_path"],
            features=SceneInfo.from_dict(d["features"]),
            frames=[FrameInfo.from_dict(f) for f in d.get("frames", [])],
            frame_features=[FrameFeatures.from_dict(ff) for ff in d.get("frame_features", [])],
        )


# ---------------------------------------------------------------------------
# Video-level
# ---------------------------------------------------------------------------

@dataclass
class VideoMetadata:
    """
    Top-level video metadata extracted via ffprobe or direct parsing.
    """
    file_path: str
    file_name: str
    file_size_bytes: int = 0
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    total_frames: int = 0
    codec: str = ""
    bitrate_kbps: int = 0
    has_audio: bool = False
    audio_codec: str = ""
    audio_channels: int = 0
    audio_sample_rate: int = 0
    creation_time: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> VideoMetadata:
        return cls(**d)


# ---------------------------------------------------------------------------
# Scene export metadata (Phase 1B)
# ---------------------------------------------------------------------------

@dataclass
class SceneExportMeta:
    """
    Audio-aware export metadata for a single scene clip.
    Tracks ffmpeg export results and audio stream verification.
    """
    scene_id: str
    export_path: str
    export_duration_sec: float = 0.0
    has_audio: bool = False
    audio_codec: str = ""
    sample_rate: int = 0
    channel_layout: str = ""
    file_size_bytes: int = 0
    ffmpeg_cmd: str = ""
    export_success: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> SceneExportMeta:
        return cls(**d)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

@dataclass
class IngestionProvenance:
    """
    Tracks the complete lineage of an ingestion run.
    Enables reproducibility and cache invalidation.
    """
    workflow_id: str
    video_path: str
    video_hash: str = ""                # SHA-256 of video file
    pipeline_version: str = "0.1.0"
    extracted_at: str = ""              # ISO timestamp
    duration_sec: float = 0.0
    total_frames: int = 0
    total_scenes: int = 0
    total_keyframes: int = 0
    parameters: dict = field(default_factory=dict)
    cache_keys: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> IngestionProvenance:
        return cls(**d)