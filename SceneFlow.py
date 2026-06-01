"""
SceneFlow - Unified Timeline Inspection Workflow
- Select Video: file picker, path display, embedded QMediaPlayer playback.
- Choose Output: folder selector, default output/<video_name>/
- Detect Scenes: PySceneDetect only, no export.
- Timeline: horizontal scene blocks with thumbnails, click to seek.
- Master timing source: exact floating-point FPS from video metadata.
- GPU encoder selection: auto-detect NVIDIA/AMD/Intel or fallback to CPU x264.
- Subtitle timeline layer: load .srt/.ass, match to scenes.
- Manual export: MP4 clips, PNG frames, Metadata JSON - separate operations.
- Synchronized playback: video + scenes + subtitles + audio regions move together.
- SF-8E: Runtime subtitle safety, hard cut, clean package export.
"""

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
from PySide6.QtCore import QPoint, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFrame,
    QMessageBox,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from scenedetect import detect, ContentDetector


# Encoder options
ENCODER_OPTIONS = [
    ("auto", "Auto-detect (NVIDIA \u2192 CPU)"),
    ("nvenc", "NVIDIA NVENC"),
    ("amf", "AMD AMF"),
    ("qsv", "Intel QSV"),
    ("cpu", "CPU x264"),
]

ENCODER_PRESETS = {
    "nvenc": {"codec": "h264_nvenc", "preset": "p5", "quality": "-cq 18"},
    "amf":   {"codec": "h264_amf",   "preset": "balanced", "quality": "-qp 18"},
    "qsv":   {"codec": "h264_qsv",   "preset": "medium",   "quality": "-global_quality 18"},
    "cpu":   {"codec": "libx264",    "preset": "fast",     "quality": "-crf 18"},
}


def detect_gpu_encoder() -> str:
    """Auto-detect available GPU encoder, fallback to CPU."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        if "h264_nvenc" in result.stdout:
            return "nvenc"
        if "h264_amf" in result.stdout:
            return "amf"
        if "h264_qsv" in result.stdout:
            return "qsv"
    except Exception:
        pass
    return "cpu"


@dataclass
class VideoMetadata:
    """Master timing source - extracted ONCE on video load."""
    path: str
    real_fps: float
    total_frames: int
    duration: float
    width: int
    height: int
    codec: str

    def duration_str(self) -> str:
        m = int(self.duration // 60)
        s = self.duration % 60
        return f"{m}:{s:05.2f}"


@dataclass
class AudioRegion:
    """Audio region with type classification and energy level."""
    start: float
    end: float
    type: str  # "silence", "speech", "music", "high_energy", "music_speech"
    energy: float  # 0.0 to 1.0


@dataclass
class Subtitle:
    """Subtitle entry with timing and text."""
    start: float
    end: float
    text: str


@dataclass
class SegmentProfile:
    """Human-confirmed segment profile for intro/outro detection."""
    type: str  # "intro" or "outro"
    scene_start: int
    scene_end: int
    time_start: float
    time_end: float
    duration: float
    audio_summary: dict
    subtitle_summary: dict
    scene_summary: dict

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "scene_start": self.scene_start,
            "scene_end": self.scene_end,
            "time_start": round(self.time_start, 3),
            "time_end": round(self.time_end, 3),
            "duration": round(self.duration, 3),
            "audio_summary": self.audio_summary,
            "subtitle_summary": self.subtitle_summary,
            "scene_summary": self.scene_summary,
        }

    @staticmethod
    def from_dict(data: dict) -> "SegmentProfile":
        return SegmentProfile(
            type=data["type"],
            scene_start=data["scene_start"],
            scene_end=data["scene_end"],
            time_start=data["time_start"],
            time_end=data["time_end"],
            duration=data["duration"],
            audio_summary=data.get("audio_summary", {}),
            subtitle_summary=data.get("subtitle_summary", {}),
            scene_summary=data.get("scene_summary", {}),
        )


PROFILE_DIR = Path("output") / "profiles"


# ---------------------------------------------------------------------------
# Profile Helpers
# ---------------------------------------------------------------------------

def build_audio_summary(regions: list[AudioRegion], scene_start: float, scene_end: float) -> dict:
    """Build deterministic audio summary for a range of scenes."""
    overlapping = [
        r for r in regions
        if r.start < scene_end and r.end > scene_start
    ]
    if not overlapping:
        return {"dominant": "unknown", "avg_energy": 0.0}
    type_duration: dict[str, float] = {}
    total_energy = 0.0
    for r in overlapping:
        overlap_dur = min(r.end, scene_end) - max(r.start, scene_start)
        if overlap_dur > 0:
            type_duration[r.type] = type_duration.get(r.type, 0) + overlap_dur
            total_energy += r.energy * overlap_dur
    total_overlap = sum(type_duration.values())
    dominant = max(type_duration, key=type_duration.get) if type_duration else "unknown"
    avg_energy = total_energy / total_overlap if total_overlap > 0 else 0.0
    return {
        "dominant": dominant,
        "avg_energy": round(avg_energy, 3),
    }


def build_subtitle_summary(subtitles: list[Subtitle], scene_start: float, scene_end: float) -> dict:
    """Build deterministic subtitle summary for a range of scenes."""
    matched = [s for s in subtitles if scene_start <= s.start <= scene_end]
    total_dur = scene_end - scene_start
    return {
        "line_count": len(matched),
        "density": round(len(matched) / total_dur, 3) if total_dur > 0 else 0.0,
    }


def build_scene_summary(scenes, fps: float, start_idx: int, end_idx: int) -> dict:
    """Build deterministic scene summary for a range of scenes."""
    selected = [s for s in scenes if start_idx <= s.index <= end_idx]
    if not selected:
        return {"scene_count": 0, "avg_scene_duration": 0.0}
    avg_dur = sum(s.duration_sec(fps) for s in selected) / len(selected)
    return {
        "scene_count": len(selected),
        "avg_scene_duration": round(avg_dur, 3),
    }


def save_profile(profile: SegmentProfile, video_name: str) -> None:
    """Save a segment profile to output/profiles/<video_name>/."""
    profile_dir = PROFILE_DIR / video_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{profile.type}_profile.json"
    path = profile_dir / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"[PROFILE] Saved {profile.type} profile: {path}")


def load_profile(video_name: str, profile_type: str) -> Optional[SegmentProfile]:
    """Load a segment profile from output/profiles/<video_name>/."""
    path = PROFILE_DIR / video_name / f"{profile_type}_profile.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SegmentProfile.from_dict(data)
    except Exception as e:
        print(f"[PROFILE] Load error: {e}")
        return None


def compute_profile_similarity(
    profile: SegmentProfile,
    scenes,
    fps: float,
    audio_regions,
    subtitles,
    candidate_start: int,
    candidate_end: int,
) -> float:
    """Heuristic similarity score (0 to 1) between a saved profile and a candidate range.
    No AI, no embeddings. Uses duration, subtitle density, audio dominant type, scene pacing.
    """
    if candidate_start < 1 or candidate_end > len(scenes):
        return 0.0

    # Candidate stats
    cand_scenes = [s for s in scenes if candidate_start <= s.index <= candidate_end]
    if not cand_scenes:
        return 0.0

    cand_time_start = cand_scenes[0].start_sec(fps)
    cand_time_end = cand_scenes[-1].end_sec(fps)
    cand_duration = cand_time_end - cand_time_start
    if cand_duration <= 0:
        return 0.0

    # Duration similarity (weight: 0.4)
    dur_ratio = min(cand_duration, profile.duration) / max(cand_duration, profile.duration)
    dur_score = dur_ratio * 0.4

    # Scene count similarity (weight: 0.2)
    cnt_ratio = min(len(cand_scenes), profile.scene_summary.get("scene_count", 1)) / max(len(cand_scenes), profile.scene_summary.get("scene_count", 1), 1)
    scene_score = cnt_ratio * 0.2

    # Subtitle density similarity (weight: 0.2)
    cand_sub = build_subtitle_summary(subtitles, cand_time_start, cand_time_end)
    prof_density = profile.subtitle_summary.get("density", 0)
    cand_density = cand_sub.get("density", 0)
    den_ratio = min(cand_density, prof_density) / max(cand_density, prof_density, 0.001)
    subtitle_score = den_ratio * 0.2

    # Audio dominant type match (weight: 0.2)
    cand_audio = build_audio_summary(audio_regions, cand_time_start, cand_time_end)
    audio_match = 1.0 if cand_audio.get("dominant") == profile.audio_summary.get("dominant") else 0.0
    audio_score = audio_match * 0.2

    return round(dur_score + scene_score + subtitle_score + audio_score, 3)


def suggest_matches(
    profile: SegmentProfile,
    scenes,
    fps: float,
    audio_regions,
    subtitles,
    threshold: float = 0.65,
) -> tuple[Optional[int], Optional[int], float]:
    """Slide a window through scenes to find best match for a profile.
    Returns (best_start, best_end, best_score) or (None, None, 0.0).
    """
    prof_scene_count = profile.scene_summary.get("scene_count", 1)
    if not scenes or prof_scene_count == 0:
        return None, None, 0.0

    best_score = 0.0
    best_start = None
    best_end = None
    total = len(scenes)

    # Slide range: allow ±50% scene count flexibility
    min_count = max(1, int(prof_scene_count * 0.5))
    max_count = min(total, int(prof_scene_count * 1.5))

    for count in range(min_count, max_count + 1):
        for i in range(total - count + 1):
            start_idx = scenes[i].index
            end_idx = scenes[i + count - 1].index
            score = compute_profile_similarity(
                profile, scenes, fps, audio_regions, subtitles, start_idx, end_idx
            )
            if score > best_score:
                best_score = score
                best_start = start_idx
                best_end = end_idx

    if best_score >= threshold:
        return best_start, best_end, best_score
    return None, None, 0.0


@dataclass
class Scene:
    index: int  # Runtime index (1-based, changes after cuts)
    source_id: int  # ORIGINAL source scene ID (NEVER changes) - for reconstruction
    start_frame: int
    end_frame: int
    output_path: str = ""
    frame_path: str = ""
    png_exported: bool = False
    metadata_exported: bool = False
    mp4_exported: bool = False
    thumbnail: QPixmap | None = None
    subtitles: list[Subtitle] = field(default_factory=list)
    # SF-RUNTIME: Filter state (PART 5)
    filtered: bool = False
    filtered_reason: str = ""  # "intro", "outro", etc.

    def start_sec(self, fps: float) -> float:
        return self.start_frame / fps

    def end_sec(self, fps: float) -> float:
        return self.end_frame / fps

    def duration_sec(self, fps: float) -> float:
        return (self.end_frame - self.start_frame) / fps

    def duration_str(self, fps: float) -> str:
        d = self.duration_sec(fps)
        m = int(d // 60)
        s = d % 60
        return f"{m}:{s:05.2f}"


def parse_srt(path: str) -> list[Subtitle]:
    """Parse .srt subtitle file."""
    subs = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = re.compile(
            r"(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*"
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n(.*?)(?=\n\n\d+\s*\n|\Z)",
            re.DOTALL | re.IGNORECASE,
        )
        for m in pattern.finditer(content):
            start_str = m.group(2).replace(",", ".")
            end_str = m.group(3).replace(",", ".")
            start = parse_timestamp(start_str)
            end = parse_timestamp(end_str)
            text = m.group(4).strip().replace("\n", " ")
            if text:
                subs.append(Subtitle(start=start, end=end, text=text))
    except Exception as e:
        print(f"[SUBTITLE] SRT parse error: {e}")
    return subs


def parse_ass(path: str) -> list[Subtitle]:
    """Parse .ass/.ssa subtitle file."""
    subs = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = re.compile(
            r"Dialogue:\s*\d+,(\d+:\d{2}:\d{2}\.\d{2}),"
            r"(\d+:\d{2}:\d{2}\.\d{2}),.*?,.*?,.*?,.*?,.*?,(.*)",
            re.IGNORECASE,
        )
        for m in pattern.finditer(content):
            start = parse_ass_timestamp(m.group(1))
            end = parse_ass_timestamp(m.group(2))
            text = m.group(3).strip()
            text = re.sub(r"\{[^}]*\}", "", text)
            text = text.replace("\\h", " ").replace("\\N", " ").replace("\\n", " ")
            text = re.sub(r"\\[^a-z]", " ", text)
            text = text.strip()
            if text:
                subs.append(Subtitle(start=start, end=end, text=text))
    except Exception as e:
        print(f"[SUBTITLE] ASS parse error: {e}")
    return subs


def parse_timestamp(ts: str) -> float:
    """Parse SRT timestamp (HH:MM:SS,mmm) to seconds."""
    parts = ts.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = float(parts[2].replace(",", "."))
    return h * 3600 + m * 60 + s


def parse_ass_timestamp(ts: str) -> float:
    """Parse ASS timestamp (H:MM:SS.cc) to seconds."""
    parts = ts.split(":")
    h = int(parts[0])
    m = int(parts[1])
    s = float(parts[2])
    return h * 3600 + m * 60 + s


def match_subtitles_to_scenes(
    subtitles, scenes, fps: float
) -> None:
    """Match subtitles to scenes."""
    for scene in scenes:
        scene.subtitles = []
    for sub in subtitles:
        for scene in scenes:
            start_sec = scene.start_frame / fps
            end_sec = scene.end_frame / fps
            if sub.start >= start_sec and sub.start <= end_sec:
                scene.subtitles.append(sub)
                break


def export_scene_metadata(
    scenes, fps: float, output_dir: str, video_name: str
) -> None:
    """Export metadata JSON per scene to output_dir/metadata/"""  # SF-RUNTIME: Now preserves source_id
    meta_dir = Path(output_dir) / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)

    # SF-APP1-PART2: Filter to active scenes and generate dynamic runtime index
    active_scenes = [s for s in scenes if not s.filtered]

    for runtime_idx, scene in enumerate(active_scenes, start=1):
        print(f"[PACKAGE] exporting source_scene_id={scene.source_id:04d}")
        # SF-APP1-PART2: Use runtime_idx for runtime_scene_index, source_id is immutable
        meta = {
            "runtime_scene_index": runtime_idx,  # SF-APP1: Dynamic runtime ordering
            "source_scene_id": scene.source_id,  # SF-RUNTIME: Immutable source identity
            "scene_file": f"scene_src_{scene.source_id:04d}.mp4",  # SF-PART1: source_id in filename
            "start": round(scene.start_sec(fps), 3),
            "end": round(scene.end_sec(fps), 3),
            "duration": round(scene.duration_sec(fps), 3),
            "source_start_frame": scene.start_frame,  # SF-RUNTIME: Original frame start
            "source_end_frame": scene.end_frame,      # SF-RUNTIME: Original frame end
            # SF-APP1-PART3: Portable package-relative frame path
            "frame_path": f"frames/scene_src_{scene.source_id:04d}.png",
            "subtitle_count": len(scene.subtitles),
            "subtitles": [
                {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text}
                for s in scene.subtitles
            ],
            # SF-PART5: Filter state preserved in metadata
            "filtered": scene.filtered,
            "filtered_reason": scene.filtered_reason,
        }
        # SF-PART1: Use source_id for filename
        out_path = meta_dir / f"scene_src_{scene.source_id:04d}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        scene.metadata_exported = True
        print(f"[METADATA] Exported scene_src_{scene.source_id:04d}.json (source_id={scene.source_id})")


# =============================================================================
# Workers
# =============================================================================

class DetectWorker(QThread):
    """Detect scenes only - no export."""
    finished = Signal(list)
    error = Signal(str)
    stage_changed = Signal(str)
    progress_updated = Signal(int)

    def __init__(self, video_path: str, metadata: VideoMetadata):
        super().__init__()
        self._video_path = video_path
        self._metadata = metadata

    def run(self):
        try:
            self.stage_changed.emit("detecting scenes")
            self.progress_updated.emit(10)
            scene_list = detect(self._video_path, ContentDetector())

            total = len(scene_list)
            if total == 0:
                self.error.emit("No scenes detected")
                return

            self.stage_changed.emit("building timeline")
            self.progress_updated.emit(50)

            fps = self._metadata.real_fps
            scenes: list["Scene"] = []
            prev_end = 0

            for i, scene_tup in enumerate(scene_list):
                scene_num = i + 1
                start_frame = scene_tup[0].get_frames()
                end_frame = scene_tup[1].get_frames()

                if start_frame < prev_end:
                    start_frame = prev_end
                if start_frame >= end_frame:
                    continue

                # SF-PART1: Preserve source identity with source_id
                scene = Scene(
                    index=scene_num,
                    source_id=scene_num,  # SF-RUNTIME: Original source ID - NEVER changes
                    start_frame=start_frame,
                    end_frame=end_frame,
                )
                scenes.append(scene)
                prev_end = end_frame

                pct = 50 + int((i + 1) / total * 50)
                self.progress_updated.emit(pct)

            self.progress_updated.emit(100)
            self.finished.emit(scenes)

        except Exception as e:
            self.error.emit(str(e))


class ExportMP4Worker(QThread):
    """Export MP4 clips to output/scenes/"""
    finished = Signal()
    error = Signal(str)
    stage_changed = Signal(str)
    progress_updated = Signal(int)

    def __init__(self, video_path: str, scenes: list[Scene], fps: float,
                 output_dir: str, video_name: str, encoder: str):
        super().__init__()
        self._video_path = video_path
        self._scenes = scenes
        self._fps = fps
        self._output_dir = output_dir
        self._video_name = video_name
        self._encoder = encoder

    def run(self):
        try:
            self.stage_changed.emit("exporting MP4 clips")
            scenes_dir = Path(self._output_dir) / "scenes"
            scenes_dir.mkdir(parents=True, exist_ok=True)

            enc_key = self._encoder if self._encoder != "auto" else detect_gpu_encoder()
            enc_preset = ENCODER_PRESETS.get(enc_key, ENCODER_PRESETS["cpu"])

            for i, scene in enumerate(self._scenes):
                # SF-PART3: Use source_id for immutable filename identity
                start_sec = scene.start_frame / self._fps
                end_sec = scene.end_frame / self._fps
                out_path = scenes_dir / f"scene_src_{scene.source_id:04d}.mp4"
                scene.output_path = str(out_path)

                cmd = [
                    "ffmpeg", "-y",
                    "-i", self._video_path,
                    "-ss", str(start_sec),
                    "-to", str(end_sec),
                    "-c:v", enc_preset["codec"],
                    "-preset", enc_preset["preset"],
                ]
                quality_parts = enc_preset["quality"].split()
                cmd.extend(quality_parts)
                cmd.extend([
                    "-c:a", "aac",
                    "-avoid_negative_ts", "make_zero",
                    str(out_path),
                ])
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode != 0:
                    print(f"[EXPORT MP4] Scene {scene.source_id}: {result.stderr[:150]}")
                else:
                    scene.mp4_exported = True
                    print(f"[EXPORT MP4] Scene {scene.source_id}: {out_path}")

                pct = int((i + 1) / len(self._scenes) * 100)
                self.progress_updated.emit(pct)

            self.progress_updated.emit(100)
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


class ExportPNGWorker(QThread):
    """Export PNG frames to output/frames/"""
    finished = Signal()
    error = Signal(str)
    stage_changed = Signal(str)
    progress_updated = Signal(int)

    def __init__(self, video_path: str, scenes: list[Scene], fps: float,
                 output_dir: str, video_name: str):
        super().__init__()
        self._video_path = video_path
        self._scenes = scenes
        self._fps = fps
        self._output_dir = output_dir
        self._video_name = video_name

    def run(self):
        try:
            self.stage_changed.emit("exporting PNG frames")
            frames_dir = Path(self._output_dir) / "frames"
            frames_dir.mkdir(parents=True, exist_ok=True)

            cap = cv2.VideoCapture(self._video_path)
            if not cap.isOpened():
                self.error.emit("Cannot open video")
                return

            for i, scene in enumerate(self._scenes):
                # SF-PART3: Use source_id for immutable filename identity
                mid_frame = (scene.start_frame + scene.end_frame) // 2
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
                ret, frame = cap.read()

                if ret:
                    # SF-APP1-RUNTIME-CLEANUP: Simplified naming (no video-name prefix, source identity)
                    out_path = frames_dir / f"scene_src_{scene.source_id:04d}.png"
                    cv2.imwrite(str(out_path), frame)
                    # SF-APP1-PART3: Store portable package-relative path, not absolute filesystem path
                    scene.frame_path = f"frames/scene_src_{scene.source_id:04d}.png"
                    scene.png_exported = True
                    print(f"[EXPORT PNG] Scene {scene.source_id}: {out_path}")
                else:
                    print(f"[EXPORT PNG] Scene {scene.source_id}: Failed to read frame")

                pct = int((i + 1) / len(self._scenes) * 100)
                self.progress_updated.emit(pct)

            cap.release()
            self.progress_updated.emit(100)
            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))


class ExportPackageWorker(QThread):
    """SF-8E: Clean package export for runtime state after CUT."""
    finished = Signal()
    error = Signal(str)
    stage_changed = Signal(str)
    progress_updated = Signal(int)

    def __init__(self, scenes, metadata, subtitles, audio_regions,
                 output_base: str, video_name: str,
                 intro_cut: bool, outro_cut: bool):
        super().__init__()
        self._scenes = scenes
        self._metadata = metadata
        self._subtitles = subtitles
        self._audio_regions = audio_regions
        self._output_base = output_base
        self._video_name = video_name
        self._intro_cut = intro_cut
        self._outro_cut = outro_cut

    def run(self) -> None:
        try:
            self._do_export()
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

    def _do_export(self) -> None:
        """Create layered package structure:
        
        output/<video_name>/
        ├── packages/
        │   ├── runtime_timeline.json   # Active scenes only (App2 semantic)
        │   ├── runtime_manifest.json  # Minimal runtime metadata
        │   └── frames/                 # Active scene frames
        └── source/
            ├── source_master_timeline.json  # ALL source scenes (reconstruction)
            ├── source_subtitles.json        # Full subtitle timeline
            └── source_reconstruction_map.json # Reconstruction graph (App3)
        """
        import shutil
        import os

        base_dir = os.path.join(self._output_base, self._video_name)
        pkg_dir = os.path.join(base_dir, "packages")
        src_dir = os.path.join(base_dir, "source")
        frames_dir = os.path.join(pkg_dir, "frames")

        # Remove old structure if exists
        self.stage_changed.emit("Removing old package")
        if os.path.exists(pkg_dir):
            shutil.rmtree(pkg_dir)
        if os.path.exists(src_dir):
            shutil.rmtree(src_dir)

        # Create directories
        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(src_dir, exist_ok=True)

        self.stage_changed.emit("Creating package")
        fps = self._metadata.real_fps
        scenes = self._scenes

        # Separate active vs filtered scenes
        active_scenes = [s for s in scenes if not s.filtered]
        filtered_scenes = [s for s in scenes if s.filtered]
        total_source_scenes = len(self._scenes)

        # Copy frame PNGs for active scenes only
        self.stage_changed.emit("Exporting frames")
        source_frames_dir = os.path.join(base_dir, "frames")
        for scene in active_scenes:
            src_png = os.path.join(source_frames_dir, f"scene_src_{scene.source_id:04d}.png")
            dst_png = os.path.join(frames_dir, f"scene_src_{scene.source_id:04d}.png")
            if os.path.exists(src_png):
                shutil.copy2(src_png, dst_png)

        # ========================================================================
        # PART 1+2: RUNTIME TIMELINE (packages/runtime_timeline.json)
        # Active scenes ONLY for App2 semantic analysis
        # ========================================================================
        self.stage_changed.emit("Exporting runtime timeline")
        runtime_timeline_data = []
        for runtime_idx, scene in enumerate(active_scenes, start=1):
            s_start = scene.start_sec(fps)
            s_end = scene.end_sec(fps)
            frame_path = f"frames/scene_src_{scene.source_id:04d}.png"
            has_frame = os.path.exists(os.path.join(frames_dir, f"scene_src_{scene.source_id:04d}.png"))
            runtime_timeline_data.append({
                "runtime_scene_index": runtime_idx,
                "source_scene_id": scene.source_id,
                "start_sec": round(s_start, 3),
                "end_sec": round(s_end, 3),
                "duration": round(s_end - s_start, 3),
                "frame_path": frame_path if has_frame else None,
                "subtitle_count": len([s for s in self._subtitles
                    if s_start <= s.start <= s_end or s_start <= s.end <= s_end]),
            })

        runtime_timeline_path = os.path.join(pkg_dir, "runtime_timeline.json")
        with open(runtime_timeline_path, "w", encoding="utf-8") as f:
            json.dump({"scenes": runtime_timeline_data}, f, indent=2)

        # ========================================================================
        # RUNTIME SUBTITLES (packages/runtime_subtitles.json)
        # App2 semantic analysis: subtitle intersections for ACTIVE scenes only
        # Immutable scene_src_XXXX naming preserved
        # ========================================================================
        self.stage_changed.emit("Exporting runtime subtitles")
        runtime_subtitles_data = []
        for scene in active_scenes:
            s_start = scene.start_sec(fps)
            s_end = scene.end_sec(fps)
            # Find subtitle intersections for this scene
            scene_subtitles = []
            for sub in self._subtitles:
                # Subtitle intersects scene if:
                # - sub.start is within scene bounds, OR
                # - sub.end is within scene bounds, OR
                # - sub spans entire scene
                if (s_start <= sub.start <= s_end or
                    s_start <= sub.end <= s_end or
                    (sub.start <= s_start and sub.end >= s_end)):
                    scene_subtitles.append({
                        "start": round(sub.start, 3),
                        "end": round(sub.end, 3),
                        "text": sub.text,
                    })
            if scene_subtitles:
                runtime_subtitles_data.append({
                    "scene_id": f"scene_src_{scene.source_id:04d}",
                    "subtitles": scene_subtitles,
                })

        if runtime_subtitles_data:
            runtime_subs_path = os.path.join(pkg_dir, "runtime_subtitles.json")
            with open(runtime_subs_path, "w", encoding="utf-8") as f:
                json.dump({"scenes": runtime_subtitles_data}, f, indent=2, ensure_ascii=False)
            print(f"[EXPORT] Runtime subtitles: {len(runtime_subtitles_data)} scenes with subtitles")
        else:
            print("[EXPORT] No runtime subtitles to export")

        # ========================================================================
        # RUNTIME AUDIO REGIONS (packages/runtime_audio_regions.json)
        # App2 semantic analysis: audio intersections for ACTIVE scenes only
        # Immutable scene_src_XXXX naming preserved
        # ========================================================================
        self.stage_changed.emit("Exporting runtime audio regions")
        runtime_audio_data = []
        for scene in active_scenes:
            s_start = scene.start_sec(fps)
            s_end = scene.end_sec(fps)
            # Find audio region intersections for this scene
            scene_audio_regions = []
            for region in self._audio_regions:
                # Region intersects scene if:
                # - region.start is within scene bounds, OR
                # - region.end is within scene bounds, OR
                # - region spans entire scene
                if (s_start <= region.start <= s_end or
                    s_start <= region.end <= s_end or
                    (region.start <= s_start and region.end >= s_end)):
                    scene_audio_regions.append({
                        "start": round(region.start, 3),
                        "end": round(region.end, 3),
                        "type": region.type,
                        "energy": round(region.energy, 3),
                    })
            if scene_audio_regions:
                runtime_audio_data.append({
                    "scene_id": f"scene_src_{scene.source_id:04d}",
                    "audio_regions": scene_audio_regions,
                })

        if runtime_audio_data:
            runtime_audio_path = os.path.join(pkg_dir, "runtime_audio_regions.json")
            with open(runtime_audio_path, "w", encoding="utf-8") as f:
                json.dump({"scenes": runtime_audio_data}, f, indent=2)
            print(f"[EXPORT] Runtime audio regions: {len(runtime_audio_data)} scenes with audio")
        else:
            print("[EXPORT] No runtime audio regions to export - skipping runtime_audio_regions.json")

        # ========================================================================
        # PART 3: SOURCE MASTER TIMELINE (source/source_master_timeline.json)
        # ALL source scenes with full continuity for App3 reconstruction
        # ========================================================================
        self.stage_changed.emit("Exporting source master timeline")
        source_master_data = []
        for scene in scenes:
            s_start = scene.start_sec(fps)
            s_end = scene.end_sec(fps)
            # Find runtime index for active scenes
            runtime_idx = None
            if not scene.filtered:
                for idx, active_scene in enumerate(active_scenes, start=1):
                    if active_scene.source_id == scene.source_id:
                        runtime_idx = idx
                        break
            source_master_data.append({
                "source_scene_id": scene.source_id,
                "source_start_frame": scene.start_frame,
                "source_end_frame": scene.end_frame,
                "start_sec": round(s_start, 3),
                "end_sec": round(s_end, 3),
                "duration": round(s_end - s_start, 3),
                "filtered": scene.filtered,
                "filtered_reason": scene.filtered_reason,
                "is_runtime_active": not scene.filtered,
                "runtime_scene_index": runtime_idx,
                "frame_path": f"frames/scene_src_{scene.source_id:04d}.png" if not scene.filtered else None,
            })

        source_master_path = os.path.join(src_dir, "source_master_timeline.json")
        with open(source_master_path, "w", encoding="utf-8") as f:
            json.dump({"scenes": source_master_data}, f, indent=2)

        # ========================================================================
        # PART 5: SOURCE SUBTITLES (source/source_subtitles.json)
        # Full original subtitle timeline - DO NOT runtime filter
        # ========================================================================
        self.stage_changed.emit("Exporting source subtitles")
        source_subtitles_data = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in self._subtitles
        ]
        source_subs_path = os.path.join(src_dir, "source_subtitles.json")
        with open(source_subs_path, "w", encoding="utf-8") as f:
            json.dump({"subtitles": source_subtitles_data}, f, indent=2)

        # ========================================================================
        # PART 6: SOURCE AUDIO REGIONS (source/source_audio_regions.json)
        # Only create if audio regions actually exist
        # ========================================================================
        self.stage_changed.emit("Exporting source audio")
        source_audio_data = [
            {
                "start": round(r.start, 3),
                "end": round(r.end, 3),
                "type": r.type,
                "energy": r.energy,
            }
            for r in self._audio_regions
        ]
        if source_audio_data:
            # Only export if audio regions exist
            audio_path = os.path.join(src_dir, "source_audio_regions.json")
            with open(audio_path, "w", encoding="utf-8") as f:
                json.dump({"audio_regions": source_audio_data}, f, indent=2)
            print(f"[EXPORT] Audio regions: {len(source_audio_data)} source regions exported")
        else:
            print("[EXPORT] No audio regions to export - skipping source_audio_regions.json")

        # ========================================================================
        # PART 7: SOURCE RECONSTRUCTION MAP (source/source_reconstruction_map.json)
        # Reconstruction graph data for App3
        # ========================================================================
        self.stage_changed.emit("Exporting reconstruction map")
        reconstruction_map = {
            "video_name": self._video_name,
            "video_fps": fps,
            "video_duration": self._metadata.duration,
            "source_frames_dir": source_frames_dir,
            "intro_cut": self._intro_cut,
            "outro_cut": self._outro_cut,
            "total_source_scenes": total_source_scenes,
            "active_scene_count": len(active_scenes),
            "filtered_scene_count": len(filtered_scenes),
            "all_source_ids": [s.source_id for s in self._scenes],
            "active_source_ids": [s.source_id for s in active_scenes],
            "filtered_source_ids": [s.source_id for s in filtered_scenes],
            "filtered_details": [
                {
                    "source_id": s.source_id,
                    "reason": s.filtered_reason,
                    "original_start_sec": round(s.start_sec(fps), 3),
                    "original_end_sec": round(s.end_sec(fps), 3),
                }
                for s in filtered_scenes
            ],
        }
        reconstruction_map_path = os.path.join(src_dir, "source_reconstruction_map.json")
        with open(reconstruction_map_path, "w", encoding="utf-8") as f:
            json.dump(reconstruction_map, f, indent=2, ensure_ascii=False)

        # ========================================================================
        # PART 7: CLEANED RUNTIME MANIFEST (packages/runtime_manifest.json)
        # Minimal runtime data - NO reconstruction graph
        # ========================================================================
        self.stage_changed.emit("Writing runtime manifest")
        manifest = {
            "runtime_version": "SF-LAYERED-ARCHITECTURE",
            "package_version": "3.0",
            "source_scene_count": total_source_scenes,
            "filtered_scene_count": len(filtered_scenes),
            "exported_scene_count": len(active_scenes),
            "intro_cut": self._intro_cut,
            "outro_cut": self._outro_cut,
            "has_audio": len(source_audio_data) > 0,
            "has_subtitles": len(source_subtitles_data) > 0,
            "video_name": self._video_name,
            "video_fps": fps,
            "video_duration": self._metadata.duration,
        }
        manifest_path = os.path.join(pkg_dir, "runtime_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        self.stage_changed.emit("Export complete")


# =============================================================================
# Audio Analysis Worker
# =============================================================================

def extract_audio_ffmpeg(video_path: str, audio_path: str) -> bool:
    """Extract mono 16kHz WAV audio from video using ffmpeg."""
    try:
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"[AUDIO] ffmpeg error: {result.stderr[:200]}")
            return False
        print(f"[AUDIO] Extracted to {audio_path}")
        return True
    except Exception as e:
        print(f"[AUDIO] ffmpeg exception: {e}")
        return False


def analyze_audio_regions(audio_path: str, duration: float) -> list[AudioRegion]:
    """Analyze audio file and return classified regions.
    
    Detects: silence, speech-heavy, music-heavy, high-energy, music_speech.
    Uses librosa RMS energy + spectral contrast, no AI models.
    """
    try:
        import numpy as np
        import librosa
    except ImportError:
        print("[AUDIO] librosa not available")
        return []

    try:
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
    except Exception as e:
        print(f"[AUDIO] librosa load error: {e}")
        return []

    if len(y) == 0:
        return []

    # Window size: 0.5 seconds
    win_length = int(sr * 0.5)  # 8000 samples at 16kHz
    hop_length = win_length // 2

    # Compute RMS energy per window
    rms = librosa.feature.rms(y=y, frame_length=win_length, hop_length=hop_length)[0]

    # Compute spectral contrast (music vs speech indicator)
    try:
        contrast = librosa.feature.spectral_contrast(
            y=y, sr=sr, n_bands=4, fmin=200.0,
            hop_length=hop_length, win_length=win_length
        )
        # Mean contrast across bands - higher = more music-like
        contrast_mean = np.mean(contrast, axis=0)
    except Exception:
        contrast_mean = np.full_like(rms, 0.5)

    # Compute spectral centroid (higher = more speech/noise-like)
    try:
        centroid = librosa.feature.spectral_centroid(
            y=y, sr=sr, hop_length=hop_length, win_length=win_length
        )[0]
        centroid_norm = centroid / 8000.0  # normalize to 0-1
    except Exception:
        centroid_norm = np.full_like(rms, 0.5)

    # Normalize RMS to 0-1
    rms_max = np.max(rms) if np.max(rms) > 0 else 1.0
    rms_norm = rms / rms_max

    # Silence threshold
    silence_threshold = 0.02  # RMS below this = silence
    high_energy_threshold = 0.6  # RMS above this = high energy

    # Classify each window
    regions: list[AudioRegion] = []
    n_frames = len(rms)
    current_type = ""
    current_start = 0.0
    current_energy = 0.0
    energy_sum = 0.0
    count = 0

    # Track energy peaks for music_speech detection
    speech_energy_accum = 0.0
    music_energy_accum = 0.0
    speech_count = 0
    music_count = 0
    detection_window = 20  # frames (~5 seconds)

    for i in range(n_frames):
        t_start = i * hop_length / sr
        t_end = min((i + 1) * hop_length / sr, duration)
        energy = float(rms_norm[i])

        # Determine base type
        if energy < silence_threshold:
            base_type = "silence"
        elif energy > high_energy_threshold:
            base_type = "high_energy"
        elif contrast_mean[i] > 15.0 and centroid_norm[i] < 0.3:
            base_type = "music"
        elif contrast_mean[i] > 10.0:
            base_type = "music"
        elif centroid_norm[i] > 0.4 and energy > 0.05:
            base_type = "speech"
        else:
            base_type = "music" if contrast_mean[i] > 5.0 else "speech"

        # Track rolling window for music_speech detection
        if base_type == "speech" and energy > 0.05:
            speech_energy_accum += energy
            speech_count += 1
        if base_type == "music" and energy > 0.05:
            music_energy_accum += energy
            music_count += 1

        # Reset accumulators periodically
        if i % detection_window == 0 and i > 0:
            # Rule: if speech and strong music coexist, classify as music_speech
            if speech_count > 3 and music_count > 3 and \
               (speech_energy_accum / max(speech_count, 1)) > 0.04 and \
               (music_energy_accum / max(music_count, 1)) > 0.04:
                base_type = "music_speech"
            speech_energy_accum = 0.0
            music_energy_accum = 0.0
            speech_count = 0
            music_count = 0

        rtype = base_type

        if rtype != current_type:
            # Emit previous region if it had reasonable duration (> 0.5s)
            if current_type and count > 0:
                avg_energy = energy_sum / count
                regions.append(AudioRegion(
                    start=round(current_start, 3),
                    end=round(t_start, 3),
                    type=current_type,
                    energy=round(min(avg_energy, 1.0), 3),
                ))
            current_type = rtype
            current_start = t_start
            energy_sum = 0.0
            count = 0

        energy_sum += energy
        count += 1

    # Emit last region
    if current_type and count > 0:
        avg_energy = energy_sum / count
        regions.append(AudioRegion(
            start=round(current_start, 3),
            end=round(duration, 3),
            type=current_type,
            energy=round(min(avg_energy, 1.0), 3),
        ))

    # Merge adjacent same-type regions
    if len(regions) > 1:
        merged: list[AudioRegion] = []
        current = regions[0]
        for r in regions[1:]:
            if r.type == current.type:
                current = AudioRegion(
                    start=current.start,
                    end=r.end,
                    type=current.type,
                    energy=max(current.energy, r.energy),
                )
            else:
                merged.append(current)
                current = r
        merged.append(current)
        regions = merged

    print(f"[AUDIO] Analyzed: {len(regions)} regions")
    return regions


def export_audio_regions(regions: list[AudioRegion], output_dir: str, video_name: str) -> None:
    """Export audio regions JSON to output/audio/"""
    out_dir = Path(output_dir) / "audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    data = [
        {
            "start": r.start,
            "end": r.end,
            "type": r.type,
            "energy": r.energy,
        }
        for r in regions
    ]

    out_path = out_dir / "source_audio_regions.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[AUDIO] Exported {out_path}")


class AudioAnalysisWorker(QThread):
    """Extract audio, analyze regions, return results."""
    finished = Signal(list)
    error = Signal(str)
    stage_changed = Signal(str)
    progress_updated = Signal(int)

    def __init__(self, video_path: str, duration: float):
        super().__init__()
        self._video_path = video_path
        self._duration = duration

    def run(self):
        try:
            self.stage_changed.emit("extracting audio")
            self.progress_updated.emit(10)

            audio_path = Path("temp") / "audio.wav"
            if not extract_audio_ffmpeg(self._video_path, str(audio_path)):
                self.error.emit("Audio extraction failed")
                return

            self.stage_changed.emit("analyzing audio regions")
            self.progress_updated.emit(50)

            if not audio_path.exists():
                self.error.emit("Audio file not found")
                return

            regions = analyze_audio_regions(str(audio_path), self._duration)

            self.progress_updated.emit(100)
            self.finished.emit(regions)

        except Exception as e:
            self.error.emit(f"Audio analysis error: {e}")


# =============================================================================
# SceneBlock Widget
# =============================================================================

class SceneBlock(QWidget):
    clicked = Signal(int)

    def __init__(self, scene: Scene, fps: float, parent=None):
        super().__init__(parent)
        self._scene = scene
        self._fps = fps
        self._audio_regions: list[AudioRegion] = []
        self._is_playing: bool = False
        # SF-6C: Profile suggestion highlights
        self._suggested_intro: bool = False
        self._suggested_outro: bool = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(100, 110)
        self.setStyleSheet(
            "background-color: #2a2a2a; border: 1px solid #444; border-radius: 4px;"
        )

    def mousePressEvent(self, event):
        self.clicked.emit(self._scene.index)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet(
                "background-color: #3a3a3a; border: 2px solid #6cf; border-radius: 4px;"
            )
        else:
            self.setStyleSheet(
                "background-color: #2a2a2a; border: 1px solid #444; border-radius: 4px;"
            )

    def set_playing(self, playing: bool) -> None:
        self._is_playing = playing
        if playing:
            self.setStyleSheet(
                "background-color: #2a4a2a; border: 2px solid #4f4; border-radius: 4px;"
            )
        else:
            self.setStyleSheet(
                "background-color: #2a2a2a; border: 1px solid #444; border-radius: 4px;"
            )

    def set_audio_regions(self, regions: list[AudioRegion]) -> None:
        self._audio_regions = regions
        self.update()

    def set_suggested_intro(self, suggested: bool) -> None:
        """Set intro suggestion highlight state."""
        self._suggested_intro = suggested
        self.update()

    def set_suggested_outro(self, suggested: bool) -> None:
        """Set outro suggestion highlight state."""
        self._suggested_outro = suggested
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            painter.setPen(Qt.white)
            painter.setFont(QFont("Segoe UI", 9))

            thumb_rect = self.rect().adjusted(4, 4, -4, -38)
            if self._scene.thumbnail:
                scaled = self._scene.thumbnail.scaled(
                    thumb_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                x = (thumb_rect.width() - scaled.width()) // 2
                painter.drawPixmap(thumb_rect.topLeft() + QPoint(x, 0), scaled)
            else:
                painter.setBrush(Qt.darkGray)
                painter.drawRect(thumb_rect)

            painter.setPen(Qt.white)
            painter.setFont(QFont("Segoe UI", 8))
            s = self._scene
            painter.drawText(4, 93, f"#{s.index}  {s.start_sec(self._fps):.1f}s")
            painter.setPen(Qt.gray)
            painter.drawText(4, 105, f"-> {s.end_sec(self._fps):.1f}s  {s.duration_str(self._fps)}")

            # --- Audio type indicator bar ---
            if self._audio_regions:
                bar_rect = thumb_rect.adjusted(0, thumb_rect.height() - 4, 0, 0)
                bar_rect.setHeight(4)
                for r in self._audio_regions:
                    r_start = max(r.start, self._scene.start_sec(self._fps))
                    r_end = min(r.end, self._scene.end_sec(self._fps))
                    if r_end <= r_start:
                        continue
                    rel_start = (r_start - self._scene.start_sec(self._fps)) / max(self._scene.duration_sec(self._fps), 0.001)
                    rel_end = (r_end - self._scene.start_sec(self._fps)) / max(self._scene.duration_sec(self._fps), 0.001)
                    x1 = int(bar_rect.left() + rel_start * bar_rect.width())
                    x2 = int(bar_rect.left() + rel_end * bar_rect.width())
                    if r.type == "silence":
                        c = QColor("#555555")
                    elif r.type == "speech":
                        c = QColor("#4488ff")
                    elif r.type == "music":
                        c = QColor("#44cc44")
                    elif r.type == "high_energy":
                        c = QColor("#ff4444")
                    elif r.type == "music_speech":
                        c = QColor("#cc44cc")
                    else:
                        c = QColor("#888888")
                    painter.fillRect(x1, bar_rect.top(), x2 - x1, bar_rect.height(), c)

            # --- Subtitle count badge ---
            if self._scene.subtitles:
                painter.setPen(QColor("#ffcc00"))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(self.width() - 20, 10, f"S{len(self._scene.subtitles)}")

            # --- Profile suggestion highlight overlays ---
            if self._suggested_intro:
                # Draw intro suggestion highlight: golden border
                painter.setPen(QPen(QColor("#cc6"), 3))
                painter.drawRect(1, 1, self.width() - 3, self.height() - 3)
                painter.setFont(QFont("Segoe UI", 7))
                painter.setPen(QColor("#cc6"))
                painter.drawText(4, 15, "INTRO")
            elif self._suggested_outro:
                # Draw outro suggestion highlight: magenta border
                painter.setPen(QPen(QColor("#c6c"), 3))
                painter.drawRect(1, 1, self.width() - 3, self.height() - 3)
                painter.setFont(QFont("Segoe UI", 7))
                painter.setPen(QColor("#c6c"))
                painter.drawText(4, 15, "OUTRO")

            # --- Export status badges ---
            y_offset = 20
            if self._scene.png_exported:
                painter.setPen(QColor("#4f4"))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(self.width() - 20, y_offset, "PNG")
                y_offset += 10
            if self._scene.metadata_exported:
                painter.setPen(QColor("#ffcc00"))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(self.width() - 20, y_offset, "META")
                y_offset += 10
            if self._scene.mp4_exported:
                painter.setPen(QColor("#ff8844"))
                painter.setFont(QFont("Segoe UI", 7))
                painter.drawText(self.width() - 20, y_offset, "MP4")
        finally:
            painter.end()


# =============================================================================
# Playhead Overlay Widget
# =============================================================================

class PlayheadOverlay(QWidget):
    """A vertical line that tracks playback position on the timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._position_ratio: float = 0.0  # 0.0 to 1.0
        self.setFixedWidth(3)
        self.setStyleSheet("background-color: #ff4444;")

    def set_position_ratio(self, ratio: float) -> None:
        self._position_ratio = max(0.0, min(1.0, ratio))

    def position_ratio(self) -> float:
        return self._position_ratio


# =============================================================================
# LogPanel Widget
# =============================================================================

class LogPanel(QWidget):
    """Internal runtime log panel with color-coded sections."""

    COLORS = {
        "SCENE": "#6cf",
        "AUDIO": "#f8a",
        "EXPORT": "#8f8",
        "PLAYBACK": "#ff8",
        "SUBTITLE": "#fca",
        "PROFILE": "#cc6",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(80)
        self.setMaximumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        # Tab bar
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(2)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        self._tab_buttons: dict[str, QPushButton] = {}
        self._active_tab = "SCENE"

        for section in ["SCENE", "AUDIO", "EXPORT", "PLAYBACK", "PROFILE"]:
            btn = QPushButton(f"[{section}]")
            btn.setFixedHeight(20)
            btn.setCheckable(True)
            btn.setChecked(section == self._active_tab)
            btn.setStyleSheet(self._tab_style(section == self._active_tab))
            btn.clicked.connect(lambda checked, s=section: self._switch_tab(s))
            tab_layout.addWidget(btn)
            self._tab_buttons[section] = btn

        tab_layout.addStretch()
        layout.addLayout(tab_layout)

        # Log display
        self._log_display = QPlainTextEdit()
        self._log_display.setReadOnly(True)
        self._log_display.setMaximumBlockCount(200)
        self._log_display.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d0d0d;
                color: #aaa;
                border: 1px solid #333;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 8pt;
                padding: 2px;
            }
        """)
        layout.addWidget(self._log_display, stretch=1)

        self._all_logs: list[tuple[str, str]] = []  # (section, message)

    def _tab_style(self, active: bool) -> str:
        if active:
            return """
                QPushButton {
                    background-color: #333;
                    color: #fff;
                    border: 1px solid #555;
                    font-weight: bold;
                    font-size: 8pt;
                    padding: 0 6px;
                }
            """
        return """
            QPushButton {
                background-color: #1a1a1a;
                color: #666;
                border: 1px solid #333;
                font-size: 8pt;
                padding: 0 6px;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
                color: #888;
            }
        """

    def _switch_tab(self, section: str) -> None:
        self._active_tab = section
        for s, btn in self._tab_buttons.items():
            btn.setChecked(s == section)
            btn.setStyleSheet(self._tab_style(s == section))
        self._refresh_display()

    def _refresh_display(self) -> None:
        self._log_display.clear()
        html_parts = []
        for section, msg in self._all_logs:
            if section == self._active_tab:
                color = self.COLORS.get(section, "#aaa")
                html_parts.append(f"<span style='color:{color};'>[{section}]</span> {msg}<br>")
        self._log_display.appendHtml("".join(html_parts))

    def log(self, section: str, message: str) -> None:
        self._all_logs.append((section, message))
        if section == self._active_tab:
            color = self.COLORS.get(section, "#aaa")
            self._log_display.appendHtml(f"<span style='color:{color};'>[{section}]</span> {message}<br>")
            # Auto-scroll to bottom
            scrollbar = self._log_display.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())


# =============================================================================
# AudioTimeline Strip Widget
# =============================================================================

class AudioTimelineStrip(QWidget):
    """Visual audio region strip aligned with the scene timeline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._regions: list[AudioRegion] = []
        self._duration: float = 1.0
        self._current_time: float = 0.0
        self.setMinimumHeight(20)
        self.setMaximumHeight(24)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_regions(self, regions: list[AudioRegion], duration: float) -> None:
        self._regions = regions
        self._duration = duration if duration > 0 else 1.0
        self.update()

    def set_current_time(self, t: float) -> None:
        self._current_time = t
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        try:
            w = self.width()
            h = self.height()
            mid_y = h // 2

            # Background
            painter.fillRect(0, 0, w, h, QColor("#1a1a1a"))

            if not self._regions:
                painter.setPen(QColor("#444"))
                painter.drawText(4, mid_y + 4, "No audio regions")
                return

            # Draw each region as a colored bar
            for r in self._regions:
                x1 = int((r.start / self._duration) * w)
                x2 = int((r.end / self._duration) * w)
                if x2 <= x1:
                    continue

                if r.type == "silence":
                    c = QColor("#333333")
                elif r.type == "speech":
                    c = QColor("#4488ff")
                    alpha = min(255, int(80 + r.energy * 175))
                    c.setAlpha(alpha)
                elif r.type == "music":
                    c = QColor("#44cc44")
                    alpha = min(255, int(100 + r.energy * 155))
                    c.setAlpha(alpha)
                elif r.type == "high_energy":
                    c = QColor("#ff4444")
                elif r.type == "music_speech":
                    c = QColor("#cc44cc")
                    alpha = min(255, int(100 + r.energy * 155))
                    c.setAlpha(alpha)
                else:
                    c = QColor("#555555")

                painter.fillRect(x1, 0, x2 - x1, h, c)

            # Playhead position
            px = int((self._current_time / self._duration) * w)
            painter.setPen(QPen(QColor("#ff4444"), 2))
            painter.drawLine(px, 0, px, h)

            # Time ticks (every 10 seconds)
            painter.setPen(QColor("#555555"))
            tick_interval = 10.0
            t = 0.0
            while t <= self._duration:
                tx = int((t / self._duration) * w)
                painter.drawLine(tx, h - 4, tx, h)
                painter.setFont(QFont("Segoe UI", 6))
                painter.drawText(tx - 10, h - 5, f"{int(t)}s")
                t += tick_interval

        finally:
            painter.end()


# =============================================================================
# SceneFlow Main Window
# =============================================================================

class SceneFlow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SceneFlow - Unified Timeline Inspector")
        self.setMinimumSize(1100, 800)

        central = QWidget()
        self.setCentralWidget(central)

        # ── State ────────────────────────────────────────────────────────────
        self._current_path: str | None = None
        self._video_name: str = ""
        self._output_dir: str = "output"
        self._scenes: list[Scene] = []
        self._selected_index: int = 0
        self._worker: DetectWorker | None = None
        self._mp4_worker: ExportMP4Worker | None = None
        self._png_worker: ExportPNGWorker | None = None
        self._metadata: VideoMetadata | None = None
        self._encoder: str = "auto"
        # SF-8E: Runtime subtitle state (read from original, work with copy)
        self._original_subtitle_path: str = ""  # Path to original file (READ ONLY)
        self._runtime_subtitles: list[Subtitle] = []  # Runtime copy, never modify original
        self._runtime_subtitles_path: str = ""  # Path to runtime subtitle JSON
        self._original_subtitle_touched: bool = False  # Debug flag
        self._audio_regions: list[AudioRegion] = []
        self._audio_worker: AudioAnalysisWorker | None = None
        self._package_worker: ExportPackageWorker | None = None

        # ── SF-8E: CUT state ────────────────────────────────────────────────
        self._intro_cut_applied: bool = False
        self._outro_cut_applied: bool = False
        self._intro_cut_start: int | None = None
        self._intro_cut_end: int | None = None
        self._outro_cut_start: int | None = None
        self._outro_cut_end: int | None = None

        # ── SF-6A: Profile state ────────────────────────────────────────────
        self._intro_start_idx: int | None = None
        self._intro_end_idx: int | None = None
        self._outro_start_idx: int | None = None
        self._outro_end_idx: int | None = None
        self._loaded_intro_profile: SegmentProfile | None = None
        self._loaded_outro_profile: SegmentProfile | None = None
        self._profile_matched: bool = False
        self._profile_match_intro: tuple[int, int, float] | None = None
        self._profile_match_outro: tuple[int, int, float] | None = None

        # SF-6B: Toggle mode state
        self._selection_mode: tuple[str, str] | None = None

        # ── Root layout ──────────────────────────────────────────────────────
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── LEFT TOOL DOCK (fixed 280px) ──────────────────────────────────────
        tool_dock = QWidget()
        tool_dock.setFixedWidth(280)
        tool_dock.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        dock_layout = QVBoxLayout(tool_dock)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.setSpacing(6)

        # -- INPUT section --
        input_box = QGroupBox("INPUT")
        input_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #444; border-radius: 4px; margin-top: 4px; padding-top: 4px; padding-bottom: 2px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """)
        input_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        input_grid = QGridLayout(input_box)
        input_grid.setContentsMargins(6, 4, 6, 4)
        input_grid.setSpacing(4)

        self.select_btn = QPushButton("Select Video")
        self.select_btn.setFixedHeight(30)
        self.select_btn.setMinimumWidth(80)
        self.select_btn.setMaximumWidth(110)

        self.subtitle_btn = QPushButton("Load Subtitle")
        self.subtitle_btn.setEnabled(False)
        self.subtitle_btn.setFixedHeight(30)
        self.subtitle_btn.setMinimumWidth(80)
        self.subtitle_btn.setMaximumWidth(110)

        self.output_btn = QPushButton("Output Folder")
        self.output_btn.setFixedHeight(30)
        self.output_btn.setMinimumWidth(80)
        self.output_btn.setMaximumWidth(110)

        self.encoder_combo = QComboBox()
        for key, label in ENCODER_OPTIONS:
            self.encoder_combo.addItem(label, key)
        self.encoder_combo.setFixedHeight(28)
        self.encoder_combo.setStyleSheet("""
            QComboBox { background-color: #2a2a2a; color: #6cf; border: 1px solid #444; padding: 2px 4px; }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox::down-arrow { image: none; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #888; margin-right: 4px; }
        """)
        self.encoder_combo.currentIndexChanged.connect(self._on_encoder_changed)

        detected = detect_gpu_encoder()
        for i in range(self.encoder_combo.count()):
            if self.encoder_combo.itemData(i) == detected:
                self.encoder_combo.setCurrentIndex(i)
                break
        self._encoder = detected

        input_grid.addWidget(self.select_btn, 0, 0)
        input_grid.addWidget(self.subtitle_btn, 0, 1)
        input_grid.addWidget(self.output_btn, 0, 2)
        input_grid.addWidget(QLabel("Encoder:"), 1, 0)
        input_grid.addWidget(self.encoder_combo, 1, 1, 1, 2)

        self.subtitle_label = QLabel("No subtitle")
        self.subtitle_label.setStyleSheet("color: #888; font-size: 8pt;")
        input_grid.addWidget(self.subtitle_label, 2, 0, 1, 3)

        dock_layout.addWidget(input_box)

        # -- ANALYSIS section --
        analysis_box = QGroupBox("ANALYSIS")
        analysis_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #444; border-radius: 4px; margin-top: 4px; padding-top: 4px; padding-bottom: 2px; color: #6cf; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """)
        analysis_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        analysis_grid = QGridLayout(analysis_box)
        analysis_grid.setContentsMargins(6, 4, 6, 4)
        analysis_grid.setSpacing(4)

        self.detect_btn = QPushButton("Detect Scenes")
        self.detect_btn.setEnabled(False)
        self.detect_btn.setFixedHeight(32)
        self.detect_btn.setMinimumWidth(80)
        self.detect_btn.setMaximumWidth(110)

        self.analyze_audio_btn = QPushButton("Analyze Audio")
        self.analyze_audio_btn.setEnabled(False)
        self.analyze_audio_btn.setFixedHeight(32)
        self.analyze_audio_btn.setMinimumWidth(80)
        self.analyze_audio_btn.setMaximumWidth(110)

        self.scene_status_label = QLabel("SCENE DETECTION: Idle")
        self.scene_status_label.setStyleSheet("color: #aaa; font-size: 9pt;")
        self.scene_status_label.setWordWrap(True)

        self.audio_status_label = QLabel("AUDIO: Not started")
        self.audio_status_label.setStyleSheet("color: #aaa; font-size: 9pt;")
        self.audio_status_label.setWordWrap(True)

        # SF-6C: Find Intro/Outro buttons
        self.find_intro_btn = QPushButton("Find Intro")
        self.find_intro_btn.setEnabled(False)
        self.find_intro_btn.setFixedHeight(32)
        self.find_intro_btn.setMinimumWidth(80)
        self.find_intro_btn.setMaximumWidth(110)
        self.find_intro_btn.setStyleSheet("""
            QPushButton { background-color: #2d4d2d; color: #cc6; border: 1px solid #664400; padding: 2px 4px; font-size: 9pt; }
            QPushButton:hover { background-color: #3d6d3d; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; border-color: #444; }
        """)

        self.find_outro_btn = QPushButton("Find Outro")
        self.find_outro_btn.setEnabled(False)
        self.find_outro_btn.setFixedHeight(32)
        self.find_outro_btn.setMinimumWidth(80)
        self.find_outro_btn.setMaximumWidth(110)
        self.find_outro_btn.setStyleSheet("""
            QPushButton { background-color: #4d2d4d; color: #c6c; border: 1px solid #660066; padding: 2px 4px; font-size: 9pt; }
            QPushButton:hover { background-color: #6d3d6d; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; border-color: #444; }
        """)

        analysis_grid.addWidget(self.detect_btn, 0, 0)
        analysis_grid.addWidget(self.analyze_audio_btn, 0, 1)
        analysis_grid.addWidget(self.find_intro_btn, 0, 2)
        analysis_grid.addWidget(self.find_outro_btn, 0, 3)
        analysis_grid.addWidget(self.scene_status_label, 1, 0, 1, 4)
        analysis_grid.addWidget(self.audio_status_label, 2, 0, 1, 4)

        dock_layout.addWidget(analysis_box)

        # Backward compatibility aliases
        self.stage_label = self.scene_status_label
        self.progress_label = self.scene_status_label

        # -- PROFILE section (SF-8E: INTRO / OUTRO groups with CUT buttons) --
        profile_box = QGroupBox("PROFILE")
        profile_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 4px; margin-top: 4px; padding-top: 4px; padding-bottom: 2px; color: #cc6; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """)
        profile_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        profile_vbox = QVBoxLayout(profile_box)
        profile_vbox.setContentsMargins(6, 4, 6, 4)
        profile_vbox.setSpacing(3)

        # ── INTRO group ────────────────────────────────────────────────────
        intro_group = QGroupBox("INTRO")
        intro_group.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #665533; border-radius: 3px; margin-top: 3px; padding-top: 3px; color: #cc6; font-size: 8pt; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
        """)
        intro_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        intro_grid = QGridLayout(intro_group)
        intro_grid.setContentsMargins(4, 2, 4, 2)
        intro_grid.setSpacing(3)

        self.mark_intro_start_btn = QPushButton("Start")
        self.mark_intro_start_btn.setFixedHeight(26)
        self.mark_intro_start_btn.setMinimumWidth(56)
        self.mark_intro_start_btn.setCheckable(True)
        self.mark_intro_start_btn.setStyleSheet("""
            QPushButton { background-color: #3a3020; color: #cc6; border: 1px solid #664; padding: 2px 4px; font-size: 8pt; }
            QPushButton:hover { background-color: #4a4030; }
            QPushButton:checked { background-color: #665533; color: #ff8; border: 2px solid #cc6; }
        """)

        self.mark_intro_end_btn = QPushButton("End")
        self.mark_intro_end_btn.setFixedHeight(26)
        self.mark_intro_end_btn.setMinimumWidth(56)
        self.mark_intro_end_btn.setCheckable(True)
        self.mark_intro_end_btn.setStyleSheet("""
            QPushButton { background-color: #3a3020; color: #cc6; border: 1px solid #664; padding: 2px 4px; font-size: 8pt; }
            QPushButton:hover { background-color: #4a4030; }
            QPushButton:checked { background-color: #665533; color: #ff8; border: 2px solid #cc6; }
        """)

        self.load_intro_btn = QPushButton("Load")
        self.load_intro_btn.setFixedHeight(26)
        self.load_intro_btn.setMinimumWidth(56)
        self.load_intro_btn.setStyleSheet("""
            QPushButton { background-color: #2a3040; color: #8cf; border: 1px solid #446; padding: 2px 4px; font-size: 8pt; }
            QPushButton:hover { background-color: #3a4060; }
        """)

        self.save_intro_btn = QPushButton("Save")
        self.save_intro_btn.setFixedHeight(26)
        self.save_intro_btn.setMinimumWidth(56)
        self.save_intro_btn.setStyleSheet("""
            QPushButton { background-color: #2d4d2d; color: #8f8; border: 1px solid #5a8a5a; padding: 2px 4px; font-size: 8pt; font-weight: bold; }
            QPushButton:hover { background-color: #3d6d3d; }
        """)

        # SF-8E: INTRO CUT button
        self.cut_intro_btn = QPushButton("CUT")
        self.cut_intro_btn.setFixedHeight(28)
        self.cut_intro_btn.setMinimumWidth(56)
        self.cut_intro_btn.setEnabled(False)  # disabled until valid range
        self.cut_intro_btn.setStyleSheet("""
            QPushButton {
                background-color: #4d2020;
                color: #ff6666;
                border: 1px solid #8a3a3a;
                padding: 2px 4px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #6d3030; }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
                border-color: #444;
            }
        """)

        # Row 0: marking buttons, Row 1: load/save, Row 2: CUT
        intro_grid.addWidget(self.mark_intro_start_btn, 0, 0)
        intro_grid.addWidget(self.mark_intro_end_btn, 0, 1)
        intro_grid.addWidget(self.load_intro_btn, 1, 0)
        intro_grid.addWidget(self.save_intro_btn, 1, 1)
        intro_grid.addWidget(self.cut_intro_btn, 2, 0, 1, 2)

        self.intro_status_label = QLabel("")  # dynamic status
        self.intro_status_label.setStyleSheet("color: #888; font-size: 7pt;")
        intro_grid.addWidget(self.intro_status_label, 3, 0, 1, 2)

        profile_vbox.addWidget(intro_group)

        # ── OUTRO group ────────────────────────────────────────────────────
        outro_group = QGroupBox("OUTRO")
        outro_group.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #553355; border-radius: 3px; margin-top: 3px; padding-top: 3px; color: #c6c; font-size: 8pt; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
        """)
        outro_group.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        outro_grid = QGridLayout(outro_group)
        outro_grid.setContentsMargins(4, 2, 4, 2)
        outro_grid.setSpacing(3)

        self.mark_outro_start_btn = QPushButton("Start")
        self.mark_outro_start_btn.setFixedHeight(26)
        self.mark_outro_start_btn.setMinimumWidth(56)
        self.mark_outro_start_btn.setCheckable(True)
        self.mark_outro_start_btn.setStyleSheet("""
            QPushButton { background-color: #302030; color: #c6c; border: 1px solid #646; padding: 2px 4px; font-size: 8pt; }
            QPushButton:hover { background-color: #403040; }
            QPushButton:checked { background-color: #553355; color: #f8f; border: 2px solid #c6c; }
        """)

        self.mark_outro_end_btn = QPushButton("End")
        self.mark_outro_end_btn.setFixedHeight(26)
        self.mark_outro_end_btn.setMinimumWidth(56)
        self.mark_outro_end_btn.setCheckable(True)
        self.mark_outro_end_btn.setStyleSheet("""
            QPushButton { background-color: #302030; color: #c6c; border: 1px solid #646; padding: 2px 4px; font-size: 8pt; }
            QPushButton:hover { background-color: #403040; }
            QPushButton:checked { background-color: #553355; color: #f8f; border: 2px solid #c6c; }
        """)

        self.load_outro_btn = QPushButton("Load")
        self.load_outro_btn.setFixedHeight(26)
        self.load_outro_btn.setMinimumWidth(56)
        self.load_outro_btn.setStyleSheet("""
            QPushButton { background-color: #2a3040; color: #8cf; border: 1px solid #446; padding: 2px 4px; font-size: 8pt; }
            QPushButton:hover { background-color: #3a4060; }
        """)

        self.save_outro_btn = QPushButton("Save")
        self.save_outro_btn.setFixedHeight(26)
        self.save_outro_btn.setMinimumWidth(56)
        self.save_outro_btn.setStyleSheet("""
            QPushButton { background-color: #4d2d4d; color: #f8f; border: 1px solid #8a5a8a; padding: 2px 4px; font-size: 8pt; font-weight: bold; }
            QPushButton:hover { background-color: #6d3d6d; }
        """)

        # SF-8E: OUTRO CUT button
        self.cut_outro_btn = QPushButton("CUT")
        self.cut_outro_btn.setFixedHeight(28)
        self.cut_outro_btn.setMinimumWidth(56)
        self.cut_outro_btn.setEnabled(False)  # disabled until valid range
        self.cut_outro_btn.setStyleSheet("""
            QPushButton {
                background-color: #4d2020;
                color: #ff6666;
                border: 1px solid #8a3a3a;
                padding: 2px 4px;
                font-size: 8pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #6d3030; }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
                border-color: #444;
            }
        """)

        outro_grid.addWidget(self.mark_outro_start_btn, 0, 0)
        outro_grid.addWidget(self.mark_outro_end_btn, 0, 1)
        outro_grid.addWidget(self.load_outro_btn, 1, 0)
        outro_grid.addWidget(self.save_outro_btn, 1, 1)
        outro_grid.addWidget(self.cut_outro_btn, 2, 0, 1, 2)

        self.outro_status_label = QLabel("")  # dynamic status
        self.outro_status_label.setStyleSheet("color: #888; font-size: 7pt;")
        outro_grid.addWidget(self.outro_status_label, 3, 0, 1, 2)

        profile_vbox.addWidget(outro_group)

        # ── Shared match label below both groups ───────────────────────────
        self.profile_match_label = QLabel("")
        self.profile_match_label.setStyleSheet("color: #ffcc00; font-size: 8pt; font-weight: bold;")
        self.profile_match_label.setWordWrap(True)
        profile_vbox.addWidget(self.profile_match_label)

        dock_layout.addWidget(profile_box)

        # -- EXPORT ANALYSIS section --
        export_anal_box = QGroupBox("EXPORT ANALYSIS")
        export_anal_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #444; border-radius: 4px; margin-top: 4px; padding-top: 4px; padding-bottom: 2px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """)
        export_anal_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        export_anal_grid = QGridLayout(export_anal_box)
        export_anal_grid.setContentsMargins(6, 4, 6, 4)
        export_anal_grid.setSpacing(4)

        self.export_png_btn = QPushButton("Export PNG")
        self.export_png_btn.setEnabled(False)
        self.export_png_btn.setFixedHeight(30)
        self.export_png_btn.setMinimumWidth(75)
        self.export_png_btn.setMaximumWidth(100)

        self.export_json_btn = QPushButton("Export Meta")
        self.export_json_btn.setEnabled(False)
        self.export_json_btn.setFixedHeight(30)
        self.export_json_btn.setMinimumWidth(75)
        self.export_json_btn.setMaximumWidth(100)

        self.export_audio_btn = QPushButton("Export Audio")
        self.export_audio_btn.setEnabled(False)
        self.export_audio_btn.setFixedHeight(30)
        self.export_audio_btn.setMinimumWidth(75)
        self.export_audio_btn.setMaximumWidth(100)

        # SF-8E: Export Timeline Package button (clean version)
        self.export_package_btn = QPushButton("Export Timeline Package")
        self.export_package_btn.setEnabled(False)
        self.export_package_btn.setFixedHeight(30)
        self.export_package_btn.setMinimumWidth(100)
        self.export_package_btn.setMaximumWidth(130)
        self.export_package_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d4d2d;
                color: #8f8;
                border: 1px solid #5a8a5a;
                padding: 2px 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3d6d3d; }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
                border-color: #444;
            }
        """)

        export_anal_grid.addWidget(self.export_png_btn, 0, 0)
        export_anal_grid.addWidget(self.export_json_btn, 0, 1)
        export_anal_grid.addWidget(self.export_audio_btn, 0, 2)
        export_anal_grid.addWidget(self.export_package_btn, 1, 0, 1, 3)

        dock_layout.addWidget(export_anal_box)

        # -- FINAL EXPORT section --
        final_box = QGroupBox("FINAL EXPORT")
        final_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 4px; margin-top: 4px; padding-top: 4px; padding-bottom: 2px; color: #8f8; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """)
        final_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        final_layout = QVBoxLayout(final_box)
        final_layout.setContentsMargins(6, 4, 6, 4)
        final_layout.setSpacing(4)

        self.export_mp4_btn = QPushButton("Export MP4 Clips")
        self.export_mp4_btn.setEnabled(False)
        self.export_mp4_btn.setFixedHeight(32)
        self.export_mp4_btn.setMinimumWidth(120)
        self.export_mp4_btn.setMaximumWidth(160)
        self.export_mp4_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.export_mp4_btn.setStyleSheet("""
            QPushButton { background-color: #2d4d2d; color: #8f8; border: 1px solid #5a8a5a; padding: 4px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #3d6d3d; }
            QPushButton:disabled { background-color: #2a2a2a; color: #555; border-color: #444; }
        """)
        final_layout.addWidget(self.export_mp4_btn, alignment=Qt.AlignLeft)

        dock_layout.addWidget(final_box)

        # Add dock to root layout
        layout.addWidget(tool_dock)

        # ── Main content area ─────────────────────────────────────────────────
        main_content = QWidget()
        main_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout = QVBoxLayout(main_content)
        layout.addWidget(main_content, stretch=1)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Path label row
        self.path_label = QLabel("No video selected")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #888; font-size: 9pt;")
        main_layout.addWidget(self.path_label)

        # -- Video Metadata (now in main content area) --
        self.metadata_box = QGroupBox("Video Metadata")
        self.metadata_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #444; border-radius: 4px; margin-top: 6px; padding-top: 6px; padding-bottom: 2px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)
        self.metadata_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        meta_layout = QGridLayout(self.metadata_box)
        meta_layout.setContentsMargins(8, 4, 8, 4)
        meta_layout.setVerticalSpacing(2)
        meta_layout.setHorizontalSpacing(8)
        meta_layout.setColumnStretch(1, 1)
        meta_layout.setColumnStretch(3, 1)

        self.fps_label = QLabel("FPS: --")
        self.fps_label.setStyleSheet("color: #6cf;")
        self.res_label = QLabel("Resolution: --")
        self.res_label.setStyleSheet("color: #ccc;")
        meta_layout.addWidget(QLabel("FPS:"), 0, 0)
        meta_layout.addWidget(self.fps_label, 0, 1)
        meta_layout.addWidget(QLabel("Resolution:"), 0, 2)
        meta_layout.addWidget(self.res_label, 0, 3)

        self.frames_label = QLabel("Total Frames: --")
        self.frames_label.setStyleSheet("color: #ccc;")
        self.duration_meta_label = QLabel("Duration: --")
        self.duration_meta_label.setStyleSheet("color: #ccc;")
        meta_layout.addWidget(QLabel("Total Frames:"), 1, 0)
        meta_layout.addWidget(self.frames_label, 1, 1)
        meta_layout.addWidget(QLabel("Duration:"), 1, 2)
        meta_layout.addWidget(self.duration_meta_label, 1, 3)

        self.codec_label = QLabel("Codec: --")
        self.codec_label.setStyleSheet("color: #888;")
        meta_layout.addWidget(QLabel("Codec:"), 2, 0)
        meta_layout.addWidget(self.codec_label, 2, 1)
        main_layout.addWidget(self.metadata_box)

        # Output folder display (inline in main area)
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        self.output_label = QLabel("output/ (default)")
        self.output_label.setWordWrap(True)
        self.output_label.setStyleSheet("color: #888;")
        out_row.addWidget(QLabel("Output:"))
        out_row.addWidget(self.output_label, stretch=1)
        main_layout.addLayout(out_row)

        # ═════════════════════════════════════════════════════════════════════
        # SPLITTER: Preview area + Timeline band + Log panel
        # ═════════════════════════════════════════════════════════════════════
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setHandleWidth(4)
        main_splitter.setChildrenCollapsible(False)

        # ── Top half: Preview + Scene Info ────────────────────────────────────
        preview_wrapper = QWidget()
        preview_wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout = QHBoxLayout(preview_wrapper)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(8)

        # -- Preview area (left) --
        preview_container = QWidget()
        preview_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_container_layout = QVBoxLayout(preview_container)
        preview_container_layout.setContentsMargins(0, 0, 0, 0)
        preview_container_layout.setSpacing(4)

        # Video widget placeholder
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.video_widget.setMinimumSize(320, 180)
        self.video_widget.setStyleSheet("background-color: #000; border: 1px solid #333;")

        # Player setup - FIXED: AudioOutput before VideoOutput (preferred stable order)
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.audio_output.setVolume(1.0)  # Ensure volume > 0
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)

        # Playback controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(4)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(32, 24)
        self.play_btn.setToolTip("Play / Pause")
        self.play_btn.setEnabled(False)
        self.play_btn.setStyleSheet("""
            QPushButton { background-color: #2a4a2a; color: #8f8; border: 1px solid #5a8a5a; font-size: 11pt; }
            QPushButton:hover { background-color: #3d6d3d; }
            QPushButton:disabled { background-color: #1a1a1a; color: #444; border-color: #333; }
        """)

        self.stop_btn = QPushButton("⏹")
        self.stop_btn.setFixedSize(32, 24)
        self.stop_btn.setToolTip("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #4d2d2d; color: #f88; border: 1px solid #8a5a5a; font-size: 11pt; }
            QPushButton:hover { background-color: #6d3d3d; }
            QPushButton:disabled { background-color: #1a1a1a; color: #444; border-color: #333; }
        """)

        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setMinimumHeight(24)
        self.seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #333;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #6cf;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #6cf;
                border-radius: 3px;
            }
        """)

        self.time_label = QLabel("0:00.00 / 0:00.00")
        self.time_label.setStyleSheet("color: #aaa; font-size: 9pt; font-family: monospace;")
        self.time_label.setMinimumWidth(140)

        controls_layout.addWidget(self.play_btn)
        controls_layout.addWidget(self.stop_btn)
        controls_layout.addWidget(self.seek_slider, stretch=1)
        controls_layout.addWidget(self.time_label)

        preview_container_layout.addWidget(self.video_widget, stretch=1)
        preview_container_layout.addLayout(controls_layout)

        # Subtitle bar - uses runtime subtitle state
        self.subtitle_bar = QLabel("")
        self.subtitle_bar.setAlignment(Qt.AlignCenter)
        self.subtitle_bar.setMinimumHeight(32)
        self.subtitle_bar.setMaximumHeight(48)
        self.subtitle_bar.setWordWrap(True)
        self.subtitle_bar.setStyleSheet("""
            QLabel {
                background-color: #000000;
                color: #ffffcc;
                font-size: 11pt;
                font-family: 'Segoe UI', sans-serif;
                padding: 4px 12px;
                border: 1px solid #444;
                border-radius: 3px;
                margin-top: 2px;
            }
        """)
        preview_container_layout.addWidget(self.subtitle_bar)

        preview_layout.addWidget(preview_container, stretch=1)

        # -- Scene Info (right, fixed width) --
        self.scene_info_box = QGroupBox("Scene Info")
        self.scene_info_box.setMinimumWidth(280)
        self.scene_info_box.setMaximumWidth(320)
        self.scene_info_box.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.scene_info_box.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #444; border-radius: 4px; margin-top: 6px; padding-top: 6px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        """)
        info_layout = QVBoxLayout(self.scene_info_box)
        info_layout.setContentsMargins(6, 4, 6, 4)
        info_layout.setSpacing(4)

        # SCENE section
        scene_section = QGroupBox("SCENE")
        scene_section.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 3px; margin-top: 4px; padding-top: 4px; color: #6cf; font-size: 8pt; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
        """)
        scene_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        scene_section_layout = QVBoxLayout(scene_section)
        scene_section_layout.setContentsMargins(4, 2, 4, 2)
        scene_section_layout.setSpacing(1)
        self.scene_num_label = QLabel("Scene #--")
        self.scene_num_label.setStyleSheet("color: #fff; font-size: 10pt; font-weight: bold;")
        self.scene_start_label = QLabel("Start: --")
        self.scene_start_label.setStyleSheet("color: #ccc; font-size: 8pt;")
        self.scene_end_label = QLabel("End: --")
        self.scene_end_label.setStyleSheet("color: #ccc; font-size: 8pt;")
        self.scene_dur_label = QLabel("Duration: --")
        self.scene_dur_label.setStyleSheet("color: #ccc; font-size: 8pt;")
        scene_section_layout.addWidget(self.scene_num_label)
        scene_section_layout.addWidget(self.scene_start_label)
        scene_section_layout.addWidget(self.scene_end_label)
        scene_section_layout.addWidget(self.scene_dur_label)
        info_layout.addWidget(scene_section)

        # AUDIO section
        audio_section = QGroupBox("AUDIO")
        audio_section.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 3px; margin-top: 4px; padding-top: 4px; color: #f8a; font-size: 8pt; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
        """)
        audio_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        audio_section_layout = QVBoxLayout(audio_section)
        audio_section_layout.setContentsMargins(4, 2, 4, 2)
        audio_section_layout.setSpacing(1)
        self.scene_audio_type = QLabel("Dominant: --")
        self.scene_audio_type.setStyleSheet("color: #f8a; font-size: 9pt;")
        self.scene_audio_energy = QLabel("Avg energy: --")
        self.scene_audio_energy.setStyleSheet("color: #aaa; font-size: 8pt;")
        self.scene_audio_overlap = QLabel("Overlapping regions: --")
        self.scene_audio_overlap.setStyleSheet("color: #aaa; font-size: 8pt;")
        audio_section_layout.addWidget(self.scene_audio_type)
        audio_section_layout.addWidget(self.scene_audio_energy)
        audio_section_layout.addWidget(self.scene_audio_overlap)
        info_layout.addWidget(audio_section)

        # EXPORT STATUS section
        export_section = QGroupBox("EXPORT STATUS")
        export_section.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 3px; margin-top: 4px; padding-top: 4px; color: #8f8; font-size: 8pt; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 3px; }
        """)
        export_section.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        export_section_layout = QVBoxLayout(export_section)
        export_section_layout.setContentsMargins(4, 2, 4, 2)
        export_section_layout.setSpacing(1)
        self.export_png_status = QLabel("PNG: Not exported")
        self.export_png_status.setStyleSheet("color: #888; font-size: 8pt;")
        self.export_meta_status = QLabel("Metadata: Not exported")
        self.export_meta_status.setStyleSheet("color: #888; font-size: 8pt;")
        self.export_mp4_status = QLabel("MP4: Not exported")
        self.export_mp4_status.setStyleSheet("color: #888; font-size: 8pt;")
        export_section_layout.addWidget(self.export_png_status)
        export_section_layout.addWidget(self.export_meta_status)
        export_section_layout.addWidget(self.export_mp4_status)
        info_layout.addWidget(export_section)

        preview_layout.addWidget(self.scene_info_box)

        main_splitter.addWidget(preview_wrapper)

        # ── Middle section: Timeline + Audio strip ──────────────────────────
        timeline_container = QWidget()
        timeline_container.setMinimumHeight(180)
        timeline_container.setMaximumHeight(240)
        timeline_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        timeline_container_layout = QVBoxLayout(timeline_container)
        timeline_container_layout.setContentsMargins(0, 2, 0, 0)
        timeline_container_layout.setSpacing(2)

        # Timeline scroll
        timeline_scroll_wrapper = QWidget()
        timeline_scroll_wrapper.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        timeline_scroll_layout = QVBoxLayout(timeline_scroll_wrapper)
        timeline_scroll_layout.setContentsMargins(0, 0, 0, 0)
        timeline_scroll_layout.setSpacing(0)

        self.timeline_scroll = QScrollArea()
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setMinimumHeight(120)
        self.timeline_scroll.setMaximumHeight(140)
        self.timeline_scroll.setStyleSheet(
            "QScrollArea { background-color: #1a1a1a; border: none; }"
        )
        self.timeline_content = QWidget()
        self.timeline_layout = QHBoxLayout(self.timeline_content)
        self.timeline_layout.setSpacing(6)
        self.timeline_layout.setContentsMargins(4, 8, 4, 4)
        self.timeline_scroll.setWidget(self.timeline_content)

        timeline_scroll_layout.addWidget(self.timeline_scroll, stretch=1)

        # Playhead overlay
        self.playhead = PlayheadOverlay(self.timeline_scroll.viewport())
        self.playhead.hide()

        # Timeline label
        self.timeline_label = QLabel("No scenes")
        self.timeline_label.setStyleSheet("color: #666; font-size: 8pt;")
        timeline_scroll_layout.addWidget(self.timeline_label)

        timeline_container_layout.addWidget(timeline_scroll_wrapper, stretch=1)

        # Audio strip
        self.audio_timeline_strip = AudioTimelineStrip()
        timeline_container_layout.addWidget(self.audio_timeline_strip)

        main_splitter.addWidget(timeline_container)

        # ── Bottom: Log Panel ───────────────────────────────────────────────
        self.log_panel = LogPanel()
        main_splitter.addWidget(self.log_panel)

        # Set initial splitter sizes
        main_splitter.setSizes([400, 180, 100])

        main_layout.addWidget(main_splitter, stretch=1)

        # ── Connect signals ─────────────────────────────────────────────────
        self.select_btn.clicked.connect(self._on_select_video)
        self.subtitle_btn.clicked.connect(self._on_load_subtitle)
        self.output_btn.clicked.connect(self._on_select_output)
        self.detect_btn.clicked.connect(self._on_detect_scenes)
        self.export_mp4_btn.clicked.connect(self._on_export_mp4)
        self.export_png_btn.clicked.connect(self._on_export_png)
        self.export_json_btn.clicked.connect(self._on_export_json)
        self.export_audio_btn.clicked.connect(self._on_export_audio)
        self.analyze_audio_btn.clicked.connect(self._on_analyze_audio)
        self.export_package_btn.clicked.connect(self._on_export_package)

        # ── SF-6B: Profile button connections (toggle mode + load) ──────────
        self.mark_intro_start_btn.clicked.connect(lambda: self._on_toggle_selection_mode("intro", "start"))
        self.mark_intro_end_btn.clicked.connect(lambda: self._on_toggle_selection_mode("intro", "end"))
        self.load_intro_btn.clicked.connect(lambda: self._on_load_profile("intro"))
        self.save_intro_btn.clicked.connect(lambda: self._on_save_profile("intro"))
        self.mark_outro_start_btn.clicked.connect(lambda: self._on_toggle_selection_mode("outro", "start"))
        self.mark_outro_end_btn.clicked.connect(lambda: self._on_toggle_selection_mode("outro", "end"))
        self.load_outro_btn.clicked.connect(lambda: self._on_load_profile("outro"))
        self.save_outro_btn.clicked.connect(lambda: self._on_save_profile("outro"))

        # ── SF-8E: CUT button connections ──────────────────────────────────
        self.cut_intro_btn.clicked.connect(self._on_cut_intro)
        self.cut_outro_btn.clicked.connect(self._on_cut_outro)

        # SF-6C: Profile suggestion highlight state
        self._highlighted_intro_range: tuple[int, int] | None = None
        self._highlighted_outro_range: tuple[int, int] | None = None

        # SF-6C: Find Intro/Outro button connections
        self.find_intro_btn.clicked.connect(self._on_find_intro)
        self.find_outro_btn.clicked.connect(self._on_find_outro)

        # Player connections
        self.play_btn.clicked.connect(self._toggle_playback)
        self.stop_btn.clicked.connect(self._stop_playback)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        self.seek_slider.sliderMoved.connect(self._on_seek_moved)
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.media_player.errorOccurred.connect(self._on_player_error)

        # Position sync timer (poll at 30fps for smooth updates)
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(33)  # ~30fps
        self._sync_timer.timeout.connect(self._sync_timeline)
        self._is_seeking = False

        self.log_panel.log("SCENE", "SceneFlow initialized")
        self.log_panel.log("PLAYBACK", "Waiting for video load...")

    # ── SF-8E: Reference alias for backwards compatibility ──────────────────
    @property
    def _subtitles(self) -> list[Subtitle]:
        """Backwards-compatible access to runtime subtitles. Never modify original."""
        return self._runtime_subtitles

    @_subtitles.setter
    def _subtitles(self, value: list[Subtitle]) -> None:
        self._runtime_subtitles = value

    # --------------------------------------------------------------------------
    # Playback Methods
    # --------------------------------------------------------------------------

    def _toggle_playback(self) -> None:
        if self.media_player.playbackState() == QMediaPlayer.PlayingState:
            self.media_player.pause()
            self.log_panel.log("PLAYBACK", "Paused")
        else:
            self.media_player.play()
            self.log_panel.log("PLAYBACK", "Playing")
            self._sync_timer.start()

    def _stop_playback(self) -> None:
        self.media_player.stop()
        self._sync_timer.stop()
        self.play_btn.setText("▶")
        self.log_panel.log("PLAYBACK", "Stopped")

    def _on_seek_pressed(self) -> None:
        self._is_seeking = True
        self.media_player.pause()

    def _on_seek_released(self) -> None:
        self._is_seeking = False
        position = self.seek_slider.value()
        self.media_player.setPosition(position)
        # Update UI immediately
        self._sync_scene_info_at_position(position)
        self._sync_timeline()
        self.log_panel.log("PLAYBACK", f"Seek to {self._format_time(position)}")

    def _on_seek_moved(self, position: int) -> None:
        # Update time label during drag
        duration = self.media_player.duration()
        self.time_label.setText(
            f"{self._format_time(position)} / {self._format_time(duration)}"
        )

    def _on_position_changed(self, position: int) -> None:
        if not self._is_seeking:
            duration = self.media_player.duration()
            self.seek_slider.blockSignals(True)
            self.seek_slider.setValue(position)
            self.seek_slider.blockSignals(False)
            self.time_label.setText(
                f"{self._format_time(position)} / {self._format_time(duration)}"
            )

    def _on_duration_changed(self, duration: int) -> None:
        self.seek_slider.setRange(0, duration)
        self.seek_slider.setEnabled(duration > 0)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlayingState:
            self.play_btn.setText("⏸")
            self._sync_timer.start()
        elif state == QMediaPlayer.PausedState:
            self.play_btn.setText("▶")
            self._sync_timer.stop()
            # Final sync on pause
            self._sync_timeline()
        else:  # StoppedState
            self.play_btn.setText("▶")
            self._sync_timer.stop()
            self._sync_timeline()

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        self.log_panel.log("PLAYBACK", f"Player error: {error_string}")
        self.play_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.seek_slider.setEnabled(False)

    def _format_time(self, ms: int) -> str:
        """Format milliseconds to M:SS.cc"""
        total_sec = ms / 1000.0
        m = int(total_sec // 60)
        s = total_sec % 60
        return f"{m}:{s:05.2f}"

    # --------------------------------------------------------------------------
    # Subtitle Sync - SF-8E: Uses runtime subtitle state ONLY
    # --------------------------------------------------------------------------

    def _update_subtitle_bar(self, pos_sec: float) -> None:
        """Update subtitle bar based on current playback position using runtime state."""
        if not self._runtime_subtitles:
            self.subtitle_bar.setText("")
            return

        # Find active subtitle at current position
        for sub in self._runtime_subtitles:
            if sub.start <= pos_sec <= sub.end:
                self.subtitle_bar.setText(sub.text)
                return

        # No active subtitle
        self.subtitle_bar.setText("")

    # ── SF-8E: Runtime subtitle copy system ──────────────────────────────────

    def _create_runtime_subtitle_copy(self) -> None:
        """Create a runtime subtitle copy from the original source.
        
        Original subtitle file is NEVER modified. All systems use only
        the runtime subtitle state (_runtime_subtitles).
        """
        if not self._original_subtitle_path or not self._video_name:
            return

        # Ensure audio directory exists
        audio_dir = Path(self._output_dir) / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Save runtime subtitle copy to output/<video_name>/audio/subtitles_runtime.json
        runtime_path = audio_dir / "subtitles_runtime.json"
        runtime_data = [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in self._runtime_subtitles
        ]
        with open(runtime_path, "w", encoding="utf-8") as f:
            json.dump(runtime_data, f, indent=2, ensure_ascii=False)

        self._runtime_subtitles_path = str(runtime_path)
        self.log_panel.log("SUBTITLE", f"Runtime subtitle copy created: {runtime_path}")
        self.log_panel.log("SUBTITLE", "Runtime subtitle state active")

    def _reload_runtime_subtitles(self) -> None:
        """Reload runtime subtitle state from original source.
        Recreates clean runtime state from the original file path.
        """
        if not self._original_subtitle_path:
            return

        ext = Path(self._original_subtitle_path).suffix.lower()
        if ext == ".srt":
            self._runtime_subtitles = parse_srt(self._original_subtitle_path)
        elif ext == ".ass" or ext == ".ssa":
            self._runtime_subtitles = parse_ass(self._original_subtitle_path)
        else:
            self._runtime_subtitles = []

        self._create_runtime_subtitle_copy()
        self.log_panel.log("SUBTITLE", "Runtime subtitle state reloaded from original")

    # --------------------------------------------------------------------------
    # Timeline Sync
    # --------------------------------------------------------------------------

    def _sync_timeline(self) -> None:
        """Sync all timeline elements to current playback position."""
        position = self.media_player.position()
        duration = self.media_player.duration()
        if duration <= 0:
            return

        # Update audio strip
        pos_sec = position / 1000.0
        self.audio_timeline_strip.set_current_time(pos_sec)

        # Update subtitle bar based on current position (uses runtime state)
        self._update_subtitle_bar(pos_sec)

        # Find active scene
        if self._metadata and self._scenes:
            fps = self._metadata.real_fps
            active_idx = -1
            for i, scene in enumerate(self._scenes):
                start_s = scene.start_sec(fps) * 1000  # ms
                end_s = scene.end_sec(fps) * 1000      # ms
                if start_s <= position <= end_s:
                    active_idx = i
                    break

            if active_idx >= 0 and active_idx != self._selected_index:
                self._selected_index = active_idx
                scene = self._scenes[active_idx]
                # Update scene info
                self._update_scene_info(active_idx)
                # Update timeline block highlighting
                for i in range(self.timeline_layout.count()):
                    w = self.timeline_layout.itemAt(i).widget()
                    if isinstance(w, SceneBlock):
                        w.set_selected(w._scene.index == scene.index)

                self.log_panel.log(
                    "PLAYBACK",
                    f"Active scene #{scene.index} @ {self._format_time(position)}"
                )

        # Update playhead position
        self._update_playhead()

    def _update_playhead(self) -> None:
        """Position the playhead overlay on the timeline."""
        if not self._scenes or not self._scenes:
            self.playhead.hide()
            return

        total_duration = self.media_player.duration()
        if total_duration <= 0:
            self.playhead.hide()
            return

        position = self.media_player.position()
        ratio = position / total_duration if total_duration > 0 else 0.0

        viewport = self.timeline_scroll.viewport()
        scroll_w = self.timeline_content.width() if self.timeline_content.width() > 0 else 1
        # Position playhead relative to scroll area viewport
        content_x = int(ratio * self.timeline_content.width())
        visible_x = content_x - self.timeline_scroll.horizontalScrollBar().value()

        if 0 <= visible_x <= viewport.width():
            self.playhead.show()
            self.playhead.move(visible_x - 1, 0)
            self.playhead.setFixedHeight(viewport.height())
        else:
            self.playhead.hide()

    def _sync_scene_info_at_position(self, position_ms: int) -> None:
        """Update scene info based on seek position."""
        if not self._metadata or not self._scenes:
            return

        fps = self._metadata.real_fps
        pos_sec = position_ms / 1000.0
        for i, scene in enumerate(self._scenes):
            start_s = scene.start_sec(fps)
            end_s = scene.end_sec(fps)
            if start_s <= pos_sec <= end_s:
                self._selected_index = i
                self._update_scene_info(i)
                # Update timeline selection
                for j in range(self.timeline_layout.count()):
                    w = self.timeline_layout.itemAt(j).widget()
                    if isinstance(w, SceneBlock):
                        w.set_selected(w._scene.index == scene.index)
                        if w._scene.index == scene.index:
                            # Scroll to make this scene visible
                            w_global = w.mapTo(self.timeline_content, QPoint(0, 0))
                            self.timeline_scroll.ensureVisible(
                                w_global.x(), w_global.y(), 50, 50
                            )
                break

    # --------------------------------------------------------------------------
    # Audio Methods
    # --------------------------------------------------------------------------

    def _on_analyze_audio(self) -> None:
        if not self._current_path or not self._metadata:
            return

        self.analyze_audio_btn.setEnabled(False)
        self.audio_status_label.setText("Extracting audio...")
        self.audio_status_label.setStyleSheet("color: #ffcc00; font-size: 10pt; font-weight: bold;")
        self.stage_label.setText("Analyzing audio...")
        self.stage_label.setStyleSheet("color: #ffcc00;")
        self.progress_label.setText("0%")
        self.log_panel.log("AUDIO", "Starting audio extraction...")

        self._audio_worker = AudioAnalysisWorker(
            self._current_path, self._metadata.duration
        )
        self._audio_worker.stage_changed.connect(self._on_stage_changed)
        self._audio_worker.progress_updated.connect(self._on_progress_updated)
        self._audio_worker.finished.connect(self._on_audio_done)
        self._audio_worker.error.connect(self._on_audio_error)
        self._audio_worker.start()

    def _on_audio_done(self, regions: list[AudioRegion]) -> None:
        self._audio_regions = regions
        self.analyze_audio_btn.setEnabled(True)
        self.export_audio_btn.setEnabled(True)

        music_count = sum(1 for r in regions if r.type == "music")
        speech_count = sum(1 for r in regions if r.type == "speech")
        silence_count = sum(1 for r in regions if r.type == "silence")
        energy_count = sum(1 for r in regions if r.type == "high_energy")
        music_speech_count = sum(1 for r in regions if r.type == "music_speech")

        status_msg = (
            f"AUDIO ANALYSIS COMPLETE  ({len(regions)} regions | "
            f"M:{music_count} S:{speech_count} MS:{music_speech_count} "
            f"Z:{silence_count} E:{energy_count})"
        )
        self.audio_status_label.setText(status_msg)
        self.audio_status_label.setStyleSheet("color: #4f4; font-size: 10pt; font-weight: bold;")
        self.scene_status_label.setText("AUDIO: Complete")
        self.scene_status_label.setStyleSheet("color: #8f8; font-size: 10pt; font-weight: bold;")
        self.progress_label.setText("100%")
        self.log_panel.log("AUDIO", f"Analysis complete: {len(regions)} regions")

        # Pass audio regions to timeline blocks
        for i in range(self.timeline_layout.count()):
            w = self.timeline_layout.itemAt(i).widget()
            if isinstance(w, SceneBlock):
                w.set_audio_regions(regions)

        # Update audio timeline strip
        duration = self._metadata.duration if self._metadata else 1.0
        self.audio_timeline_strip.set_regions(regions, duration)

    def _on_audio_error(self, msg: str) -> None:
        self.analyze_audio_btn.setEnabled(True)
        self.audio_status_label.setText(f"AUDIO ERROR: {msg}")
        self.audio_status_label.setStyleSheet("color: #f44; font-size: 10pt; font-weight: bold;")
        self.scene_status_label.setText("AUDIO: Error")
        self.scene_status_label.setStyleSheet("color: #f88; font-size: 10pt; font-weight: bold;")
        self.progress_label.setText("")
        self.log_panel.log("AUDIO", f"Error: {msg}")

    def _on_export_audio(self) -> None:
        if not self._audio_regions:
            return
        video_name = self._video_name or "unknown"
        export_audio_regions(self._audio_regions, self._output_dir, video_name)
        self.stage_label.setText("Audio JSON exported")
        self.stage_label.setStyleSheet("color: #8f8;")
        self.log_panel.log("EXPORT", f"Audio regions exported to {self._output_dir}/audio/")

    # ── SF-8E: CUT methods ──────────────────────────────────────────────────

    def _update_cut_buttons(self) -> None:
        """Enable/disable CUT buttons based on whether valid ranges exist."""
        has_intro_range = (
            self._intro_start_idx is not None and
            self._intro_end_idx is not None and
            not self._intro_cut_applied
        )
        has_outro_range = (
            self._outro_start_idx is not None and
            self._outro_end_idx is not None and
            not self._outro_cut_applied
        )
        self.cut_intro_btn.setEnabled(has_intro_range)
        self.cut_outro_btn.setEnabled(has_outro_range)

    def _on_cut_intro(self) -> None:
        """SF-PART5: Mark intro scenes as filtered, DO NOT delete source files."""
        if self._intro_start_idx is None or self._intro_end_idx is None:
            return
        if not self._scenes:
            return

        start_idx = min(self._intro_start_idx, self._intro_end_idx)
        end_idx = max(self._intro_start_idx, self._intro_end_idx)

        # Record cut indices for manifest
        self._intro_cut_start = start_idx
        self._intro_cut_end = end_idx

        # SF-PART5: Mark scenes as filtered, DO NOT delete frame files
        for s in self._scenes:
            if start_idx <= s.index <= end_idx:
                s.filtered = True
                s.filtered_reason = "intro"
                print(f"[CUT] scene_{s.source_id:04d} filtered=intro")

        # SF-PART1: DO NOT renumber scenes - preserve source identities
        # Removed: self._scenes = [s for s in self._scenes if s.index not in range(...)]
        # Removed: for new_idx, s in enumerate(self._scenes, 1): s.index = new_idx

        # Remove from runtime subtitles
        if self._runtime_subtitles:
            fps = self._metadata.real_fps if self._metadata else 23.976
            removed_times = set()
            for s in self._scenes:
                if s.filtered:
                    removed_times.add((s.start_sec(fps), s.end_sec(fps)))

            self._runtime_subtitles = [
                sub for sub in self._runtime_subtitles
                if not any(s_start <= sub.start <= s_end or s_start <= sub.end <= s_end
                           for s_start, s_end in removed_times)
            ]

        # Remove from audio regions
        if self._audio_regions:
            fps = self._metadata.real_fps if self._metadata else 23.976
            removed_times = [(s.start_sec(fps), s.end_sec(fps)) for s in self._scenes if s.filtered]
            self._audio_regions = [
                r for r in self._audio_regions
                if not any(r.start >= s_start and r.end <= s_end 
                           for s_start, s_end in removed_times)
            ]

        # Mark CUT as applied
        self._intro_cut_applied = True
        self.cut_intro_btn.setEnabled(False)

        # Reset intro markers
        self._intro_start_idx = None
        self._intro_end_idx = None

        # Reload runtime subtitle state from original
        self._reload_runtime_subtitles()

        # Rebuild timeline UI
        self._render_timeline()
        self._update_scene_info(0 if self._scenes else -1)

        # Rebuild audio strip
        if self._audio_regions and self._metadata:
            self.audio_timeline_strip.set_regions(
                self._audio_regions, self._metadata.duration
            )

        self.log_panel.log("PROFILE", "Intro scenes marked as filtered (source preserved)")
        print(f"[PROFILE] Intro scenes marked as filtered (scenes {start_idx}-{end_idx})")

    def _on_cut_outro(self) -> None:
        """SF-PART5: Mark outro scenes as filtered, DO NOT delete source files."""
        if self._outro_start_idx is None or self._outro_end_idx is None:
            return
        if not self._scenes:
            return

        start_idx = min(self._outro_start_idx, self._outro_end_idx)
        end_idx = max(self._outro_start_idx, self._outro_end_idx)

        # Record cut indices for manifest
        self._outro_cut_start = start_idx
        self._outro_cut_end = end_idx

        # SF-PART5: Mark scenes as filtered, DO NOT delete frame files
        for s in self._scenes:
            if start_idx <= s.index <= end_idx:
                s.filtered = True
                s.filtered_reason = "outro"
                print(f"[CUT] scene_{s.source_id:04d} filtered=outro")

        # SF-PART1: DO NOT renumber scenes - preserve source identities
        # Removed: to_remove = [s for s in self._scenes if start_idx <= s.index <= end_idx]
        # Removed: self._scenes = [s for s in self._scenes if s.index not in range(...)]
        # Removed: for new_idx, s in enumerate(self._scenes, 1): s.index = new_idx

        # Remove from runtime subtitles
        if self._runtime_subtitles:
            fps = self._metadata.real_fps if self._metadata else 23.976
            removed_times = set()
            for s in self._scenes:
                if s.filtered:
                    removed_times.add((s.start_sec(fps), s.end_sec(fps)))
            self._runtime_subtitles = [
                sub for sub in self._runtime_subtitles
                if not any(s_start <= sub.start <= s_end or s_start <= sub.end <= s_end
                           for s_start, s_end in removed_times)
            ]

        # Remove from audio regions
        if self._audio_regions:
            fps = self._metadata.real_fps if self._metadata else 23.976
            removed_times = [(s.start_sec(fps), s.end_sec(fps)) for s in self._scenes if s.filtered]
            self._audio_regions = [
                r for r in self._audio_regions
                if not any(r.start >= s_start and r.end <= s_end 
                           for s_start, s_end in removed_times)
            ]

        # Mark CUT as applied
        self._outro_cut_applied = True
        self.cut_outro_btn.setEnabled(False)

        # Reset outro markers
        self._outro_start_idx = None
        self._outro_end_idx = None

        # Reload runtime subtitle state from original (clean copy)
        self._reload_runtime_subtitles()

        # Rebuild timeline UI
        self._render_timeline()
        self._update_scene_info(0 if self._scenes else -1)

        # Rebuild audio strip
        if self._audio_regions and self._metadata:
            self.audio_timeline_strip.set_regions(
                self._audio_regions, self._metadata.duration
            )

        self.log_panel.log("PROFILE", "Outro scenes marked as filtered (source preserved)")
        print(f"[PROFILE] Outro scenes marked as filtered (scenes {start_idx}-{end_idx})")

    # ── SF-8E: Clean package export ─────────────────────────────────────────

    def _on_export_package(self) -> None:
        """SF-8E: Export ONLY current runtime state AFTER CUT."""
        if not self._scenes or not self._metadata:
            self.log_panel.log("EXPORT", "No scenes or metadata to export")
            return

        video_name = self._video_name or "unknown"
        pkg_dir = Path("output") / video_name / "packages"

        # Check if package already exists - show overwrite dialog
        if pkg_dir.exists():
            msg = QMessageBox(self)
            msg.setWindowTitle("Package Exists")
            msg.setText("Overwrite existing package?")
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #1a1a1a;
                    color: #ccc;
                }
                QMessageBox QLabel {
                    color: #ccc;
                    font-size: 11pt;
                }
                QPushButton {
                    background-color: #2a2a2a;
                    color: #ccc;
                    border: 1px solid #555;
                    padding: 6px 16px;
                    min-width: 80px;
                }
                QPushButton:hover {
                    background-color: #3a3a3a;
                }
            """)
            reply = msg.exec()
            if reply == QMessageBox.StandardButton.Cancel:
                self.log_panel.log("EXPORT", "Export cancelled by user")
                return

        # Disable button immediately
        self.export_package_btn.setEnabled(False)

        try:
            self.stage_label.setText("Creating package...")
            self.stage_label.setStyleSheet("color: #ffcc00;")
            self.progress_label.setText("0%")
            self.log_panel.log("EXPORT", f"Starting package export: {video_name}")

            # Export ONLY current runtime state - scenes already filtered by CUT
            self._package_worker = ExportPackageWorker(
                scenes=self._scenes,
                metadata=self._metadata,
                subtitles=self._runtime_subtitles,  # Uses runtime state
                audio_regions=self._audio_regions,
                output_base="output",
                video_name=video_name,
                intro_cut=self._intro_cut_applied,
                outro_cut=self._outro_cut_applied,
            )
            self._package_worker.stage_changed.connect(self._on_export_stage_changed)
            self._package_worker.progress_updated.connect(self._on_progress_updated)
            self._package_worker.finished.connect(self._on_export_package_done)
            self._package_worker.error.connect(self._on_export_error)
            self._package_worker.start()

        except Exception as e:
            self._on_export_error(str(e))
        finally:
            # Re-enable button if worker failed to start
            pass

    # --------------------------------------------------------------------------
    def _on_export_package_done(self) -> None:
        """Handle package export completion."""
        self.stage_label.setText("Package export complete")
        self.stage_label.setStyleSheet("color: #8f8;")
        self.progress_label.setText("100%")
        self.export_package_btn.setEnabled(True)
        video_name = self._video_name or "unknown"
        self.log_panel.log("EXPORT", f"Package export complete: output/{video_name}/packages/")

    # --------------------------------------------------------------------------
    def _on_encoder_changed(self, index: int) -> None:
        self._encoder = self.encoder_combo.itemData(index)

    # --------------------------------------------------------------------------
    def _clear_runtime_state(self) -> None:
        """Clear runtime-generated data from output/<video_name>/ for fresh analysis session."""
        if not self._video_name:
            return
        
        import shutil
        runtime_dir = Path("output") / self._video_name
        if runtime_dir.exists():
            self.log_panel.log("RUNTIME", "Clearing previous runtime state")
            shutil.rmtree(runtime_dir)
            self.log_panel.log("RUNTIME", "Runtime reset complete")

    def _on_select_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", "Video Files (*.mp4);;All Files (*)",
        )
        if not path:
            return

        # SF-8B: Clear stale runtime state before loading new video
        self._clear_runtime_state()

        self._current_path = path
        self._video_name = Path(path).stem
        self.path_label.setText(path)
        self.path_label.setStyleSheet("color: #ccc;")
        self.subtitle_btn.setEnabled(True)
        self.detect_btn.setEnabled(True)
        self.analyze_audio_btn.setEnabled(True)
        self._disable_export_buttons()
        self.stage_label.setText("")
        self.progress_label.setText("")
        self._clear_timeline()
        self._extract_metadata(path)
        self._setup_player(path)

        # Reset SF-8E CUT state on new video
        self._intro_cut_applied = False
        self._outro_cut_applied = False
        self._intro_cut_start = None
        self._intro_cut_end = None
        self._outro_cut_start = None
        self._outro_cut_end = None
        self._original_subtitle_path = ""
        self._runtime_subtitles = []
        self._runtime_subtitles_path = ""

        self._output_dir = str(Path("output") / self._video_name)
        self.output_label.setText(self._output_dir)
        self.output_label.setStyleSheet("color: #ccc;")
        self.log_panel.log("SCENE", f"Video loaded: {Path(path).name}")

    def _setup_player(self, video_path: str) -> None:
        """Initialize QMediaPlayer with the video source."""
        from PySide6.QtCore import QUrl
        from pathlib import Path

        self.media_player.stop()
        self.media_player.setSource(QUrl.fromLocalFile(str(Path(video_path).absolute())))
        self.play_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.seek_slider.setValue(0)
        self.time_label.setText("0:00.00 / 0:00.00")
        self.log_panel.log("PLAYBACK", f"Source set: {Path(video_path).name}")

    # --------------------------------------------------------------------------
    def _on_load_subtitle(self) -> None:
        """SF-8E: Load subtitle with runtime safety.
        
        Original file is NEVER modified. All operations use runtime copy.
        """
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Subtitle File", "",
            "Subtitle Files (*.srt *.ass);;SRT (*.srt);;ASS (*.ass);;All Files (*)",
        )
        if not path:
            return

        # Store original path - this file is NEVER modified
        self._original_subtitle_path = path

        # Verify original file exists
        if not Path(path).exists():
            self.log_panel.log("SUBTITLE", "Original subtitle file not found")
            return

        # Read original subtitle and parse
        ext = Path(path).suffix.lower()
        if ext == ".srt":
            self._runtime_subtitles = parse_srt(path)
        elif ext == ".ass" or ext == ".ssa":
            self._runtime_subtitles = parse_ass(path)
        else:
            self._runtime_subtitles = []

        name = Path(path).name
        self.subtitle_label.setText(f"Sub: {name} ({len(self._runtime_subtitles)} entries)")
        self.subtitle_label.setStyleSheet("color: #6cf; font-size: 9pt;")
        self.log_panel.log("SUBTITLE", f"Loaded {len(self._runtime_subtitles)} entries from {name} (original untouched)")

        # Create runtime copy
        self._create_runtime_subtitle_copy()

        # Match runtime subtitles to scenes if scenes exist
        if self._scenes and self._metadata:
            match_subtitles_to_scenes(self._runtime_subtitles, self._scenes, self._metadata.real_fps)
            self._render_timeline()
            self._update_scene_info(self._selected_index)

        # Enable CUT buttons if we have valid ranges
        self._update_cut_buttons()

    # --------------------------------------------------------------------------
    def _extract_metadata(self, video_path: str) -> None:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            self.fps_label.setText("FPS: Error")
            self._metadata = None
            return

        real_fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / real_fps if real_fps > 0 else 0.0

        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc_int >> 8 * i) & 0xFF) for i in range(4)])
        cap.release()

        self._metadata = VideoMetadata(
            path=video_path, real_fps=real_fps, total_frames=total_frames,
            duration=duration, width=width, height=height, codec=codec,
        )

        self.fps_label.setText(f"FPS: {real_fps:.6f}")
        self.res_label.setText(f"Resolution: {width}x{height}")
        self.frames_label.setText(f"Total Frames: {total_frames:,}")
        self.duration_meta_label.setText(f"Duration: {self._metadata.duration_str()}")
        self.codec_label.setText(f"Codec: {codec}")

    # --------------------------------------------------------------------------
    def _on_select_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", self._output_dir)
        if not folder:
            return
        self._output_dir = folder
        self.output_label.setText(folder)
        self.output_label.setStyleSheet("color: #ccc;")

    # --------------------------------------------------------------------------
    def _on_detect_scenes(self) -> None:
        if not self._current_path or not self._metadata:
            return

        self.detect_btn.setEnabled(False)
        self._disable_export_buttons()
        self.stage_label.setText("Starting...")
        self.stage_label.setStyleSheet("color: #ffcc00;")
        self.progress_label.setText("0%")
        self.log_panel.log("SCENE", "Starting scene detection...")

        self._worker = DetectWorker(self._current_path, self._metadata)
        self._worker.stage_changed.connect(self._on_stage_changed)
        self._worker.progress_updated.connect(self._on_progress_updated)
        self._worker.finished.connect(self._on_detect_done)
        self._worker.error.connect(self._on_detect_error)
        self._worker.start()

    # --------------------------------------------------------------------------
    def _on_stage_changed(self, stage: str) -> None:
        self.scene_status_label.setText(f"SCENE DETECTION: {stage}")
        self.scene_status_label.setStyleSheet("color: #ffcc00; font-size: 10pt; font-weight: bold;")
        self.log_panel.log("SCENE", f"Stage: {stage}")

    # --------------------------------------------------------------------------
    def _on_export_stage_changed(self, stage: str) -> None:
        """Handle export package worker stage changes with [EXPORT] prefix."""
        self.scene_status_label.setText(f"EXPORT: {stage}")
        self.scene_status_label.setStyleSheet("color: #ffcc00; font-size: 10pt; font-weight: bold;")
        self.log_panel.log("EXPORT", f"{stage}")

    # --------------------------------------------------------------------------
    def _on_progress_updated(self, pct: int) -> None:
        self.progress_label.setText(f"{pct}%")
        if pct < 100:
            self.scene_status_label.setStyleSheet("color: #ffcc00; font-size: 10pt; font-weight: bold;")
        else:
            self.scene_status_label.setStyleSheet("color: #8f8; font-size: 10pt; font-weight: bold;")

    # --------------------------------------------------------------------------
    def _on_detect_done(self, scenes: list[Scene]) -> None:
        self.detect_btn.setEnabled(True)
        self.scene_status_label.setText(f"SCENE DETECTION COMPLETE  ({len(scenes)} scenes)")
        self.scene_status_label.setStyleSheet("color: #4f4; font-size: 10pt; font-weight: bold;")
        self.stage_label.setText("Detection complete")
        self.stage_label.setStyleSheet("color: #8f8;")
        self.progress_label.setText("100%")
        self._scenes = scenes
        self._selected_index = 0

        # Match runtime subtitles to scenes
        if self._runtime_subtitles and self._metadata:
            match_subtitles_to_scenes(self._runtime_subtitles, self._scenes, self._metadata.real_fps)

        self._enable_export_buttons()
        self._render_timeline()
        self._update_scene_info(0)

        # SF-6A: Try loading profiles now that scenes exist
        self._try_load_profiles()

        # Update CUT button state
        self._update_cut_buttons()

        self.log_panel.log("SCENE", f"Detection complete: {len(scenes)} scenes found")

    # --------------------------------------------------------------------------
    def _on_detect_error(self, msg: str) -> None:
        self.detect_btn.setEnabled(True)
        self.stage_label.setText(f"Error: {msg}")
        self.stage_label.setStyleSheet("color: #f88;")
        self.progress_label.setText("")
        self.log_panel.log("SCENE", f"Detection error: {msg}")

    # --------------------------------------------------------------------------
    def _on_export_mp4(self) -> None:
        if not self._current_path or not self._scenes or not self._metadata:
            return

        self._disable_export_buttons()
        self.stage_label.setText("Exporting MP4...")
        self.stage_label.setStyleSheet("color: #ffcc00;")
        self.progress_label.setText("0%")
        self.log_panel.log("EXPORT", "Starting MP4 export...")

        self._mp4_worker = ExportMP4Worker(
            self._current_path, self._scenes, self._metadata.real_fps,
            self._output_dir, self._video_name, self._encoder,
        )
        self._mp4_worker.stage_changed.connect(self._on_stage_changed)
        self._mp4_worker.progress_updated.connect(self._on_progress_updated)
        self._mp4_worker.finished.connect(self._on_export_mp4_done)
        self._mp4_worker.error.connect(self._on_export_error)
        self._mp4_worker.start()

    # --------------------------------------------------------------------------
    def _on_export_mp4_done(self) -> None:
        self.stage_label.setText("MP4 export complete")
        self.stage_label.setStyleSheet("color: #8f8;")
        self.progress_label.setText("100%")
        self._enable_export_buttons()
        self.log_panel.log("EXPORT", "MP4 export complete")
        self._update_scene_info(self._selected_index)

    # --------------------------------------------------------------------------
    def _on_export_png(self) -> None:
        if not self._current_path or not self._scenes or not self._metadata:
            return

        self._disable_export_buttons()
        self.stage_label.setText("Exporting PNG frames...")
        self.stage_label.setStyleSheet("color: #ffcc00;")
        self.progress_label.setText("0%")
        self.log_panel.log("EXPORT", "Starting PNG export...")

        self._png_worker = ExportPNGWorker(
            self._current_path, self._scenes, self._metadata.real_fps,
            self._output_dir, self._video_name,
        )
        self._png_worker.stage_changed.connect(self._on_stage_changed)
        self._png_worker.progress_updated.connect(self._on_progress_updated)
        self._png_worker.finished.connect(self._on_export_png_done)
        self._png_worker.error.connect(self._on_export_error)
        self._png_worker.start()

    # --------------------------------------------------------------------------
    def _on_export_png_done(self) -> None:
        self.stage_label.setText("PNG export complete")
        self.stage_label.setStyleSheet("color: #8f8;")
        self.progress_label.setText("100%")
        self._enable_export_buttons()
        self.log_panel.log("EXPORT", "PNG export complete")
        self._update_scene_info(self._selected_index)
        self._render_timeline()

    # --------------------------------------------------------------------------
    def _on_export_json(self) -> None:
        if not self._scenes or not self._metadata:
            return

        export_scene_metadata(
            self._scenes, self._metadata.real_fps,
            self._output_dir, self._video_name
        )
        self.stage_label.setText("Metadata JSON exported")
        self.stage_label.setStyleSheet("color: #8f8;")
        self.log_panel.log("EXPORT", "Metadata JSON exported")
        self._update_scene_info(self._selected_index)
        self._render_timeline()

    # --------------------------------------------------------------------------
    def _on_export_error(self, msg: str) -> None:
        self.stage_label.setText(f"Export error: {msg}")
        self.stage_label.setStyleSheet("color: #f88;")
        self.progress_label.setText("")
        self._enable_export_buttons()
        self.log_panel.log("EXPORT", f"Export error: {msg}")

    # --------------------------------------------------------------------------
    def _disable_export_buttons(self) -> None:
        self.export_mp4_btn.setEnabled(False)
        self.export_png_btn.setEnabled(False)
        self.export_json_btn.setEnabled(False)
        self.export_audio_btn.setEnabled(False)
        self.export_package_btn.setEnabled(False)

    # --------------------------------------------------------------------------
    def _enable_export_buttons(self) -> None:
        self.export_mp4_btn.setEnabled(True)
        self.export_png_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)
        self.export_audio_btn.setEnabled(True)
        self.export_package_btn.setEnabled(True)

    # --------------------------------------------------------------------------
    def _render_timeline(self) -> None:
        while self.timeline_layout.count():
            item = self.timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._scenes or not self._metadata:
            return

        fps = self._metadata.real_fps
        for scene in self._scenes:
            block = SceneBlock(scene, fps)
            block.clicked.connect(self._on_scene_click)
            self.timeline_layout.addWidget(block)

        self.timeline_label.setText(f"Timeline: {len(self._scenes)} scenes")
        self._extract_thumbnails()

        # Update audio timeline strip
        if self._audio_regions:
            duration = self._metadata.duration if self._metadata else 1.0
            self.audio_timeline_strip.set_regions(self._audio_regions, duration)

        self.log_panel.log("SCENE", f"Timeline rendered: {len(self._scenes)} scenes")

    # --------------------------------------------------------------------------
    def _extract_thumbnails(self) -> None:
        if not self._current_path or not self._metadata:
            return

        cap = cv2.VideoCapture(self._current_path)
        if not cap.isOpened():
            return

        for scene in self._scenes:
            frame_idx = (scene.start_frame + scene.end_frame) // 2
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w = frame_rgb.shape[:2]
                scale = 88 / max(h, w)
                small = cv2.resize(
                    frame_rgb, (int(w * scale), int(h * scale)),
                    interpolation=cv2.INTER_AREA,
                )
                h2, w2 = small.shape[:2]
                qimg = QImage(small.data, w2, h2, w2 * 3, QImage.Format_RGB888)
                scene.thumbnail = QPixmap.fromImage(qimg)
                for i in range(self.timeline_layout.count()):
                    widget = self.timeline_layout.itemAt(i).widget()
                    if isinstance(widget, SceneBlock) and widget._scene is scene:
                        widget.update()
                        break
        cap.release()

    # --------------------------------------------------------------------------

    # --------------------------------------------------------------------------
    def _update_scene_info(self, scene_idx: int) -> None:
        """Update all sections of the Scene Info panel."""
        if not self._scenes or scene_idx < 0 or scene_idx >= len(self._scenes):
            self.scene_num_label.setText("Scene #--")
            self.scene_start_label.setText("Start: --")
            self.scene_end_label.setText("End: --")
            self.scene_dur_label.setText("Duration: --")
            self.scene_audio_type.setText("Dominant: --")
            self.scene_audio_energy.setText("Avg energy: --")
            self.scene_audio_overlap.setText("Overlapping regions: --")
            self.export_png_status.setText("PNG: Not exported")
            self.export_meta_status.setText("Metadata: Not exported")
            self.export_mp4_status.setText("MP4: Not exported")
            return

        scene = self._scenes[scene_idx]
        fps = self._metadata.real_fps if self._metadata else 23.976

        # SCENE section
        self.scene_num_label.setText(f"Scene #{scene.index}")
        self.scene_start_label.setText(f"Start: {scene.start_sec(fps):.3f}s ({scene.start_frame} frames)")
        self.scene_end_label.setText(f"End: {scene.end_sec(fps):.3f}s ({scene.end_frame} frames)")
        self.scene_dur_label.setText(f"Duration: {scene.duration_str(fps)} ({scene.duration_sec(fps):.3f}s)")

        # (Subtitle info now shown in subtitle bar below video)

        # AUDIO section
        if self._audio_regions:
            # Find regions overlapping this scene
            scene_start = scene.start_sec(fps)
            scene_end = scene.end_sec(fps)
            overlapping = [
                r for r in self._audio_regions
                if r.start < scene_end and r.end > scene_start
            ]
            if overlapping:
                # Dominant type
                type_counts: dict[str, int] = {}
                for r in overlapping:
                    overlap_dur = min(r.end, scene_end) - max(r.start, scene_start)
                    if overlap_dur > 0:
                        type_counts[r.type] = type_counts.get(r.type, 0) + overlap_dur
                dominant = max(type_counts, key=type_counts.get) if type_counts else "unknown"
                avg_energy = sum(r.energy for r in overlapping) / len(overlapping)
                self.scene_audio_type.setText(f"Dominant: {dominant}")
                self.scene_audio_energy.setText(f"Avg energy: {avg_energy:.3f}")
                self.scene_audio_overlap.setText(f"Overlapping regions: {len(overlapping)}")
            else:
                self.scene_audio_type.setText("Dominant: --")
                self.scene_audio_energy.setText("Avg energy: --")
                self.scene_audio_overlap.setText("Overlapping regions: 0")
        else:
            self.scene_audio_type.setText("Dominant: -- (analyze audio first)")
            self.scene_audio_energy.setText("Avg energy: --")
            self.scene_audio_overlap.setText("Overlapping regions: --")

        # EXPORT STATUS section
        self.export_png_status.setText(
            f"PNG: {'Exported' if scene.png_exported else 'Not exported'}"
        )
        self.export_png_status.setStyleSheet(
            f"color: {'#4f4' if scene.png_exported else '#888'}; font-size: 8pt;"
        )
        self.export_meta_status.setText(
            f"Metadata: {'Exported' if scene.metadata_exported else 'Not exported'}"
        )
        self.export_meta_status.setStyleSheet(
            f"color: {'#ffcc00' if scene.metadata_exported else '#888'}; font-size: 8pt;"
        )
        self.export_mp4_status.setText(
            f"MP4: {'Exported' if scene.mp4_exported else 'Not exported'}"
        )
        self.export_mp4_status.setStyleSheet(
            f"color: {'#ff8844' if scene.mp4_exported else '#888'}; font-size: 8pt;"
        )

        # Scene subtitle count shown via badge on timeline blocks

    # --------------------------------------------------------------------------
    def _clear_timeline(self) -> None:
        self._scenes = []
        self._selected_index = 0
        while self.timeline_layout.count():
            item = self.timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.timeline_label.setText("No scenes")
        self._update_scene_info(-1)
        self.audio_timeline_strip.set_regions([], 1.0)

    # --------------------------------------------------------------------------
    # SF-6B: Segment Profile Methods
    # --------------------------------------------------------------------------

    def _on_toggle_selection_mode(self, seg_type: str, boundary: str) -> None:
        """Toggle selection mode. Clicking a scene will assign it to this boundary and exit mode."""
        if not self._scenes or self._selected_index < 0:
            return

        scene_idx = self._scenes[self._selected_index].index
        mode_key = (seg_type, boundary)

        # If already in this mode, cancel it
        if self._selection_mode == mode_key:
            self._exit_selection_mode()
            self.log_panel.log("SCENE", f"Selection mode cancelled")
            return

        # Enter new selection mode (cancels any existing mode)
        self._enter_selection_mode(seg_type, boundary)
        self.log_panel.log("SCENE", f"Entered {seg_type} {boundary} selection mode. Click a scene.")

    def _enter_selection_mode(self, seg_type: str, boundary: str) -> None:
        """Enter selection mode for a specific boundary."""
        # Exit any current mode first
        self._exit_selection_mode(False)

        # Set new mode
        self._selection_mode = (seg_type, boundary)

        # Update button states
        self._update_selection_mode_buttons()

        # Update status
        if seg_type == "intro":
            self.intro_status_label.setText(f"INTRO {boundary.upper()}: Click scene...")
            self.intro_status_label.setStyleSheet("color: #ffcc00; font-size: 7pt; font-style: italic;")
        else:
            self.outro_status_label.setText(f"OUTRO {boundary.upper()}: Click scene...")
            self.outro_status_label.setStyleSheet("color: #ffcc00; font-size: 7pt; font-style: italic;")

    def _exit_selection_mode(self, clear_ui: bool = True) -> None:
        """Exit selection mode, optionally clearing UI state."""
        if not self._selection_mode:
            return

        seg_type, boundary = self._selection_mode
        self._selection_mode = None

        if clear_ui:
            self._update_selection_mode_buttons()

    def _update_selection_mode_buttons(self) -> None:
        """Update button checked states based on current selection mode."""
        mode = self._selection_mode

        # Intro buttons
        intro_start_checked = mode == ("intro", "start")
        intro_end_checked = mode == ("intro", "end")
        self.mark_intro_start_btn.setChecked(intro_start_checked)
        self.mark_intro_end_btn.setChecked(intro_end_checked)

        # Outro buttons
        outro_start_checked = mode == ("outro", "start")
        outro_end_checked = mode == ("outro", "end")
        self.mark_outro_start_btn.setChecked(outro_start_checked)
        self.mark_outro_end_btn.setChecked(outro_end_checked)

        # Disable buttons from OTHER group when one is active
        # (mutual exclusion between intro/outro groups)
        has_mode = mode is not None
        other_seg_type = "outro" if mode and mode[0] == "intro" else "intro"

        # Disable buttons from the OTHER group
        if other_seg_type == "intro":
            self.mark_intro_start_btn.setEnabled(mode is None or mode[0] != "intro")
            self.mark_intro_end_btn.setEnabled(mode is None or mode[0] != "intro")
        else:
            self.mark_outro_start_btn.setEnabled(mode is None or mode[0] != "outro")
            self.mark_outro_end_btn.setEnabled(mode is None or mode[0] != "outro")

        # Enable own group buttons
        if mode:
            if mode[0] == "intro":
                self.mark_intro_start_btn.setEnabled(True)
                self.mark_intro_end_btn.setEnabled(True)
            else:
                self.mark_outro_start_btn.setEnabled(True)
                self.mark_outro_end_btn.setEnabled(True)

    def _on_scene_click(self, scene_idx: int) -> None:
        """Handle scene click. If in selection mode, assign scene and exit mode."""
        if self._selection_mode and self._scenes:
            seg_type, boundary = self._selection_mode

            # Assign to the boundary
            if seg_type == "intro":
                if boundary == "start":
                    self._intro_start_idx = scene_idx
                    self.intro_status_label.setText(f"INTRO START: Scene {scene_idx}")
                    self.intro_status_label.setStyleSheet("color: #cc6; font-size: 7pt;")
                    self.log_panel.log("SCENE", f"Marked intro start: Scene {scene_idx}")
                else:
                    self._intro_end_idx = scene_idx
                    self.intro_status_label.setText(
                        f"INTRO END: Scene {scene_idx}  |  Range: {self._intro_start_idx or '?'} → {scene_idx}"
                    )
                    self.intro_status_label.setStyleSheet("color: #cc6; font-size: 7pt; font-weight: bold;")
                    self.log_panel.log("SCENE", f"Marked intro end: Scene {scene_idx}")
                # Enable cut button after marking end
                if self._intro_start_idx is not None and self._intro_end_idx is not None:
                    self._update_cut_buttons()
            else:
                if boundary == "start":
                    self._outro_start_idx = scene_idx
                    self.outro_status_label.setText(f"OUTRO START: Scene {scene_idx}")
                    self.outro_status_label.setStyleSheet("color: #c6c; font-size: 7pt;")
                    self.log_panel.log("SCENE", f"Marked outro start: Scene {scene_idx}")
                else:
                    self._outro_end_idx = scene_idx
                    self.outro_status_label.setText(
                        f"OUTRO END: Scene {scene_idx}  |  Range: {self._outro_start_idx or '?'} → {scene_idx}"
                    )
                    self.outro_status_label.setStyleSheet("color: #c6c; font-size: 7pt; font-weight: bold;")
                    self.log_panel.log("SCENE", f"Marked outro end: Scene {scene_idx}")
                # Enable cut button after marking end
                if self._outro_start_idx is not None and self._outro_end_idx is not None:
                    self._update_cut_buttons()

            # Exit selection mode automatically
            self._exit_selection_mode()
            return

        # Normal scene selection (not in selection mode)
        self._selected_index = next(
            (i for i, s in enumerate(self._scenes) if s.index == scene_idx), 0
        )
        self._update_scene_info(self._selected_index)
        self._seek_to_scene(scene_idx)

    def _on_load_profile(self, seg_type: str) -> None:
        """Open file dialog to manually load a profile."""
        filters = "JSON Profile (*.json);;All Files (*)"
        if seg_type == "intro":
            caption = "Load Intro Profile"
        else:
            caption = "Load Outro Profile"

        path, _ = QFileDialog.getOpenFileName(self, caption, "", filters)
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            profile = SegmentProfile.from_dict(data)

            if seg_type == "intro":
                self._loaded_intro_profile = profile
                self._intro_start_idx = profile.scene_start
                self._intro_end_idx = profile.scene_end
                self.intro_status_label.setText(
                    f"INTRO Loaded (Sc {profile.scene_start}-{profile.scene_end}, {profile.duration:.1f}s)"
                )
                self.intro_status_label.setStyleSheet("color: #6cf; font-size: 7pt;")
                self.log_panel.log("SCENE", f"Loaded intro profile: {Path(path).name}")
                self._update_cut_buttons()
            else:
                self._loaded_outro_profile = profile
                self._outro_start_idx = profile.scene_start
                self._outro_end_idx = profile.scene_end
                self.outro_status_label.setText(
                    f"OUTRO Loaded (Sc {profile.scene_start}-{profile.scene_end}, {profile.duration:.1f}s)"
                )
                self.outro_status_label.setStyleSheet("color: #c6c; font-size: 7pt;")
                self.log_panel.log("SCENE", f"Loaded outro profile: {Path(path).name}")
                self._update_cut_buttons()

            self.profile_match_label.setText(f"[PROFILE] {seg_type.capitalize()} profile loaded.")
            self.profile_match_label.setStyleSheet("color: #8cf; font-size: 8pt;")

            # SF-6C: Enable Find buttons after manual load
            if self._scenes:
                self.find_intro_btn.setEnabled(self._loaded_intro_profile is not None)
                self.find_outro_btn.setEnabled(self._loaded_outro_profile is not None)

        except Exception as e:
            self.profile_match_label.setText(f"[ERROR] Failed to load profile: {e}")
            self.profile_match_label.setStyleSheet("color: #f66; font-size: 8pt;")
            self.log_panel.log("ERROR", f"Profile load failed: {e}")

    def _on_save_profile(self, seg_type: str) -> None:
        """Build and save a segment profile from the marked range."""
        if not self._scenes or not self._metadata:
            return

        # Get range boundaries
        if seg_type == "intro":
            start_idx = self._intro_start_idx
            end_idx = self._intro_end_idx
        else:
            start_idx = self._outro_start_idx
            end_idx = self._outro_end_idx

        if start_idx is None or end_idx is None:
            self.profile_match_label.setText(
                f"[PROFILE] Mark both start and end scenes first."
            )
            return

        # Ensure start <= end
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        # Collect scenes in range
        fps = self._metadata.real_fps
        selected = [s for s in self._scenes if start_idx <= s.index <= end_idx]
        if not selected:
            self.profile_match_label.setText(f"[PROFILE] No scenes in range {start_idx}-{end_idx}.")
            return

        time_start = selected[0].start_sec(fps)
        time_end = selected[-1].end_sec(fps)
        duration = time_end - time_start

        # Build summaries
        audio_summary = build_audio_summary(self._audio_regions, time_start, time_end)
        subtitle_summary = build_subtitle_summary(self._runtime_subtitles, time_start, time_end)
        scene_summary = build_scene_summary(self._scenes, fps, start_idx, end_idx)

        profile = SegmentProfile(
            type=seg_type,
            scene_start=start_idx,
            scene_end=end_idx,
            time_start=time_start,
            time_end=time_end,
            duration=duration,
            audio_summary=audio_summary,
            subtitle_summary=subtitle_summary,
            scene_summary=scene_summary,
        )

        save_profile(profile, self._video_name)

        # Update state
        if seg_type == "intro":
            self._loaded_intro_profile = profile
            self.intro_status_label.setText(
                f"Intro: Scene {start_idx} → {end_idx}  ({duration:.1f}s, {len(selected)} scenes)"
            )
            self.intro_status_label.setStyleSheet("color: #4f4; font-size: 8pt; font-weight: bold;")
        else:
            self._loaded_outro_profile = profile
            self.outro_status_label.setText(
                f"Outro: Scene {start_idx} → {end_idx}  ({duration:.1f}s, {len(selected)} scenes)"
            )
            self.outro_status_label.setStyleSheet("color: #f8f; font-size: 8pt; font-weight: bold;")

        self.profile_match_label.setText(f"[PROFILE] {seg_type.capitalize()} profile saved successfully.")
        self.profile_match_label.setStyleSheet("color: #4f4; font-size: 8pt; font-weight: bold;")
        self.log_panel.log("SCENE", f"Saved {seg_type} profile: Scenes {start_idx}-{end_idx}")

        # SF-6C: Enable Find buttons after save (profile now exists)
        if self._scenes:
            self.find_intro_btn.setEnabled(self._loaded_intro_profile is not None)
            self.find_outro_btn.setEnabled(self._loaded_outro_profile is not None)

    def _try_load_profiles(self) -> None:
        """Attempt to load existing intro/outro profiles for the current video."""
        if not self._video_name:
            return

        fps = self._metadata.real_fps if self._metadata else 23.976

        # Try loading intro profile
        intro = load_profile(self._video_name, "intro")
        if intro:
            self._loaded_intro_profile = intro
            self.intro_status_label.setText(
                f"Intro Profile Loaded  (Sc {intro.scene_start}-{intro.scene_end}, {intro.duration:.1f}s)"
            )
            self.intro_status_label.setStyleSheet("color: #6cf; font-size: 8pt;")
            self.log_panel.log("SCENE", f"Loaded intro profile: Scenes {intro.scene_start}-{intro.scene_end}")
            self._update_cut_buttons()
        else:
            self._loaded_intro_profile = None

        # Try loading outro profile
        outro = load_profile(self._video_name, "outro")
        if outro:
            self._loaded_outro_profile = outro
            self.outro_status_label.setText(
                f"Outro Profile Loaded  (Sc {outro.scene_start}-{outro.scene_end}, {outro.duration:.1f}s)"
            )
            self.outro_status_label.setStyleSheet("color: #c6c; font-size: 8pt;")
            self.log_panel.log("SCENE", f"Loaded outro profile: Scenes {outro.scene_start}-{outro.scene_end}")
            self._update_cut_buttons()
        else:
            self._loaded_outro_profile = None

        # SF-6C: Enable Find buttons when profiles are loaded
        if self._scenes:
            self.find_intro_btn.setEnabled(self._loaded_intro_profile is not None)
            self.find_outro_btn.setEnabled(self._loaded_outro_profile is not None)

    def _seek_to_scene(self, scene_idx: int) -> None:
        """Seek player to a scene and update playhead."""
        if scene_idx < 0 or scene_idx >= len(self._scenes):
            return

        scene = self._scenes[scene_idx]
        fps = self._metadata.real_fps if self._metadata else 23.976
        seek_ms = int(scene.start_sec(fps) * 1000)

        # Seek player to scene start
        self.media_player.setPosition(seek_ms)
        if self.media_player.playbackState() != QMediaPlayer.PlayingState:
            self.media_player.play()

        # Update UI state
        self._selected_index = scene_idx
        for i in range(self.timeline_layout.count()):
            w = self.timeline_layout.itemAt(i).widget()
            if isinstance(w, SceneBlock):
                w.set_selected(w._scene.index == scene_idx)

        self._update_playhead()

        self.log_panel.log(
            "SCENE",
            f"Clicked scene #{scene_idx} → seek to {self._format_time(seek_ms)}"
        )

    # --------------------------------------------------------------------------
    # SF-6C: Profile Match Suggestion Handlers
    # --------------------------------------------------------------------------

    def _on_find_intro(self) -> None:
        """Find intro match using loaded profile and highlight on timeline."""
        if not self._scenes or not self._metadata:
            self.profile_match_label.setText("[PROFILE] Load a video and detect scenes first.")
            return

        if not self._loaded_intro_profile:
            self.profile_match_label.setText("[PROFILE] No intro profile loaded. Load or create one first.")
            self.profile_match_label.setStyleSheet("color: #f66; font-size: 8pt;")
            return

        self.find_intro_btn.setEnabled(False)
        self.profile_match_label.setText("[PROFILE] Scanning for intro match...")
        self.profile_match_label.setStyleSheet("color: #ffcc00; font-size: 8pt;")
        self.log_panel.log("PROFILE", "Loaded intro profile")
        self.log_panel.log("PROFILE", "Scanning timeline for intro match")

        fps = self._metadata.real_fps
        start, end, score = suggest_matches(
            self._loaded_intro_profile, self._scenes, fps,
            self._audio_regions, self._runtime_subtitles
        )

        # Clear any existing outro highlight
        self._highlight_outro_range(None)

        if start is not None:
            self._profile_match_intro = (start, end, score)
            self._highlight_intro_range((start, end))
            confidence = int(score * 100)
            msg = f"Possible Intro Match  (Scenes {start}-{end}, Confidence: {confidence}%)"
            self.profile_match_label.setText(msg)
            self.profile_match_label.setStyleSheet("color: #ffcc00; font-size: 8pt; font-weight: bold;")
            self.log_panel.log("PROFILE", f"Best match: scenes {start}-{end} ({confidence}%)")
        else:
            self._profile_match_intro = None
            self._highlight_intro_range(None)
            msg = "No confident intro match found. Manual verification recommended."
            self.profile_match_label.setText(msg)
            self.profile_match_label.setStyleSheet("color: #888; font-size: 8pt;")
            self.log_panel.log("PROFILE", "No confident intro match found")

        self.find_intro_btn.setEnabled(True)

    def _on_find_outro(self) -> None:
        """Find outro match using loaded profile and highlight on timeline."""
        if not self._scenes or not self._metadata:
            self.profile_match_label.setText("[PROFILE] Load a video and detect scenes first.")
            return

        if not self._loaded_outro_profile:
            self.profile_match_label.setText("[PROFILE] No outro profile loaded. Load or create one first.")
            self.profile_match_label.setStyleSheet("color: #f66; font-size: 8pt;")
            return

        self.find_outro_btn.setEnabled(False)
        self.profile_match_label.setText("[PROFILE] Scanning for outro match...")
        self.profile_match_label.setStyleSheet("color: #ffcc00; font-size: 8pt;")
        self.log_panel.log("PROFILE", "Loaded outro profile")
        self.log_panel.log("PROFILE", "Scanning timeline for outro match")

        fps = self._metadata.real_fps
        start, end, score = suggest_matches(
            self._loaded_outro_profile, self._scenes, fps,
            self._audio_regions, self._runtime_subtitles
        )

        # Clear any existing intro highlight
        self._highlight_intro_range(None)

        if start is not None:
            self._profile_match_outro = (start, end, score)
            self._highlight_outro_range((start, end))
            confidence = int(score * 100)
            msg = f"Possible Outro Match  (Scenes {start}-{end}, Confidence: {confidence}%)"
            self.profile_match_label.setText(msg)
            self.profile_match_label.setStyleSheet("color: #ffcc00; font-size: 8pt; font-weight: bold;")
            self.log_panel.log("PROFILE", f"Best match: scenes {start}-{end} ({confidence}%)")
        else:
            self._profile_match_outro = None
            self._highlight_outro_range(None)
            msg = "No confident outro match found. Manual verification recommended."
            self.profile_match_label.setText(msg)
            self.profile_match_label.setStyleSheet("color: #888; font-size: 8pt;")
            self.log_panel.log("PROFILE", "No confident outro match found")

        self.find_outro_btn.setEnabled(True)

    def _highlight_intro_range(self, range_tuple: tuple[int, int] | None) -> None:
        """Highlight or clear intro suggestion range on timeline blocks."""
        self._highlighted_intro_range = range_tuple
        self._refresh_highlights()

    def _highlight_outro_range(self, range_tuple: tuple[int, int] | None) -> None:
        """Highlight or clear outro suggestion range on timeline blocks."""
        self._highlighted_outro_range = range_tuple
        self._refresh_highlights()

    def _refresh_highlights(self) -> None:
        """Refresh highlight styling on all timeline blocks."""
        intro_range = self._highlighted_intro_range
        outro_range = self._highlighted_outro_range

        for i in range(self.timeline_layout.count()):
            w = self.timeline_layout.itemAt(i).widget()
            if isinstance(w, SceneBlock):
                idx = w._scene.index
                
                # Check intro highlight
                if intro_range and intro_range[0] <= idx <= intro_range[1]:
                    w.set_suggested_intro(True)
                else:
                    w.set_suggested_intro(False)
                
                # Check outro highlight
                if outro_range and outro_range[0] <= idx <= outro_range[1]:
                    w.set_suggested_outro(True)
                else:
                    w.set_suggested_outro(False)


# ------------------------------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    win = SceneFlow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()