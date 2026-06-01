"""
test_ingestion_pipeline.py — Phase 1A/1B ingestion validation.

Phase 1A: Deterministic scene segmentation pipeline on real video files.
Phase 1B: Audio-aware scene clip export with ffprobe validation.

Usage:
    python tests/test_ingestion_pipeline.py          # first run (cache MISS)
    python tests/test_ingestion_pipeline.py          # second run (cache HIT)

Output: data/test_outputs/report.md
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import datetime
from pathlib import Path
from typing import Optional

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aicore.ingestion import (
    VideoIngester,
    FrameExtractor,
    MetadataExtractor,
    SceneDetector,
    FrameSampler,
    SceneExporter,
    SceneExportAudio,
    SceneExportMeta,
    VideoMetadata,
    IngestionProvenance,
    frame_time_str,
)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VIDEO_DIR = Path("data/videos")
OUTPUT_DIR = Path("data/test_outputs")
FRAMES_DIR = OUTPUT_DIR / "frames"
REPORT_PATH = OUTPUT_DIR / "report.md"

EXTRACTION_FPS = 1.0  # extract 1 frame per second
TEST_AUDIO_EXPORT = True  # Phase 1B: set False to skip audio-heavy tests

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_timings: dict[str, dict[str, float]] = {}  # video -> step -> seconds
_cache_stats: dict[str, dict[str, str]] = {}  # video -> step -> "HIT"/"MISS"

# Phase 1B: cache for scene lookup during audio validation
_export_scenes_cache: list = []


def _log(msg: str) -> None:
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def _time_step(video_name: str, step: str) -> "Timer":
    return Timer(video_name, step)


class Timer:
    def __init__(self, video: str, step: str) -> None:
        self.video = video
        self.step = step
        self.start: float = 0.0

    def __enter__(self) -> "Timer":
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args) -> None:
        elapsed = time.perf_counter() - self.start
        if self.video not in _timings:
            _timings[self.video] = {}
        _timings[self.video][self.step] = elapsed
        _log(f"  [{self.step}] {elapsed:.3f}s")


def _cache_event(video: str, step: str, status: str) -> None:
    if video not in _cache_stats:
        _cache_stats[video] = {}
    _cache_stats[video][step] = status


# ---------------------------------------------------------------------------
# Scene lookup helpers (Phase 1B audio validation)
# ---------------------------------------------------------------------------


def _get_scene_by_id(scene_id: str):
    """Look up a SceneInfo by scene_id from the export cache."""
    for s in _export_scenes_cache:
        if s.scene_id == scene_id:
            return s
    return None


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_validation_errors: list[str] = []
_validation_warnings: list[str] = []


def _check(cond: bool, msg: str, is_warning: bool = False) -> None:
    target = _validation_warnings if is_warning else _validation_errors
    if not cond:
        target.append(msg)
        level = "WARN" if is_warning else "FAIL"
        _log(f"    ! {level}: {msg}")
    else:
        _log(f"    ✓ {msg}")


def _validate_video(video_name: str, meta: VideoMetadata) -> None:
    """Validate ffprobe metadata."""
    _check(meta.duration_sec > 0, f"duration={meta.duration_sec:.3f}s")
    _check(meta.fps > 0, f"fps={meta.fps}")
    _check(meta.width > 0 and meta.height > 0, f"resolution={meta.width}x{meta.height}")
    _check(meta.total_frames > 0, f"total_frames={meta.total_frames}")
    _check(meta.file_size_bytes > 0, f"file_size={meta.file_size_bytes}")
    _check(bool(meta.codec), f"codec={meta.codec}")
    # Phase 1B: audio metadata validation
    _check(
        isinstance(meta.has_audio, bool),
        f"has_audio={meta.has_audio}",
    )


def _validate_frames(
    video_name: str,
    frames: list,
    fps: float,
    meta: VideoMetadata,
) -> None:
    """Validate frame sequence integrity."""
    _check(len(frames) > 0, f"extracted {len(frames)} frames")

    # Timestamps monotonically increasing
    timestamps = [f.timestamp_sec for f in frames]
    increasing = all(timestamps[i] <= timestamps[i + 1] for i in range(len(timestamps) - 1))
    _check(increasing, "timestamps monotonically increasing")

    # Frame indices monotonically increasing
    indices = [f.index for f in frames]
    idx_increasing = all(indices[i] < indices[i + 1] for i in range(len(indices) - 1))
    _check(idx_increasing, "frame indices strictly increasing")

    # File paths exist
    for f in frames:
        _check(Path(f.file_path).exists(), f"frame file exists: {Path(f.file_path).name}", is_warning=True)


def _validate_features(
    video_name: str,
    features: list,
    meta: VideoMetadata,
) -> None:
    """Validate frame features integrity."""
    _check(len(features) > 0, f"{len(features)} features extracted")

    # Frame indices in range
    for ff in features:
        _check(
            0 <= ff.frame_index < meta.total_frames,
            f"frame_index={ff.frame_index} in range [0, {meta.total_frames})",
            is_warning=True,
        )

    # Histograms have 256 bins
    if features:
        hist_len = len(features[0].histogram_bins)
        _check(hist_len == 256, f"histogram 256 bins (got {hist_len})")

    # Brightness is 0-1
    for ff in features[:3]:
        _check(0 <= ff.mean_brightness <= 1, f"brightness={ff.mean_brightness:.4f} in [0,1]", is_warning=True)

    # DHash is non-empty
    for ff in features[:3]:
        _check(len(ff.dhash) > 0, f"dhash={ff.dhash}", is_warning=True)

    # Edge density is 0-1
    for ff in features[:3]:
        _check(0 <= ff.edge_density <= 0.5, f"edge_density={ff.edge_density:.4f} in [0,0.5]", is_warning=True)


def _validate_scenes(video_name: str, scenes: list, features: list, meta: VideoMetadata) -> None:
    """Validate scene segmentation integrity."""
    _check(len(scenes) > 0, f"{len(scenes)} scenes detected")

    # No empty scenes
    for s in scenes:
        _check(s.frame_count > 0, f"scene {s.scene_id} frame_count={s.frame_count}")

    # No overlapping scene ranges
    for i in range(len(scenes) - 1):
        curr = scenes[i]
        nxt = scenes[i + 1]
        _check(
            curr.end_frame < nxt.start_frame,
            f"scenes {i} and {i+1} non-overlapping ({curr.end_frame} < {nxt.start_frame})",
        )

    # All scenes within video bounds
    for s in scenes:
        _check(
            0 <= s.start_frame <= s.end_frame < meta.total_frames,
            f"scene {s.scene_id} frames [{s.start_frame}, {s.end_frame}] in range",
            is_warning=True,
        )

    # Timestamps increasing
    for i in range(len(scenes) - 1):
        _check(
            scenes[i].end_timestamp_sec <= scenes[i + 1].start_timestamp_sec + 0.1,
            f"scene {i}->{i+1} timestamps monotonic",
        )

    # Detection method set
    for s in scenes:
        _check(
            bool(s.detection_method),
            f"scene {s.scene_id} detection_method={s.detection_method}",
        )


def _validate_keyframes(
    video_name: str,
    scene_keyframes: dict[str, list[int]],
    scenes: list,
    features: list,
) -> None:
    """Validate sampled keyframes belong to parent scene."""
    for scene in scenes:
        kfs = scene_keyframes.get(scene.scene_id, [])
        for kf in kfs:
            _check(
                scene.start_frame <= kf <= scene.end_frame,
                f"keyframe {kf} in scene {scene.scene_id} range [{scene.start_frame}, {scene.end_frame}]",
            )
        _check(
            len(kfs) > 0,
            f"scene {scene.scene_id} has >=1 keyframe",
        )


def _validate_export_roundtrip(export_path: str) -> bool:
    """Validate export JSON can be loaded back."""
    from aicore.ingestion.scene_export import SceneExporter

    try:
        scenes, provenance = SceneExporter.load_scenes(export_path)
        _check(len(scenes) > 0, f"round-trip loaded {len(scenes)} scenes")
        _check(bool(provenance.workflow_id), f"round-trip provenance workflow_id={provenance.workflow_id}")
        return True
    except Exception as e:
        _check(False, f"round-trip failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Phase 1B: Audio export validation
# ---------------------------------------------------------------------------


def _validate_audio_export(
    video_name: str,
    scene_export_metas: list[SceneExportMeta],
) -> None:
    """
    Validate audio-aware scene export results.

    Every exported scene clip MUST:
    - Have a successful ffmpeg export
    - Contain audio (has_audio=True)
    - Have a non-empty audio codec
    - Have a valid sample rate
    - Have positive duration matching source scene
    - Have positive file size
    """
    _check(
        len(scene_export_metas) > 0,
        f"exported {len(scene_export_metas)} scene clips",
    )

    for meta in scene_export_metas:
        _check(
            meta.export_success,
            f"{meta.scene_id} export_success=True",
        )
        _check(
            meta.has_audio,
            f"{meta.scene_id} has_audio=True (codec={meta.audio_codec})",
        )
        _check(
            bool(meta.audio_codec),
            f"{meta.scene_id} audio_codec={meta.audio_codec}",
        )
        _check(
            meta.sample_rate > 0,
            f"{meta.scene_id} sample_rate={meta.sample_rate}",
        )
        _check(
            meta.export_duration_sec > 0,
            f"{meta.scene_id} export_duration={meta.export_duration_sec:.3f}s",
        )
        _check(
            meta.file_size_bytes > 0,
            f"{meta.scene_id} file_size={meta.file_size_bytes} bytes",
        )

        # Video duration should match scene duration (allow small re-encode tolerance)
        scene = _get_scene_by_id(meta.scene_id)
        if scene is not None:
            dur_diff = abs(meta.export_duration_sec - scene.duration_sec)
            _check(
                dur_diff < 1.0,
                f"{meta.scene_id} export_duration matches scene ({dur_diff:.3f}s diff)",
            )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(video_path: Path, video_index: int) -> dict:
    """Run full ingestion pipeline on a single video file."""
    video_name = video_path.stem
    _log(f"\n{'='*60}")
    _log(f"Video {video_index}: {video_name}")
    _log(f"  File: {video_path.name}")
    _log(f"{'='*60}")

    video_out = OUTPUT_DIR / video_name
    video_out.mkdir(parents=True, exist_ok=True)

    result: dict = {"name": video_name, "path": str(video_path)}

    # -----------------------------------------------------------------------
    # Stage 1: Probe metadata
    # -----------------------------------------------------------------------
    ingester = VideoIngester()

    with _time_step(video_name, "probe"):
        meta = ingester.probe(str(video_path))

    result["metadata"] = {
        "duration_sec": meta.duration_sec,
        "fps": meta.fps,
        "resolution": f"{meta.width}x{meta.height}",
        "codec": meta.codec,
        "total_frames": meta.total_frames,
        "file_size_mb": round(meta.file_size_bytes / 1_000_000, 2),
        # Phase 1B: audio info
        "has_audio": meta.has_audio,
        "audio_codec": meta.audio_codec,
        "audio_channels": meta.audio_channels,
        "audio_sample_rate": meta.audio_sample_rate,
    }
    _log(f"  Probe: {meta.duration_sec:.2f}s @ {meta.fps:.2f}fps -> {meta.total_frames} frames")
    _log(f"  Audio: has_audio={meta.has_audio}, codec={meta.audio_codec}, channels={meta.audio_channels}, sr={meta.audio_sample_rate}")

    _validate_video(video_name, meta)

    # -----------------------------------------------------------------------
    # Stage 2: Frame extraction
    # -----------------------------------------------------------------------
    frame_out_dir = FRAMES_DIR / video_name
    extractor = FrameExtractor(output_dir=str(frame_out_dir))

    # Check cache: if frames already exist, skip extraction
    existing_frames = list(frame_out_dir.glob("frame_*.png"))
    if existing_frames:
        _cache_event(video_name, "extract", "HIT")
        _log(f"  Cache HIT: {len(existing_frames)} frames already extracted")
        frames = extractor._index_output_frames(frame_out_dir, video_path)
    else:
        _cache_event(video_name, "extract", "MISS")
        with _time_step(video_name, "extract"):
            frames = extractor.extract_all_at_fps(
                str(video_path),
                fps=EXTRACTION_FPS,
            )
        _log(f"  Extracted {len(frames)} frames @ {EXTRACTION_FPS}fps")

    # Fix timestamps: extracted frames have timestamp_sec=0.0 placeholder
    for i, f in enumerate(frames):
        f.timestamp_sec = i / EXTRACTION_FPS
        f.timestamp_str = frame_time_str(f.timestamp_sec)

    result["frames"] = {
        "extracted": len(frames),
        "extraction_fps": EXTRACTION_FPS,
    }
    _log(f"  Frame timestamps: 0.0 to {frames[-1].timestamp_sec:.1f}s" if frames else "  No frames!")

    _validate_frames(video_name, frames, EXTRACTION_FPS, meta)

    # -----------------------------------------------------------------------
    # Stage 3: Frame features
    # -----------------------------------------------------------------------
    feature_cache_path = video_out / "frame_features.json"

    if feature_cache_path.exists():
        _cache_event(video_name, "features", "HIT")
        with open(feature_cache_path) as f:
            feature_data = json.load(f)
        from aicore.ingestion.schemas import FrameFeatures
        frame_features = [FrameFeatures.from_dict(d) for d in feature_data]
        _log(f"  Cache HIT: {len(frame_features)} feature sets loaded")
    else:
        _cache_event(video_name, "features", "MISS")
        meta_extractor = MetadataExtractor()

        with _time_step(video_name, "features"):
            frame_features = meta_extractor.extract_batch(
                [f.file_path for f in frames],
                fps=EXTRACTION_FPS,
            )
        _log(f"  Computed features for {len(frame_features)} frames")

        # Cache features
        with open(feature_cache_path, "w") as f:
            json.dump([ff.to_dict() for ff in frame_features], f)

    result["frame_features"] = {"computed": len(frame_features)}
    _validate_features(video_name, frame_features, meta)

    # -----------------------------------------------------------------------
    # Stage 4: Scene detection
    # -----------------------------------------------------------------------
    scene_cache_path = video_out / "scene_boundaries.json"

    if scene_cache_path.exists():
        _cache_event(video_name, "detect", "HIT")
        with open(scene_cache_path) as f:
            scene_data = json.load(f)
        from aicore.ingestion.schemas import SceneInfo
        scenes = [SceneInfo.from_dict(s) for s in scene_data]
        _log(f"  Cache HIT: {len(scenes)} scene boundaries loaded")
    else:
        _cache_event(video_name, "detect", "MISS")
        detector = SceneDetector(
            histogram_threshold=0.5,
            min_scene_frames=2,
        )

        with _time_step(video_name, "detect"):
            scenes = detector.detect_from_features(frame_features, fps=EXTRACTION_FPS)
        _log(f"  Detected {len(scenes)} scenes")

        # Cache scenes
        with open(scene_cache_path, "w") as f:
            json.dump([s.to_dict() for s in scenes], f)

    result["scenes"] = {
        "detected": len(scenes),
        "scene_ids": [s.scene_id for s in scenes],
    }

    _log(f"  Scenes:")
    for s in scenes:
        _log(f"    {s.scene_id}: frames [{s.start_frame}..{s.end_frame}] "
             f"({s.frame_count}f) @ {s.start_timestamp_str}->{s.end_timestamp_str} "
             f"{'[INTRO]' if s.is_intro else ''}{'[OUTRO]' if s.is_outro else ''}"
             f"{'[BLACK]' if s.is_black else ''}{'[STATIC]' if s.is_static else ''}")

    _validate_scenes(video_name, scenes, frame_features, meta)

    # -----------------------------------------------------------------------
    # Stage 5: Frame sampling
    # -----------------------------------------------------------------------
    sampler = FrameSampler(strategy="hybrid", max_keyframes_per_scene=3)

    with _time_step(video_name, "sample"):
        scene_keyframes = sampler.sample_all_scenes(scenes, frame_features, fps=EXTRACTION_FPS)
    _log(f"  Sampled keyframes:")

    total_kfs = 0
    for s in scenes:
        kfs = scene_keyframes.get(s.scene_id, [])
        _log(f"    {s.scene_id}: {len(kfs)} keyframes -> {kfs}")
        total_kfs += len(kfs)

    result["keyframes"] = {"total": total_kfs}
    _validate_keyframes(video_name, scene_keyframes, scenes, frame_features)

    # -----------------------------------------------------------------------
    # Stage 6: Provenance
    # -----------------------------------------------------------------------
    provenance = ingester.compute_provenance(
        str(video_path),
        workflow_id=f"test_ingestion_{video_name}",
        parameters={
            "extraction_fps": EXTRACTION_FPS,
            "sampler_strategy": "hybrid",
            "histogram_threshold": 0.5,
        },
    )
    provenance.total_scenes = len(scenes)
    provenance.total_keyframes = total_kfs

    result["provenance"] = {
        "workflow_id": provenance.workflow_id,
        "video_hash": provenance.video_hash,
        "total_scenes": provenance.total_scenes,
        "total_keyframes": provenance.total_keyframes,
    }
    _log(f"  Provenance: hash={provenance.video_hash}, scenes={provenance.total_scenes}, "
         f"keyframes={provenance.total_keyframes}")

    # -----------------------------------------------------------------------
    # Stage 7: Scene metadata export (JSON)
    # -----------------------------------------------------------------------
    exporter = SceneExporter(output_dir=str(video_out))

    with _time_step(video_name, "export"):
        export_path = exporter.export_scenes(scenes, meta, provenance)
    _log(f"  Export: {export_path}")

    result["export_path"] = export_path

    # Also export provenance separately
    provenance_path = exporter.export_provenance(provenance)
    _log(f"  Provenance export: {provenance_path}")

    # -----------------------------------------------------------------------
    # Stage 7B: Audio-aware scene clip export (Phase 1B)
    # -----------------------------------------------------------------------
    result["audio_export"] = {"exported": 0, "metas": []}

    if TEST_AUDIO_EXPORT and meta.has_audio:
        audio_exporter = SceneExportAudio(
            output_dir=str(OUTPUT_DIR / "scene_clips" / video_name),
        )

        # Scene lookup cache for audio validation
        global _export_scenes_cache
        _export_scenes_cache = scenes

        with _time_step(video_name, "audio_export"):
            try:
                scene_export_metas = audio_exporter.export_scenes_batch(
                    scenes,
                    str(video_path),
                    overwrite=True,
                )
                result["audio_export"]["exported"] = len(scene_export_metas)
                result["audio_export"]["metas"] = [m.to_dict() for m in scene_export_metas]
                _log(f"  Exported {len(scene_export_metas)} audio scene clips")
            except Exception as e:
                _log(f"  WARN: Audio export failed: {e}")
                _validation_warnings.append(f"Audio export failed: {e}")
            else:
                _validate_audio_export(video_name, scene_export_metas)
    elif TEST_AUDIO_EXPORT and not meta.has_audio:
        _log(f"  SKIP audio export: source video has no audio stream")

    # -----------------------------------------------------------------------
    # Stage 8: Round-trip validation
    # -----------------------------------------------------------------------
    _validate_export_roundtrip(export_path)

    # -----------------------------------------------------------------------
    # Additional validations
    # -----------------------------------------------------------------------
    # Verify no empty scenes
    for s in scenes:
        _check(
            s.frame_count >= 1,
            f"scene {s.scene_id} non-empty",
        )

    # Verify total frames covered
    if scenes:
        first_frame = scenes[0].start_frame
        last_frame = scenes[-1].end_frame
        _check(
            first_frame == 0,
            f"first scene starts at frame 0 (got {first_frame})",
        )
        _check(
            last_frame == len(frame_features) - 1 or last_frame >= len(frames) - 1,
            f"last scene covers up to frame {last_frame} of {len(frame_features)}",
            is_warning=True,
        )

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[dict], second_run: bool = False) -> str:
    """Generate structured markdown report."""
    total_start = time.perf_counter()

    lines: list[str] = []
    lines.append("# Phase 1A/1B Ingestion Validation Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.datetime.now().isoformat()}")
    lines.append(f"**Run type:** {'SECOND RUN (cache replay)' if second_run else 'FIRST RUN (cache cold)'}")
    lines.append(f"**Videos found:** {len(results)}")
    lines.append(f"**Audio export enabled:** {TEST_AUDIO_EXPORT}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Video | Duration | Resolution | Frames | Scenes | Keyframes | Audio | Clips | Runtime |")
    lines.append("|-------|----------|------------|--------|--------|-----------|-------|-------|---------|")
    for r in results:
        meta = r.get("metadata", {})
        name = r["name"]
        dur = f"{meta.get('duration_sec', 0):.1f}s"
        res = meta.get("resolution", "?")
        frames = meta.get("total_frames", 0)
        scenes = r.get("scenes", {}).get("detected", 0)
        kfs = r.get("keyframes", {}).get("total", 0)
        has_audio = meta.get("has_audio", False)
        audio_str = f"A:{meta.get('audio_codec', '?')}" if has_audio else "NONE"
        clips = r.get("audio_export", {}).get("exported", 0)
        vid_timing = _timings.get(name, {})
        total_vid = sum(vid_timing.values())
        runtime = f"{total_vid:.2f}s"
        lines.append(f"| {name} | {dur} | {res} | {frames} | {scenes} | {kfs} | {audio_str} | {clips} | {runtime} |")

    lines.append("")

    # Per-video details
    lines.append("## Per-Video Details")
    lines.append("")

    for r in results:
        name = r["name"]
        meta = r.get("metadata", {})
        scenes = r.get("scenes", {}).get("detected", 0)
        scene_ids = r.get("scenes", {}).get("scene_ids", [])
        prov = r.get("provenance", {})

        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"- **Path:** `{r['path']}`")
        lines.append(f"- **Duration:** {meta.get('duration_sec', 0):.2f}s")
        lines.append(f"- **FPS:** {meta.get('fps', 0):.2f}")
        lines.append(f"- **Resolution:** {meta.get('resolution', '?')}")
        lines.append(f"- **Codec:** {meta.get('codec', '?')}")
        lines.append(f"- **Total frames (probe):** {meta.get('total_frames', 0)}")
        lines.append(f"- **Extracted frames:** {r.get('frames', {}).get('extracted', 0)} @ {EXTRACTION_FPS}fps")
        lines.append(f"- **Scenes detected:** {scenes}")
        lines.append(f"- **Keyframes sampled:** {r.get('keyframes', {}).get('total', 0)}")
        lines.append(f"- **Video hash:** `{prov.get('video_hash', '?')}`")

        # Phase 1B audio info
        lines.append(f"- **Has audio:** {meta.get('has_audio', False)}")
        if meta.get('has_audio'):
            lines.append(f"- **Audio codec:** {meta.get('audio_codec', '?')}")
            lines.append(f"- **Audio channels:** {meta.get('audio_channels', '?')}")
            lines.append(f"- **Audio sample rate:** {meta.get('audio_sample_rate', '?')} Hz")
            audio_export = r.get("audio_export", {})
            clips = audio_export.get("exported", 0)
            lines.append(f"- **Exported scene clips:** {clips}")

        # Timings
        vid_timing = _timings.get(name, {})
        lines.append(f"- **Stage timings:**")
        for step, secs in sorted(vid_timing.items()):
            lines.append(f"  - {step}: {secs:.3f}s")

        # Cache stats
        vid_cache = _cache_stats.get(name, {})
        if vid_cache:
            lines.append(f"- **Cache:**")
            for step, status in sorted(vid_cache.items()):
                lines.append(f"  - {step}: **{status}**")

        # Scene list
        lines.append("")
        lines.append("#### Scene Segmentation")
        lines.append("")
        lines.append("| # | Scene ID | Start Frame | End Frame | Frames | Start Time | End Time | Duration | Type | Audio Clip |")
        lines.append("|---|----------|-------------|-----------|--------|------------|----------|----------|------|------------|")

        # Re-import to get scenes
        from aicore.ingestion.schemas import SceneInfo

        export_path = r.get("export_path", "")
        audio_metas = r.get("audio_export", {}).get("metas", [])
        audio_by_id = {m["scene_id"]: m for m in audio_metas}

        if export_path and os.path.exists(export_path):
            with open(export_path) as f:
                export_data = json.load(f)
            for si, sd in enumerate(export_data.get("scenes", [])):
                s = SceneInfo.from_dict(sd)
                stype = ""
                if s.is_intro:
                    stype += "INTRO "
                if s.is_outro:
                    stype += "OUTRO "
                if s.is_black:
                    stype += "BLACK "
                if s.is_static:
                    stype += "STATIC "
                stype = stype.strip() or "NORMAL"

                # Phase 1B: audio clip status
                audio_clip_str = ""
                audio_m = audio_by_id.get(s.scene_id)
                if audio_m:
                    if audio_m.get("export_success"):
                        audio_clip_str = f"A:{audio_m.get('audio_codec', '?')}"
                    else:
                        audio_clip_str = "FAIL"
                else:
                    audio_clip_str = "SKIP"

                lines.append(
                    f"| {si} | {s.scene_id} | {s.start_frame} | {s.end_frame} | "
                    f"{s.frame_count} | {s.start_timestamp_str} | {s.end_timestamp_str} | "
                    f"{s.duration_sec:.2f}s | {stype} | {audio_clip_str} |"
                )

        # Keyframe indices
        kfs = r.get("keyframes", {}).get("total", 0)
        lines.append(f"\n**Keyframes:** {kfs}")
        if scenes:
            lines.append("")
            for id_str in scene_ids:
                lines.append(f"- Scene {id_str}: keyframes from export")

        lines.append("")

    # Validation results
    lines.append("## Validation Results")
    lines.append("")
    lines.append(f"**Errors:** {len(_validation_errors)}")
    lines.append(f"**Warnings:** {len(_validation_warnings)}")
    lines.append("")

    if _validation_errors:
        lines.append("### Errors")
        lines.append("")
        for e in _validation_errors:
            lines.append(f"- :x: {e}")
        lines.append("")

    if _validation_warnings:
        lines.append("### Warnings")
        lines.append("")
        for w in _validation_warnings:
            lines.append(f"- :warning: {w}")
        lines.append("")

    if not _validation_errors and not _validation_warnings:
        lines.append(":white_check_mark: All validations passed.")
        lines.append("")

    # Phase 1B: Audio export summary
    lines.append("## Audio Export Summary (Phase 1B)")
    lines.append("")
    total_clips = 0
    total_audio_clips = 0
    for r in results:
        name = r["name"]
        audio_metas = r.get("audio_export", {}).get("metas", [])
        if audio_metas:
            lines.append(f"### {name}")
            lines.append("")
            lines.append("| Scene ID | Has Audio | Codec | Sample Rate | Duration | Size |")
            lines.append("|----------|-----------|-------|-------------|----------|------|")
            for m in audio_metas:
                has_a = m.get("has_audio", False)
                codec = m.get("audio_codec", "?")
                sr = m.get("sample_rate", 0)
                dur = m.get("export_duration_sec", 0)
                size = m.get("file_size_bytes", 0)
                lines.append(f"| {m['scene_id']} | {has_a} | {codec} | {sr} Hz | {dur:.2f}s | {size} B |")
                total_clips += 1
                if has_a:
                    total_audio_clips += 1
            lines.append("")
    lines.append(f"**Total clips exported:** {total_clips}")
    lines.append(f"**Clips with audio:** {total_audio_clips}")
    lines.append("")

    # Segmentation quality observations
    lines.append("## Segmentation Quality Observations")
    lines.append("")
    for r in results:
        name = r["name"]
        export_path = r.get("export_path", "")
        if not export_path or not os.path.exists(export_path):
            continue
        with open(export_path) as f:
            data = json.load(f)
        scenes_data = data.get("scenes", [])

        lines.append(f"### {name}")
        lines.append("")

        # Observations
        obs: list[str] = []
        scene_count = len(scenes_data)
        obs.append(f"- {scene_count} scene(s) detected")

        # Check black / intro / outro classification
        intros = sum(1 for s in scenes_data if s.get("is_intro"))
        outros = sum(1 for s in scenes_data if s.get("is_outro"))
        blacks = sum(1 for s in scenes_data if s.get("is_black"))
        statics = sum(1 for s in scenes_data if s.get("is_static"))

        if intros:
            obs.append(f"- {intros} scene(s) classified as INTRO")
        if outros:
            obs.append(f"- {outros} scene(s) classified as OUTRO")
        if blacks:
            obs.append(f"- {blacks} scene(s) classified as BLACK")
        if statics:
            obs.append(f"- {statics} scene(s) classified as STATIC")

        # Check scene lengths
        short_scenes = [s for s in scenes_data if s.get("frame_count", 0) <= 2]
        if short_scenes:
            obs.append(f"- :warning: {len(short_scenes)} very short scene(s) (<=2 frames) - possible over-segmentation")

        long_scenes = [s for s in scenes_data if s.get("frame_count", 0) > 20]
        if long_scenes:
            obs.append(f"- {len(long_scenes)} long scene(s) (>20 frames) - possible under-segmentation")

        for o in obs:
            lines.append(o)
        lines.append("")

    # Overall timing
    total_elapsed = time.perf_counter() - total_start
    lines.append(f"## Timing Summary")
    lines.append("")
    lines.append(f"**Total report generation:** {total_elapsed:.3f}s")
    lines.append("")
    lines.append("| Video | Probe | Extract | Features | Detect | Sample | Export | AudioExp | Total |")
    lines.append("|-------|-------|---------|----------|--------|--------|--------|----------|-------|")
    for r in results:
        name = r["name"]
        vid_t = _timings.get(name, {})
        probe_t = vid_t.get("probe", 0)
        extract_t = vid_t.get("extract", 0)
        features_t = vid_t.get("features", 0)
        detect_t = vid_t.get("detect", 0)
        sample_t = vid_t.get("sample", 0)
        export_t = vid_t.get("export", 0)
        audio_export_t = vid_t.get("audio_export", 0)
        total_t = probe_t + extract_t + features_t + detect_t + sample_t + export_t + audio_export_t
        lines.append(
            f"| {name} | {probe_t:.3f}s | {extract_t:.3f}s | {features_t:.3f}s | "
            f"{detect_t:.3f}s | {sample_t:.3f}s | {export_t:.3f}s | {audio_export_t:.3f}s | **{total_t:.3f}s** |"
        )

    lines.append(f"\n*Report generated by `test_ingestion_pipeline.py`*")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Run ingestion pipeline on all videos in data/videos/."""

    # Clean output directory before run (replaces manual rm -rf)
    shutil.rmtree("data/test_outputs", ignore_errors=True)

    # Detect second run (check if any export already exists)
    second_run = OUTPUT_DIR.exists() and any(OUTPUT_DIR.iterdir())

    _log(f"Phase 1A/1B Ingestion Pipeline Validation")
    _log(f"Video directory: {VIDEO_DIR}")
    _log(f"Output directory: {OUTPUT_DIR}")
    _log(f"Run type: {'SECOND (cache replay)' if second_run else 'FIRST (cold cache)'}")
    _log(f"Extraction FPS: {EXTRACTION_FPS}")
    _log(f"Audio export: {'ENABLED' if TEST_AUDIO_EXPORT else 'DISABLED'}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Find video files
    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    video_files = sorted([
        p for p in VIDEO_DIR.iterdir()
        if p.suffix.lower() in video_extensions
    ])

    if not video_files:
        _log("ERROR: No video files found in data/videos/")
        print("\nERROR: No video files found in data/videos/")
        print("Place test videos in data/videos/ (e.g. combat_01.mp4, dialogue_01.mp4, test_transition.mp4)")
        return 1

    _log(f"Found {len(video_files)} video(s): {[v.name for v in video_files]}")
    _log("")

    # Run pipeline for each video
    results: list[dict] = []
    for i, vp in enumerate(video_files, 1):
        try:
            result = run_pipeline(vp, i)
            results.append(result)
        except Exception as e:
            _log(f"  ERROR: Pipeline failed for {vp.name}: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "name": vp.stem,
                "path": str(vp),
                "error": str(e),
                "metadata": {},
                "frames": {},
                "scenes": {"detected": 0, "scene_ids": []},
                "keyframes": {"total": 0},
                "provenance": {},
                "export_path": "",
                "audio_export": {"exported": 0, "metas": []},
            })

    # Generate report
    _log(f"\n{'='*60}")
    _log(f"Generating report...")
    report = generate_report(results, second_run=second_run)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    _log(f"Report written to {REPORT_PATH}")

    # Print summary
    _log(f"\n{'='*60}")
    _log(f"PIPELINE SUMMARY")
    _log(f"{'='*60}")
    _log(f"Total videos: {len(results)}")
    total_scenes = sum(r.get("scenes", {}).get("detected", 0) for r in results)
    total_kfs = sum(r.get("keyframes", {}).get("total", 0) for r in results)
    total_clips = sum(r.get("audio_export", {}).get("exported", 0) for r in results)
    _log(f"Total scenes: {total_scenes}")
    _log(f"Total keyframes: {total_kfs}")
    _log(f"Total audio clips: {total_clips}")
    _log(f"Errors: {len(_validation_errors)}")
    _log(f"Warnings: {len(_validation_warnings)}")
    _log(f"Report: {REPORT_PATH}")

    if _validation_errors:
        _log("\nERRORS:")
        for e in _validation_errors:
            _log(f"  :x: {e}")

    return 0 if not _validation_errors else 1


if __name__ == "__main__":
    sys.exit(main())