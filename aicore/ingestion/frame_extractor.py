"""
FrameExtractor — extract frames from video using FFmpeg.

Deterministic frame extraction:
- Extract all frames at a given rate (fps)
- Extract specific frame indices
- Extract keyframes only
- Store as PNG files with deterministic naming
"""

from __future__ import annotations

import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from .schemas import FrameInfo, frame_time_str


class FrameExtractor:
    """
    Extracts frames from video files using FFmpeg.

    Output frames are stored as PNG files in a configurable output directory.
    """

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        output_dir: str = "frames_output",
        quality: int = 2,  # 2-31, lower = better
    ) -> None:
        self._ffmpeg_path = ffmpeg_path
        self._output_dir = Path(output_dir)
        self._quality = quality
        self._available = self._check_ffmpeg()

        self._last_output_dir: Optional[Path] = None
        self._extracted_frames: list[FrameInfo] = []

    # ------------------------------------------------------------------
    # Extraction methods
    # ------------------------------------------------------------------

    def extract_all_at_fps(
        self,
        video_path: str,
        fps: float = 1.0,
        output_dir: Optional[str] = None,
        max_frames: int = 0,
    ) -> list[FrameInfo]:
        """
        Extract frames at a fixed rate (e.g. 1 fps).
        Returns list of FrameInfo for each extracted frame.
        """
        video = Path(video_path)
        out = self._resolve_output_dir(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self._clean_output(out)

        pattern = str(out / "frame_%05d.png")

        cmd = [
            self._ffmpeg_path,
            "-i", str(video),
            "-vf", f"fps={fps}",
            "-qscale:v", str(self._quality),
            "-y",
            "-an",
            pattern,
        ]

        self._run_ffmpeg(cmd)
        return self._index_output_frames(out, video)

    def extract_frames_at_indices(
        self,
        video_path: str,
        indices: list[int],
        fps: float,
        output_dir: Optional[str] = None,
    ) -> list[FrameInfo]:
        """
        Extract specific frame indices using select filter.
        """
        video = Path(video_path)
        out = self._resolve_output_dir(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self._clean_output(out)

        # Use select filter with frame indices (ffmpeg is 0-based + 1)
        select_expr = "+".join(f"eq(n,{i})" for i in indices)
        pattern = str(out / "frame_%05d.png")

        cmd = [
            self._ffmpeg_path,
            "-i", str(video),
            "-vf", f"select='{select_expr}',setpts=N/FRAME_RATE/TB",
            "-qscale:v", str(self._quality),
            "-y",
            "-an",
            pattern,
        ]

        self._run_ffmpeg(cmd)
        return self._index_output_frames(out, video)

    def extract_keyframes(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
    ) -> list[FrameInfo]:
        """
        Extract only keyframes (I-frames) from video.
        Useful as a fast first-pass for scene detection.
        """
        video = Path(video_path)
        out = self._resolve_output_dir(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        self._clean_output(out)

        pattern = str(out / "keyframe_%05d.png")

        cmd = [
            self._ffmpeg_path,
            "-i", str(video),
            "-vf", "select='eq(pict_type,I)'",
            "-vsync", "vfr",
            "-qscale:v", str(self._quality),
            "-y",
            "-an",
            pattern,
        ]

        self._run_ffmpeg(cmd)
        return self._index_output_frames(out, video, prefix="keyframe_")

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _index_output_frames(
        self,
        output_dir: Path,
        video_path: Path,
        prefix: str = "frame_",
    ) -> list[FrameInfo]:
        """Scan output directory and build FrameInfo list."""
        frames: list[FrameInfo] = []
        png_files = sorted(output_dir.glob(f"{prefix}*.png"))

        frame_index = 0
        for fpath in png_files:
            try:
                # Parse frame number from filename
                stem = fpath.stem.replace(prefix, "")
                seq = int(stem)
            except ValueError:
                seq = frame_index

            # Estimate timestamp from sequence number
            frames.append(FrameInfo(
                index=seq,
                timestamp_sec=0.0,  # Will be computed from FPS later
                timestamp_str="",
                file_path=str(fpath),
                is_keyframe=(prefix == "keyframe_"),
            ))
            frame_index += 1

        self._extracted_frames = frames
        self._last_output_dir = output_dir
        return frames

    def _resolve_output_dir(self, output_dir: Optional[str]) -> Path:
        if output_dir:
            return Path(output_dir)
        return self._output_dir

    @staticmethod
    def _clean_output(directory: Path) -> None:
        """Remove existing frame files for clean extraction."""
        if directory.exists():
            for f in directory.glob("*.png"):
                f.unlink()

    # ------------------------------------------------------------------
    # FFmpeg
    # ------------------------------------------------------------------

    def _run_ffmpeg(self, cmd: list[str]) -> None:
        if not self._available:
            raise RuntimeError("FFmpeg not available on PATH")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=3600
            )
            if result.returncode != 0:
                # FFmpeg may write warnings to stderr even on success
                if "error" in result.stderr.lower():
                    raise RuntimeError(
                        f"FFmpeg error (code {result.returncode}): {result.stderr[:500]}"
                    )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"FFmpeg timed out: {exc}") from exc

    @staticmethod
    def _check_ffmpeg() -> bool:
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return True
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return False

    # ------------------------------------------------------------------
    # Debug helpers
    # ------------------------------------------------------------------

    @property
    def last_output_dir(self) -> Optional[str]:
        return str(self._last_output_dir) if self._last_output_dir else None

    @property
    def extracted_frames(self) -> list[FrameInfo]:
        return self._extracted_frames

    def to_dict(self) -> dict:
        return {
            "total_extracted": len(self._extracted_frames),
            "output_dir": self.last_output_dir,
            "frames": [f.to_dict() for f in self._extracted_frames],
        }