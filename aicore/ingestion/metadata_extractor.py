"""
MetadataExtractor — deterministic frame-level feature extraction.

All features are heuristic/algebraic — no AI, no ML, no models.

Features extracted per frame:
- Brightness, saturation, dominant color
- Grey histogram (256-bin)
- Histogram difference to previous frame
- Edge density (Sobel-based)
- Dark pixel ratio / black frame detection
- Letterbox ratio
- Difference hash (dHash) and perceptual hash (pHash)
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Optional
from .schemas import FrameFeatures


class MetadataExtractor:
    """
    Extracts deterministic features from frame images.

    Pure Python image processing — no external ML models.
    Uses PIL/Pillow for image I/O and basic pixel ops.
    """

    def __init__(self, image_size_limit: tuple[int, int] = (640, 360)) -> None:
        self._size_limit = image_size_limit
        self._pil_available = self._check_pil()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_features(self, frame_path: str) -> FrameFeatures:
        """
        Extract FrameFeatures from a single frame image.

        The frame_path must point to a valid image file (PNG/JPEG).
        Returns a full FrameFeatures dataclass.
        """
        if not self._pil_available:
            return self._empty_features()

        try:
            from PIL import Image
        except ImportError:
            self._pil_available = False
            return self._empty_features()

        img = Image.open(frame_path).convert("RGB")
        # Resize for consistent processing
        img = self._resize_if_larger(img)
        w, h = img.size
        pixels = list(img.getdata())  # list of (R, G, B) tuples

        # --- Colour features ---
        brightness = self._mean_brightness(pixels)
        saturation = self._mean_saturation(pixels)
        dom_color = self._dominant_color(pixels)

        # --- Grey histogram ---
        grey = self._to_greyscale(pixels)
        hist = self._histogram(grey)

        # --- Edge detection ---
        edge_density = self._edge_density(img)

        # --- Dark pixel ratio ---
        dark_ratio = self._dark_pixel_ratio(grey)

        # --- Black frame ---
        is_black = dark_ratio > 0.95

        # --- Letterbox ---
        letterbox = self._letterbox_ratio(img)

        # --- Perceptual hashes ---
        grey_img = self._to_greyscale_image(img)
        dhash = self._dhash(grey_img)
        phash = self._phash(grey_img)

        return FrameFeatures(
            frame_index=0,
            timestamp_sec=0.0,
            mean_brightness=round(brightness, 4),
            mean_saturation=round(saturation, 4),
            dominant_color_rgb=dom_color,
            histogram_bins=hist,
            edge_density=round(edge_density, 4),
            dark_pixel_ratio=round(dark_ratio, 4),
            is_black_frame=is_black,
            letterbox_ratio=round(letterbox, 4),
            dhash=dhash,
            phash=phash,
        )

    def extract_batch(
        self,
        frame_paths: list[str],
        prev_features: Optional[FrameFeatures] = None,
        fps: float = 1.0,
    ) -> list[FrameFeatures]:
        """
        Extract features for multiple frames in sequence.
        Chain provides histogram diff computation.

        Args:
            frame_paths: List of paths to frame images (in temporal order).
            prev_features: Optional preceding frame features for diff.
            fps: Extraction frame rate — used to compute timestamp_sec = index / fps.
        """
        results: list[FrameFeatures] = []
        prev_pixels_grey: Optional[list[int]] = None

        for i, fp in enumerate(frame_paths):
            feats = self.extract_features(fp)
            feats.frame_index = i
            feats.timestamp_sec = i / fps if fps > 0 else 0.0

            # --- Histogram diff ---
            if i == 0 and prev_features is not None:
                feats.histogram_diff_to_prev = self._histogram_diff(
                    feats.histogram_bins, prev_features.histogram_bins
                )
            elif i > 0:
                feats.histogram_diff_to_prev = self._histogram_diff(
                    feats.histogram_bins, results[i - 1].histogram_bins
                )

            # --- Motion estimation ---
            # Mean absolute pixel difference between consecutive frames.
            # Lightweight: resize to 64x64 grey, then mean abs diff.
            if i > 0 and prev_pixels_grey is not None:
                try:
                    from PIL import Image
                    curr_img = Image.open(fp).convert("L").resize((64, 64))
                    curr_pixels = list(curr_img.getdata())
                    motion_sum = 0.0
                    for j in range(len(curr_pixels)):
                        motion_sum += abs(curr_pixels[j] - prev_pixels_grey[j])
                    feats.motion_magnitude = round(
                        motion_sum / (len(curr_pixels) * 255.0), 4
                    )
                except Exception:
                    feats.motion_magnitude = 0.0

            # --- Store prev pixels for next iteration ---
            if i == 0:
                try:
                    from PIL import Image
                    prev_img = Image.open(fp).convert("L").resize((64, 64))
                    prev_pixels_grey = list(prev_img.getdata())
                except Exception:
                    prev_pixels_grey = None
            else:
                prev_pixels_grey = curr_pixels  # type: ignore

            results.append(feats)
        return results

    # ------------------------------------------------------------------
    # Feature computations
    # ------------------------------------------------------------------

    def _mean_brightness(self, pixels: list[tuple[int, int, int]]) -> float:
        """Mean luminance across all pixels (0-1)."""
        if not pixels:
            return 0.0
        total = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in pixels)
        return total / (len(pixels) * 255.0)

    def _mean_saturation(self, pixels: list[tuple[int, int, int]]) -> float:
        """Mean saturation in HSV space (0-1)."""
        if not pixels:
            return 0.0
        total = 0.0
        for r, g, b in pixels:
            mx = max(r, g, b)
            mn = min(r, g, b)
            if mx == 0:
                total += 0.0
            else:
                total += (mx - mn) / mx
        return total / len(pixels)

    def _dominant_color(self, pixels: list[tuple[int, int, int]]) -> tuple[int, int, int]:
        """
        Quantized dominant color — simple 4x4x4 cube counting.
        Sufficient for heuristic, no k-means.
        """
        if not pixels:
            return (0, 0, 0)
        cubes: dict[tuple[int, int, int], int] = {}
        for r, g, b in pixels:
            key = (r // 64, g // 64, b // 64)
            cubes[key] = cubes.get(key, 0) + 1
        if not cubes:
            return (0, 0, 0)
        best = max(cubes, key=cubes.get)
        # Return center of cube
        return (best[0] * 64 + 32, best[1] * 64 + 32, best[2] * 64 + 32)

    def _to_greyscale(self, pixels: list[tuple[int, int, int]]) -> list[int]:
        """Convert RGB pixels to 0-255 greyscale."""
        return [
            int(0.299 * r + 0.587 * g + 0.114 * b) for r, g, b in pixels
        ]

    def _to_greyscale_image(self, img):
        """Return greyscale PIL Image."""
        return img.convert("L")

    def _histogram(self, grey_pixels: list[int]) -> list[int]:
        """256-bin histogram."""
        hist = [0] * 256
        for p in grey_pixels:
            hist[min(p, 255)] += 1
        return hist

    def _histogram_diff(self, h1: list[int], h2: list[int]) -> float:
        """
        Chi-squared distance between two histograms.
        0 = identical, higher = more different.
        """
        if not h1 or not h2:
            return 0.0
        diff = 0.0
        for a, b in zip(h1, h2):
            denom = a + b
            if denom > 0:
                diff += ((a - b) ** 2) / denom
        return round(diff / 256.0, 4)

    def _edge_density(self, img) -> float:
        """
        Approximate edge detection via horizontal gradient.
        Simple Sobel-like: sum of absolute horizontal differences.
        """
        w, h = img.size
        grey = self._to_greyscale(list(img.getdata()))
        # Reshape as 2D
        pixels_2d = [grey[i * w:(i + 1) * w] for i in range(h)]
        edges = 0
        total = 0
        for y in range(1, h - 1):
            for x in range(1, w - 1):
                gx = (
                    -pixels_2d[y - 1][x - 1] + pixels_2d[y - 1][x + 1]
                    - 2 * pixels_2d[y][x - 1] + 2 * pixels_2d[y][x + 1]
                    - pixels_2d[y + 1][x - 1] + pixels_2d[y + 1][x + 1]
                )
                gy = (
                    -pixels_2d[y - 1][x - 1] - 2 * pixels_2d[y - 1][x] - pixels_2d[y - 1][x + 1]
                    + pixels_2d[y + 1][x - 1] + 2 * pixels_2d[y + 1][x] + pixels_2d[y + 1][x + 1]
                )
                mag = abs(gx) + abs(gy)
                if mag > 128:  # threshold
                    edges += 1
                total += 1
        return edges / max(total, 1)

    def _dark_pixel_ratio(self, grey_pixels: list[int]) -> float:
        """Ratio of pixels with value < 32 (near-black)."""
        if not grey_pixels:
            return 0.0
        dark = sum(1 for p in grey_pixels if p < 32)
        return dark / len(grey_pixels)

    def _letterbox_ratio(self, img) -> float:
        """
        Detect letterbox/pillarbox by checking edge rows/cols.
        Returns the fraction of letterbox area (0 = none, 1 = full black bars).
        """
        w, h = img.size
        grey = self._to_greyscale(list(img.getdata()))
        pixels_2d = [grey[i * w:(i + 1) * w] for i in range(h)]

        # Check top/bottom rows
        top_row = sum(pixels_2d[0]) / w
        bottom_row = sum(pixels_2d[-1]) / w
        left_col = sum(pixels_2d[i][0] for i in range(h)) / h
        right_col = sum(pixels_2d[i][-1] for i in range(h)) / h

        # If borders are very dark, likely letterbox
        dark_threshold = 16
        letterbox_pixels = 0
        total_pixels = w * h

        for y in range(h):
            for x in range(w):
                val = pixels_2d[y][x]
                # Check if in border zone
                is_border = (
                    y < h * 0.1 or y > h * 0.9 or
                    x < w * 0.1 or x > w * 0.9
                )
                if is_border and val < dark_threshold:
                    letterbox_pixels += 1

        return letterbox_pixels / total_pixels if total_pixels > 0 else 0.0

    # ------------------------------------------------------------------
    # Perceptual hashing (dHash, pHash)
    # ------------------------------------------------------------------

    def _dhash(self, grey_img) -> str:
        """
        Difference hash: 8x8 → compare adjacent horizontal pixels → 64 bits.
        Fast, rotation-invariant, deterministic.
        """
        small = grey_img.resize((9, 8))
        pixels = list(small.getdata())
        bits = []
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                bits.append("1" if left > right else "0")
        # Convert bits to hex
        hex_str = ""
        for i in range(0, 64, 4):
            nibble = int("".join(bits[i:i + 4]), 2)
            hex_str += format(nibble, "x")
        return hex_str

    def _phash(self, grey_img) -> str:
        """
        Simple perceptual hash: resize to 8x8, compute mean, compare.
        Deterministic, robust against small variations.
        """
        small = grey_img.resize((8, 8))
        pixels = list(small.getdata())
        mean_val = sum(pixels) / len(pixels)
        bits = ["1" if p > mean_val else "0" for p in pixels]
        hex_str = ""
        for i in range(0, 64, 4):
            nibble = int("".join(bits[i:i + 4]), 2)
            hex_str += format(nibble, "x")
        return hex_str

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resize_if_larger(self, img):
        """Downscale if image exceeds size limit."""
        from PIL import Image
        w, h = img.size
        mw, mh = self._size_limit
        if w > mw or h > mh:
            ratio = min(mw / w, mh / h)
            new_size = (int(w * ratio), int(h * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        return img

    def _empty_features(self) -> FrameFeatures:
        """Return empty features if PIL unavailable."""
        return FrameFeatures(
            frame_index=0,
            timestamp_sec=0.0,
        )

    @staticmethod
    def _check_pil() -> bool:
        try:
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            return False