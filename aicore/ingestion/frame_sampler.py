"""
FrameSampler — adaptive keyframe selection within scenes.

Strategies (all deterministic):
1. UNIFORM: evenly spaced frames
2. HISTOGRAM_PEAK: pick frames with maximum histogram difference (most "representative")
3. BRIGHTEST: pick brightest frames (best visual clarity)
4. HYBRID: combine strategies based on scene characteristics

Each strategy produces a subset of frame indices per scene.
"""

from __future__ import annotations

import math
from typing import Optional

from .schemas import FrameFeatures, SceneInfo, FrameInfo


class FrameSampler:
    """
    Adaptive keyframe sampler.

    Selects the most representative frame indices from each scene
    using deterministic heuristics.
    """

    def __init__(
        self,
        strategy: str = "hybrid",
        max_keyframes_per_scene: int = 3,
        min_keyframes_per_scene: int = 1,
        uniform_interval: float = 2.0,  # seconds between uniform samples
    ) -> None:
        valid = {"uniform", "histogram_peak", "brightest", "hybrid"}
        if strategy not in valid:
            raise ValueError(f"Unknown strategy: {strategy}. Valid: {valid}")

        self._strategy = strategy
        self._max = max_keyframes_per_scene
        self._min = min_keyframes_per_scene
        self._interval = uniform_interval

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sample_scene(
        self,
        scene: SceneInfo,
        features: list[FrameFeatures],
        fps: float,
    ) -> list[int]:
        """
        Select keyframe indices for a single scene.

        Args:
            scene: SceneInfo with start/end frame bounds
            features: Full feature list for frames in scene
            fps: Frames per second

        Returns:
            List of frame indices (absolute, in video timeline)
        """
        if not features:
            return []

        # Map to absolute indices
        start = scene.start_frame
        end = scene.end_frame
        scene_features = features[start:end + 1]

        if len(scene_features) <= self._min:
            return [start]

        if self._strategy == "uniform":
            return self._uniform_sample(scene_features, start)
        elif self._strategy == "histogram_peak":
            return self._histogram_peaks(scene_features, start)
        elif self._strategy == "brightest":
            return self._brightest_sample(scene_features, start)
        else:  # hybrid
            return self._hybrid_sample(scene_features, start, fps)

    def sample_all_scenes(
        self,
        scenes: list[SceneInfo],
        features: list[FrameFeatures],
        fps: float,
    ) -> dict[str, list[int]]:
        """
        Sample keyframes for all scenes.

        Returns dict: scene_id → list of absolute frame indices
        """
        result: dict[str, list[int]] = {}
        for scene in scenes:
            indices = self.sample_scene(scene, features, fps)
            result[scene.scene_id] = indices
            scene.keyframe_indices = indices
        return result

    # ------------------------------------------------------------------
    # Sampling strategies
    # ------------------------------------------------------------------

    def _uniform_sample(
        self,
        features: list[FrameFeatures],
        offset: int,
    ) -> list[int]:
        """Evenly spaced samples."""
        n = len(features)
        count = min(self._max, max(self._min, n))
        if count <= 1:
            return [offset]

        step = max(1, n // count)
        indices: list[int] = []
        for i in range(0, n, step):
            if len(indices) < self._max:
                indices.append(offset + i)
        if len(indices) < self._min:
            indices.append(offset + n - 1)
        return sorted(set(indices))[:self._max]

    def _histogram_peaks(
        self,
        features: list[FrameFeatures],
        offset: int,
    ) -> list[int]:
        """
        Pick frames with highest histogram diff from neighbours.
        These are frames where content changes most — often scene transitions
        or key moments within a scene.
        """
        n = len(features)
        if n <= self._min:
            return [offset + n // 2]

        # Score each frame by avg histogram diff with neighbours
        scores: list[tuple[int, float]] = []
        for i in range(n):
            left_diff = features[i].histogram_diff_to_prev if i > 0 else 0.0
            right_diff = features[i + 1].histogram_diff_to_prev if i < n - 1 else 0.0
            score = (left_diff + right_diff) / 2.0
            scores.append((i, score))

        # Sort by score descending, pick top
        scores.sort(key=lambda x: x[1], reverse=True)
        count = min(self._max, n)
        picked = sorted([offset + scores[i][0] for i in range(count)])
        return picked

    def _brightest_sample(
        self,
        features: list[FrameFeatures],
        offset: int,
    ) -> list[int]:
        """Pick brightest frames (best visual clarity)."""
        n = len(features)
        if n <= self._min:
            return [offset + n // 2]

        scored = [(i, features[i].mean_brightness) for i in range(n)]
        scored.sort(key=lambda x: x[1], reverse=True)
        count = min(self._max, n)
        picked = sorted([offset + scored[i][0] for i in range(count)])
        return picked

    def _hybrid_sample(
        self,
        features: list[FrameFeatures],
        offset: int,
        fps: float,
    ) -> list[int]:
        """
        Hybrid strategy:
        - Always include first frame (scene context)
        - Add brightest frame (visual quality)
        - Add histogram peak frame (content highlight)
        - Add uniform samples for long scenes
        """
        n = len(features)
        if n <= self._min:
            return [offset + n // 2]

        candidates: set[int] = set()

        # Always include first frame
        candidates.add(offset)

        # Brightest frame
        brightest = max(range(n), key=lambda i: features[i].mean_brightness)
        candidates.add(offset + brightest)

        # Histogram peak
        if n > 2:
            peaks = [
                i for i in range(1, n)
                if features[i].histogram_diff_to_prev > 0.3
            ]
            if peaks:
                best_peak = max(peaks, key=lambda i: features[i].histogram_diff_to_prev)
                candidates.add(offset + best_peak)

        # Uniform for long scenes (duration > 5 seconds)
        scene_duration = n / fps if fps > 0 else 0
        if scene_duration > 5.0 and n > 10:
            # Add one middle sample
            mid = offset + n // 2
            candidates.add(mid)

        # Cap at max
        result = sorted(candidates)[:self._max]
        if len(result) < self._min:
            result.append(offset + n // 2)

        return sorted(set(result))