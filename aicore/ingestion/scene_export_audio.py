"""
SceneExportAudio — ffmpeg-based scene clip export with audio preservation.

Phase 1B: Ensures exported scene clips NEVER lose audio.
Every export:
- Preserves original audio stream(s)
- Maintains A/V sync
- Uses MP4 / H.264 + AAC baseline
- Tracks export metadata (has_audio, codec, duration)
- Validates output with ffprobe
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from .schemas import SceneInfo, SceneExportMeta, VideoMetadata


class SceneExportAudio:
    """
    Audio-safe scene clip exporter.

    Uses ffmpeg to cut scene segments with full audio preservation.
    All exports are validated post-hoc with ffprobe.
    """

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        ffprobe_path: str = "ffprobe",
        output_dir: str = "data/test_outputs/scene_clips",
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        preset: str = "fast",
        crf: int = 23,
    ) -> None:
        self._ffmpeg = ffmpeg_path
        self._ffprobe = ffprobe_path
        self._output_dir = Path(output_dir)
        self._video_codec = video_codec
        self._audio_codec = audio_codec
        self._preset = preset
        self._crf = crf

        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._available = self._check_ffmpeg()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export_scene(
        self,
        scene: SceneInfo,
        video_path: str,
        overwrite: bool = False,
    ) -> SceneExportMeta:
        """
        Export a single scene clip with audio.

        Args:
            scene: SceneInfo with start/end timestamps
            video_path: Source video file path
            overwrite: Overwrite existing output file

        Returns:
            SceneExportMeta with export results and audio validation
        """
        video_path_obj = Path(video_path)
        scene_id = scene.scene_id

        # Construct output filename: {video_name}_scene_{id}.mp4
        output_filename = f"{video_path_obj.stem}_{scene_id}.mp4"
        output_path = self._output_dir / output_filename

        # Build ffmpeg command
        ss = scene.start_timestamp_str
        to = scene.end_timestamp_str

        cmd = self._build_export_cmd(
            input_path=str(video_path_obj),
            output_path=str(output_path),
            start_time=ss,
            end_time=to,
            overwrite=overwrite,
        )

        export_meta = SceneExportMeta(
            scene_id=scene_id,
            export_path=str(output_path),
            ffmpeg_cmd=" ".join(cmd),
        )

        # Run ffmpeg
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 min for long exports
            )
            export_meta.export_success = result.returncode == 0
        except (subprocess.TimeoutExpired, OSError) as exc:
            export_meta.export_success = False
            raise RuntimeError(f"ffmpeg export failed for {scene_id}: {exc}") from exc

        if not export_meta.export_success:
            raise RuntimeError(
                f"ffmpeg export failed for {scene_id}:\n"
                f"stderr: {result.stderr[:2000]}"
            )

        # File info
        if output_path.exists():
            export_meta.file_size_bytes = output_path.stat().st_size

        # Validate output with ffprobe
        probe = self._probe_export(str(output_path))
        export_meta.has_audio = probe.get("has_audio", False)
        export_meta.audio_codec = probe.get("audio_codec", "")
        export_meta.sample_rate = probe.get("sample_rate", 0)
        export_meta.channel_layout = probe.get("channel_layout", "")
        export_meta.export_duration_sec = probe.get("duration_sec", 0.0)

        return export_meta

    def export_scenes_batch(
        self,
        scenes: list[SceneInfo],
        video_path: str,
        overwrite: bool = False,
        scene_ids: Optional[list[str]] = None,
    ) -> list[SceneExportMeta]:
        """
        Export multiple scene clips.

        Args:
            scenes: List of SceneInfo
            video_path: Source video file path
            overwrite: Overwrite existing files
            scene_ids: Optional subset of scene IDs to export (None = all)

        Returns:
            List of SceneExportMeta for exported scenes
        """
        results: list[SceneExportMeta] = []
        filter_ids = set(scene_ids) if scene_ids else None

        for scene in scenes:
            if filter_ids and scene.scene_id not in filter_ids:
                continue
            meta = self.export_scene(scene, video_path, overwrite=overwrite)
            results.append(meta)

        return results

    # ------------------------------------------------------------------
    # ffmpeg command builder
    # ------------------------------------------------------------------

    def _build_export_cmd(
        self,
        input_path: str,
        output_path: str,
        start_time: str,
        end_time: str,
        overwrite: bool = False,
    ) -> list[str]:
        """
        Build ffmpeg command for audio-safe scene export.

        Strategy:
        - Seek after -i for frame-accurate cutting (re-encode)
        - Map video stream 0, audio stream 0
        - Re-encode video with libx264 for clean cuts at non-keyframes
        - Encode audio with AAC for MP4 compatibility
        """
        cmd = [self._ffmpeg]

        # Overwrite output without asking
        if overwrite:
            cmd.append("-y")

        cmd.extend([
            "-i", input_path,
            "-ss", start_time,
            "-to", end_time,
            "-map", "0:v:0",      # first video stream
            "-map", "0:a:0",      # first audio stream
            "-c:v", self._video_codec,
            "-c:a", self._audio_codec,
            "-preset", self._preset,
            "-crf", str(self._crf),
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])

        cmd.append(output_path)
        return cmd

    # ------------------------------------------------------------------
    # ffprobe validation
    # ------------------------------------------------------------------

    def _probe_export(self, clip_path: str) -> dict:
        """
        Probe an exported clip with ffprobe to verify audio presence.

        Returns dict with:
        - has_audio: bool
        - audio_codec: str
        - sample_rate: int
        - channel_layout: str
        - duration_sec: float
        """
        result: dict = {
            "has_audio": False,
            "audio_codec": "",
            "sample_rate": 0,
            "channel_layout": "",
            "duration_sec": 0.0,
        }

        if not Path(clip_path).exists():
            return result

        cmd = [
            self._ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            clip_path,
        ]

        try:
            probe_result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            data = json.loads(probe_result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return result

        streams = data.get("streams", [])
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        fmt = data.get("format", {})

        if audio_stream:
            result["has_audio"] = True
            result["audio_codec"] = audio_stream.get("codec_name", "")
            sr = audio_stream.get("sample_rate", "0")
            try:
                result["sample_rate"] = int(sr)
            except (ValueError, TypeError):
                result["sample_rate"] = 0
            result["channel_layout"] = audio_stream.get("channel_layout", "")

        duration_str = fmt.get("duration", "0")
        try:
            result["duration_sec"] = float(duration_str)
        except ValueError:
            result["duration_sec"] = 0.0

        return result

    def validate_clip_audio(self, clip_path: str) -> bool:
        """
        Quick validation: does the clip have audio?
        Used in test assertions.
        """
        probe = self._probe_export(clip_path)
        return probe["has_audio"]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ffmpeg() -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            return True
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
            return False