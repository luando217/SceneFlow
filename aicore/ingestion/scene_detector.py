"""
SceneDetector — heuristic scene boundary detection.

Detection methods (all deterministic, no ML):
1. Color histogram correlation — detect cuts when histogram diff spikes
2. Optical flow magnitude — detect slow transitions / fades
3. Black frame detection — detect fade-to-black scene boundaries
4. Keyframe-based — use I-frame positions as cues

All methods produce SceneInfo segments with detection_method provenance.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from .schemas import FrameFeatures, SceneInfo


class SceneDetector:
    """
    Deterministic scene boundary detector.

    Configurable thresholds for sensitivity.
    Supports multiple detection strategies.
    """

    def __init__(
        self,
        histogram_threshold: float = 0.5,    # chi-squared threshold for cut
        motion_threshold: float = 0.3,        # motion magnitude threshold for transition
        black_frame_ratio: float = 0.95,      # black frame detection ratio
        min_scene_frames: int = 2,            # minimum frames per scene
        fuse_overlap: bool = True,            # merge overlapping detections
    ) -> None:
        self._hist_thresh = histogram_threshold
        self._motion_thresh = motion_threshold
        self._black_ratio = black_frame_ratio
        self._min_frames = min_scene_frames
        self._fuse = fuse_overlap

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_from_features(
        self,
        frame_features: list[FrameFeatures],
        fps: float = 1.0,
    ) -> list[SceneInfo]:
        """
        Detect scene boundaries from frame features.
        Uses histogram diff as primary signal, motion as secondary.

        Returns list of SceneInfo in temporal order.
        """
        if not frame_features or len(frame_features) < self._min_frames:
            return []

        boundaries = self._detect_cuts(frame_features)
        boundaries = self._merge_nearby(boundaries, frame_features)

        scenes = self._build_scenes(boundaries, frame_features, fps)
        scenes = self._classify_scenes(scenes, frame_features)
        return scenes

    def detect_from_histograms(
        self,
        histograms: list[list[int]],
        timestamps: list[float],
        fps: float = 1.0,
    ) -> list[SceneInfo]:
        """
        Detect scenes from histogram data only (no full features).
        Useful when only histogram data is available (e.g. cached).
        """
        if not histograms or len(histograms) < self._min_frames:
            return []

        diffs: list[float] = [0.0]
        for i in range(1, len(histograms)):
            diff = self._chi_squared(histograms[i], histograms[i - 1])
            diffs.append(diff)

        boundaries: list[int] = [0]
        for i in range(1, len(diffs)):
            if diffs[i] > self._hist_thresh:
                if i - boundaries[-1] >= self._min_frames:
                    boundaries.append(i)
        if boundaries[-1] != len(histograms) - 1:
            boundaries.append(len(histograms) - 1)

        scenes: list[SceneInfo] = []
        for j in range(len(boundaries) - 1):
            start = boundaries[j]
            end_excl = boundaries[j + 1]
            last_feat_idx = min(end_excl - 1, len(histograms) - 1)
            scenes.append(SceneInfo(
                scene_id=f"scene_{j:04d}",
                index=j,
                start_frame=start,
                end_frame=end_excl - 1,
                start_timestamp_sec=timestamps[start] if start < len(timestamps) else 0.0,
                end_timestamp_sec=timestamps[last_feat_idx] if last_feat_idx >= 0 and last_feat_idx < len(timestamps) else 0.0,
                duration_sec=(
                    timestamps[last_feat_idx] - timestamps[start]
                    if start < len(timestamps) and last_feat_idx < len(timestamps)
                    else 0.0
                ),
                start_timestamp_str="",
                end_timestamp_str="",
                frame_count=end_excl - start,
                detection_method="color_histogram",
            ))
        return scenes

    # ------------------------------------------------------------------
    # Cut detection
    # ------------------------------------------------------------------

    def _detect_cuts(self, features: list[FrameFeatures]) -> list[int]:
        """Find scene boundary indices using histogram + motion signals."""
        boundaries: list[int] = [0]

        for i in range(1, len(features)):
            prev = features[i - 1]
            curr = features[i]

            # Primary: histogram difference
            hist_diff = curr.histogram_diff_to_prev

            # Secondary: motion / black frame
            is_cut = False

            # Hard cut: histogram spike
            if hist_diff > self._hist_thresh:
                is_cut = True

            # Black-to-scene or scene-to-black transition
            if prev.is_black_frame != curr.is_black_frame:
                is_cut = True

            # Fade: motion spike without histogram spike
            if curr.motion_magnitude > self._motion_thresh and prev.motion_magnitude < self._motion_thresh * 0.5:
                is_cut = True

            if is_cut and (i - boundaries[-1]) >= self._min_frames:
                boundaries.append(i)

        if boundaries[-1] != len(features) - 1:
            boundaries.append(len(features) - 1)

        return boundaries

    def _merge_nearby(
        self,
        boundaries: list[int],
        features: list[FrameFeatures],
    ) -> list[int]:
        """Merge scene boundaries that are very close together."""
        if not self._fuse or len(boundaries) < 3:
            return boundaries

        merged: list[int] = [boundaries[0]]
        for i in range(1, len(boundaries) - 1):
            gap = boundaries[i] - merged[-1]
            if gap >= self._min_frames * 2:
                merged.append(boundaries[i])
        if boundaries[-1] - merged[-1] >= self._min_frames:
            merged.append(boundaries[-1])
        else:
            merged[-1] = boundaries[-1]

        return merged

    # ------------------------------------------------------------------
    # Scene construction
    # ------------------------------------------------------------------

    def _build_scenes(
        self,
        boundaries: list[int],
        features: list[FrameFeatures],
        fps: float,
    ) -> list[SceneInfo]:
        """Convert boundary indices to SceneInfo objects."""
        scenes: list[SceneInfo] = []
        for j in range(len(boundaries) - 1):
            start = boundaries[j]
            # end is exclusive — last frame of this scene is boundaries[j+1] - 1
            end_excl = boundaries[j + 1]
            seg_features = features[start:end_excl]

            start_ts = features[start].timestamp_sec if start < len(features) else 0.0
            last_feat_idx = min(end_excl - 1, len(features) - 1)
            end_ts = features[last_feat_idx].timestamp_sec if last_feat_idx >= 0 and last_feat_idx < len(features) else 0.0
            dur = end_ts - start_ts

            # Aggregate frame features
            avg_bright = sum(f.mean_brightness for f in seg_features) / max(len(seg_features), 1)
            avg_sat = sum(f.mean_saturation for f in seg_features) / max(len(seg_features), 1)
            avg_motion = sum(f.motion_magnitude for f in seg_features) / max(len(seg_features), 1)

            from .schemas import frame_time_str
            scene = SceneInfo(
                scene_id=f"scene_{j:04d}",
                index=j,
                start_frame=start,
                end_frame=end_excl - 1,
                start_timestamp_sec=start_ts,
                end_timestamp_sec=end_ts,
                duration_sec=dur,
                start_timestamp_str=frame_time_str(start_ts),
                end_timestamp_str=frame_time_str(end_ts),
                frame_count=end_excl - start,
                avg_brightness=round(avg_bright, 4),
                avg_saturation=round(avg_sat, 4),
                avg_motion=round(avg_motion, 4),
                detection_method="color_histogram",
            )
            scenes.append(scene)

        return scenes

    def _classify_scenes(
        self,
        scenes: list[SceneInfo],
        features: list[FrameFeatures],
    ) -> list[SceneInfo]:
        """
        Classify scenes as intro/outro/black/static using heuristics.

        - Black: all frames are black
        - Static: very low motion throughout
        - Intro: first N% of video with specific characteristics
        - Outro: last N% of video with specific characteristics
        """
        if not scenes:
            return scenes

        total_duration = scenes[-1].end_timestamp_sec - scenes[0].start_timestamp_sec
        if total_duration <= 0:
            total_duration = 1.0

        # Compute per-frame black/static for scene-level classification
        for scene in scenes:
            seg_features = features[scene.start_frame:scene.end_frame + 1]

            # Black scene: all or majority frames are black
            black_count = sum(1 for f in seg_features if f.is_black_frame)
            scene.is_black = black_count > len(seg_features) * 0.7

            # Static scene: very low motion
            motion_vals = [f.motion_magnitude for f in seg_features]
            scene.is_static = sum(motion_vals) / max(len(motion_vals), 1) < 0.05

        # Intro: first scene(s) that are significantly different
        first_scene = scenes[0]
        intro_end_ratio = first_scene.duration_sec / total_duration if total_duration > 0 else 0
        if intro_end_ratio < 0.05:
            # If first scene is very short, it might be a studio logo / intro card
            first_scene.is_intro = True

        # Outro: last scene(s) near end of video
        last_scene = scenes[-1]
        outro_start_ratio = last_scene.start_timestamp_sec / total_duration if total_duration > 0 else 0
        if outro_start_ratio > 0.85:
            last_scene.is_outro = True

        # Extended outro: if last scene is black, mark as outro
        if last_scene.is_black:
            last_scene.is_outro = True

        return scenes

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _chi_squared(h1: list[int], h2: list[int]) -> float:
        """Chi-squared histogram distance."""
        if not h1 or not h2:
            return 0.0
        diff = 0.0
        for a, b in zip(h1, h2):
            denom = a + b
            if denom > 0:
                diff += ((a - b) ** 2) / denom
        return diff / 256.0

    @staticmethod
    def _histogram_from_features(features: list[FrameFeatures]) -> list[list[int]]:
        """Extract histogram bins from features for chi-squared."""
        return [f.histogram_bins for f in features]

    @staticmethod
    def _timestamps_from_features(features: list[FrameFeatures]) -> list[float]:
        """Extract timestamps from features."""
        return [f.timestamp_sec for f in features]