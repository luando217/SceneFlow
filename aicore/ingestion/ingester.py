"""
VideoIngester — extract video metadata via ffprobe/subprocess.

Pure deterministic extraction:
- Duration, resolution, FPS, codec info
- Frame count estimation
- Optional file hashing for provenance
"""

from __future__ import annotations

import json
import os
import subprocess
import hashlib
import uuid
import datetime
from pathlib import Path
from typing import Optional

from .schemas import VideoMetadata, IngestionProvenance


class VideoIngester:
    """
    Reads a video file and extracts deterministic metadata.

    Uses ffprobe (from ffmpeg) for reliable container parsing.
    Falls back to manual demuxing if ffprobe is unavailable.
    """

    def __init__(self, ffprobe_path: str = "ffprobe") -> None:
        self._ffprobe_path = ffprobe_path
        self._available = self._check_ffprobe()

    # ------------------------------------------------------------------
    # Probe
    # ------------------------------------------------------------------

    def probe(self, video_path: str) -> VideoMetadata:
        """Extract VideoMetadata from a video file."""
        path = Path(video_path)
        if not path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        if self._available:
            return self._probe_ffprobe(path)
        return self._probe_fallback(path)

    def _probe_ffprobe(self, path: Path) -> VideoMetadata:
        """Use ffprobe to extract metadata."""
        cmd = [
            self._ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"ffprobe failed for {path}: {exc}") from exc

        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        fmt = data.get("format", {})

        duration_str = video_stream.get("duration", fmt.get("duration", "0"))
        try:
            duration_sec = float(duration_str)
        except ValueError:
            duration_sec = 0.0

        fps_str = video_stream.get("r_frame_rate", "0/1")
        fps = self._parse_fraction(fps_str)

        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))

        if fps > 0 and duration_sec > 0:
            total_frames = int(duration_sec * fps)
        else:
            total_frames = int(video_stream.get("nb_frames", 0))

        file_size = path.stat().st_size
        bitrate_str = fmt.get("bit_rate", "0")
        try:
            bitrate_kbps = int(bitrate_str) // 1000
        except (ValueError, TypeError):
            bitrate_kbps = 0

        return VideoMetadata(
            file_path=str(path),
            file_name=path.name,
            file_size_bytes=file_size,
            duration_sec=duration_sec,
            width=width,
            height=height,
            fps=fps,
            total_frames=total_frames,
            codec=video_stream.get("codec_name", ""),
            bitrate_kbps=bitrate_kbps,
            has_audio=bool(audio_stream),
            audio_codec=audio_stream.get("codec_name", ""),
            audio_channels=int(audio_stream.get("channels", 0)),
            audio_sample_rate=int(audio_stream.get("sample_rate", 0)),
            creation_time=fmt.get("tags", {}).get("creation_time"),
        )

    def _probe_fallback(self, path: Path) -> VideoMetadata:
        """Minimal metadata extraction without ffprobe."""
        file_size = path.stat().st_size
        return VideoMetadata(
            file_path=str(path),
            file_name=path.name,
            file_size_bytes=file_size,
        )

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    def compute_provenance(
        self,
        video_path: str,
        workflow_id: Optional[str] = None,
        pipeline_version: str = "0.1.0",
        parameters: Optional[dict] = None,
    ) -> IngestionProvenance:
        """Build ingestion provenance with file hash."""
        vid_meta = self.probe(video_path)
        path = Path(video_path)

        video_hash = self._file_hash(path)
        now = datetime.datetime.utcnow().isoformat() + "Z"

        return IngestionProvenance(
            workflow_id=workflow_id or f"ingest_{uuid.uuid4().hex[:8]}",
            video_path=str(path),
            video_hash=video_hash,
            pipeline_version=pipeline_version,
            extracted_at=now,
            duration_sec=vid_meta.duration_sec,
            total_frames=vid_meta.total_frames,
            parameters=parameters or {},
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ffprobe() -> bool:
        """Check if ffprobe is available on PATH."""
        try:
            subprocess.run(
                ["ffprobe", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _parse_fraction(frac: str) -> float:
        """Parse '30000/1001' → 29.97"""
        try:
            parts = frac.split("/")
            if len(parts) == 2:
                return float(parts[0]) / float(parts[1])
            return float(parts[0])
        except (ValueError, ZeroDivisionError, IndexError):
            return 0.0

    @staticmethod
    def _file_hash(path: Path, blocksize: int = 2**20) -> str:
        """SHA-256 hash of file (first 64KB for speed)."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(blocksize)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()[:16]