"""
Scene Package Loader
Load exported runtime packages from App 1 for semantic analysis.

Architecture:
- NO raw video loading
- NO cv2.VideoCapture
- NO ffmpeg/ffplay
- Loads ONLY runtime packages exported by SceneFlow.py:
  packages/       - scene packages
  frames/         - pre-exported PNG frames
  runtime_timeline.json - ACTIVE FILTERED RUNTIME DATABASE entries
  runtime_manifest.json - package metadata
  runtime_subtitles.json - ACTIVE FILTERED subtitle database (PRIMARY)
  runtime_audio_regions.json - ACTIVE FILTERED audio regions (PRIMARY)

LOAD ORDER:
  subtitles: runtime_subtitles.json -> source_subtitles.json (fallback)
  audio: runtime_audio_regions.json -> source_audio_regions.json (fallback)

This module is the scene browser and package loader.
It is NOT:
- video editor
- renderer
- runtime generator
- grouping engine
- analysis engine

SceneFlow.py owns:
- immutable runtime package generator
- source reconstruction exporter
- timeline exporter

package_loader.py owns:
- scene browsing
- package loading
- profile management
- prompt module management
- UI layout persistence
"""

import sys
import os
import json
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple
import re

# Qt/PySide6 imports
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QListWidget, QLabel, QPushButton, QTextEdit,
    QTabWidget, QFileDialog, QMessageBox, QCheckBox, QGroupBox,
    QScrollArea, QFrame, QProgressBar, QComboBox, QSpinBox, QTableWidget,
    QTableWidgetItem, QInputDialog
)
from PySide6.QtWidgets import QListWidgetItem as QtWidgets_QListWidgetItem
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QProcess
from PySide6.QtWidgets import QAbstractItemView
from PySide6.QtGui import QPixmap, QTextCursor, QColor

# ============================================================================
# CONFIGURATION
# ============================================================================

# NO global analysis OUTPUT_BASE or ANALYSIS_CURRENT_DIR
# All analysis is package-local: output/<video_name>/analysis/
PROMPTS_DIR = "prompts_scene_analyzer"
CONFIG_FILE = "scene_analyzer_config.json"
PROFILE_FILE = "prompts_scene_analyzer/active_profile.json"
PROFILES_DIR = "prompts_scene_analyzer/profiles/"
UI_LAYOUT_FILE = "config/ui_layout.json"

# Default AI settings (for model fetching only, no analysis)
DEFAULT_PROVIDER = "ollama"
DEFAULT_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_MODEL = "llava:7b"

# SceneFlow.py immutable source naming prefix
SCENE_SRC_PREFIX = "scene_src_"

# ============================================================================
# PROFILE STORAGE
# ============================================================================

DEFAULT_PROFILE = {
    "version": 1,
    "modules": {}
}


def _load_profile() -> dict:
    """Load active profile from active_profile.json.
    
    Returns dict with 'modules' key containing {module_name: {"filename": str, "enabled": bool, "priority": int}}.
    Missing file returns empty profile.
    """
    profile_path = Path(PROFILE_FILE)
    if not profile_path.exists():
        return DEFAULT_PROFILE.copy()
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return DEFAULT_PROFILE.copy()
            if "modules" not in data:
                data["modules"] = {}
            return data
    except (json.JSONDecodeError, Exception):
        return DEFAULT_PROFILE.copy()


def _save_profile(profile: dict) -> None:
    """Save active profile to active_profile.json."""
    profile_path = Path(PROFILE_FILE)
    ensure_dir(str(profile_path.parent))
    profile["version"] = 1
    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to save profile: {e}")


def _load_profile_list() -> List[str]:
    """Load list of available profile names from prompts_scene_analyzer/profiles/.
    
    Returns list of profile names (without .json extension).
    Always includes 'Default' profile if no profiles exist.
    """
    profiles_dir = Path(PROFILES_DIR)
    ensure_dir(str(profiles_dir))
    
    profiles = []
    for f in profiles_dir.glob("*.json"):
        name = f.stem
        if name != "Default":  # Default is virtual
            profiles.append(name)
    
    profiles.sort()
    return profiles


def _load_named_profile(profile_name: str) -> dict:
    """Load a named profile from prompts_scene_analyzer/profiles/<name>.json.
    
    Returns profile dict with 'modules' key, or DEFAULT_PROFILE if not found.
    """
    if profile_name == "Default":
        return DEFAULT_PROFILE.copy()
    
    profile_path = Path(PROFILES_DIR) / f"{profile_name}.json"
    if not profile_path.exists():
        return DEFAULT_PROFILE.copy()
    
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return DEFAULT_PROFILE.copy()
            if "modules" not in data:
                data["modules"] = {}
            return data
    except (json.JSONDecodeError, Exception):
        return DEFAULT_PROFILE.copy()


def _save_named_profile(profile_name: str, profile: dict) -> None:
    """Save a named profile to prompts_scene_analyzer/profiles/<name>.json."""
    if profile_name == "Default":
        return  # Cannot save to Default profile
    
    profile_path = Path(PROFILES_DIR) / f"{profile_name}.json"
    ensure_dir(str(profile_path.parent))
    profile["version"] = 1
    
    try:
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Failed to save profile '{profile_name}': {e}")


def _delete_named_profile(profile_name: str) -> bool:
    """Delete a named profile file from prompts_scene_analyzer/profiles/.
    
    Returns True if deleted, False if not found or protected.
    Cannot delete 'Default' profile.
    """
    if profile_name == "Default":
        return False
    
    profile_path = Path(PROFILES_DIR) / f"{profile_name}.json"
    if not profile_path.exists():
        return False
    
    try:
        profile_path.unlink()
        return True
    except Exception:
        return False


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def ensure_dir(path: str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def clear_directory(dir_path: str) -> None:
    """Delete and recreate a directory to ensure it's empty."""
    path = Path(dir_path)
    if path.exists():
        shutil.rmtree(str(path))
    path.mkdir(parents=True, exist_ok=True)


def get_analysis_dir(package_dir: str) -> Path:
    """Get package-local analysis directory: output/<video_name>/analysis/"""
    pkg = Path(package_dir)
    return pkg / "analysis"


def parse_subtitle_srt(srt_text: str) -> List[Dict]:
    """Parse SRT format subtitles into structured list with start/end times.

    SRT format:
    1
    00:00:01,000 --> 00:00:04,000
    Subtitle text line 1
    Subtitle text line 2

    Output: list of {"start": float, "end": float, "text": str}
    """
    if not srt_text:
        return []
    parsed = []
    # Split into blocks
    blocks = re.split(r'\n\n+', srt_text.strip())
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        # Find timing line (contains -->)
        timing_line = None
        text_lines = []
        for i, line in enumerate(lines):
            if '-->' in line:
                timing_line = line
                text_lines = lines[i+1:]
                break
        if not timing_line:
            continue
        # Parse timing
        try:
            parts = timing_line.split('-->')
            start_str = parts[0].strip()
            end_str = parts[1].strip().split()[0]  # Handle any extra text after end time
            start = parse_srt_time(start_str)
            end = parse_srt_time(end_str)
            text = ' '.join(text_lines).strip()
            if text:
                parsed.append({"start": start, "end": end, "text": text})
        except Exception:
            continue
    return parsed


def parse_srt_time(time_str: str) -> float:
    """Parse SRT time string (HH:MM:SS,mmm) to float seconds."""
    # Remove commas and split
    time_str = time_str.replace(',', '.').strip()
    parts = time_str.split(':')
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    return 0.0


def parse_subtitle_json(subtitles_data: List[Dict]) -> List[Dict]:
    """Parse subtitles from JSON format and return list with start/end times.

    Input: list of {"start": float, "end": float, "text": str}
    Output: list of {"start": float, "end": float, "text": str}

    Supports multiple key formats for time fields: start/end, start_sec/end_sec, start_time/end_time
    Supports multiple key formats for text field: text, subtitle_text, content, caption
    """
    if not subtitles_data:
        return []
    parsed = []
    for sub in subtitles_data:
        # Support alternative time field names
        start = sub.get("start", sub.get("start_sec", sub.get("start_time", 0)))
        end = sub.get("end", sub.get("end_sec", sub.get("end_time", start + 1)))
        # Support alternative text field names
        text = sub.get("text", sub.get("subtitle_text", sub.get("content", sub.get("caption", "")))).strip()
        if text:
            parsed.append({"start": start, "end": end, "text": text})
    return parsed


def format_source_scene_id(scene_num: int) -> str:
    """Format scene number to immutable scene_src_XXXX pattern."""
    return f"{SCENE_SRC_PREFIX}{scene_num:04d}"


def extract_scene_number(scene_id: str) -> int:
    """Extract numeric part from scene_src_XXXX or scene_XXXX."""
    try:
        num = int(re.search(r'(\d+)', str(scene_id)).group(1))
        return num
    except (AttributeError, ValueError):
        return 0


def times_overlap(scene_start: float, scene_end: float,
                  item_start: float, item_end: float) -> bool:
    """Check if two time ranges overlap."""
    return item_start < scene_end and item_end > scene_start


def enrich_scenes_with_context(scenes: List[Dict],
                               subtitles: List[Dict],
                               audio_regions: List[Dict]) -> List[Dict]:
    """Enrich each scene with subtitle and audio context using timeline overlap.

    For each scene, find overlapping subtitles and audio regions.
    - subtitle_text: concatenated text of all overlapping subtitles
    - has_subtitle: True if any subtitle overlaps
    - audio_type: dominant audio type (speech/music/silence)
    - audio_energy: average energy of overlapping audio regions
    """
    for scene in scenes:
        scene_start = scene.get("start_time", 0)
        scene_end = scene_start + scene.get("duration", 0)

        # Find overlapping subtitles
        overlapping_subs = []
        for sub in subtitles:
            sub_start = sub.get("start", 0)
            sub_end = sub.get("end", sub_start + 1)
            if times_overlap(scene_start, scene_end, sub_start, sub_end):
                overlapping_subs.append(sub.get("text", ""))
        scene["subtitle_text"] = " ".join(overlapping_subs)
        scene["has_subtitle"] = len(overlapping_subs) > 0

        # Find overlapping audio regions
        overlapping_audio = []
        for region in audio_regions:
            reg_start = region.get("start", 0)
            reg_end = region.get("end", reg_start + 1)
            if times_overlap(scene_start, scene_end, reg_start, reg_end):
                overlapping_audio.append(region)

        # Determine dominant audio type and average energy
        if overlapping_audio:
            type_counts = {}
            total_energy = 0
            for reg in overlapping_audio:
                audio_type = reg.get("type", "silence")
                type_counts[audio_type] = type_counts.get(audio_type, 0) + 1
                total_energy += reg.get("energy", 0)
            if type_counts.get("speech", 0) > 0:
                scene["audio_type"] = "speech"
            elif type_counts.get("high_energy", 0) > 0:
                scene["audio_type"] = "music"
            elif type_counts.get("silence", 0) > 0:
                scene["audio_type"] = "silence"
            else:
                scene["audio_type"] = list(type_counts.keys())[0] if type_counts else "unknown"
            scene["audio_energy"] = round(total_energy / len(overlapping_audio), 3)
        else:
            scene["audio_type"] = "unknown"
            scene["audio_energy"] = 0.0
    return scenes


def fetch_ollama_models(base_url: str) -> List[str]:
    """Fetch model list from Ollama /api/tags endpoint."""
    import requests
    try:
        response = requests.get(f"{base_url}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        return [m for m in models if m]  # Filter empty strings
    except Exception as e:
        print(f"Failed to fetch Ollama models: {e}")
        return []


def fetch_openai_models(base_url: str) -> List[str]:
    """Fetch model list from OpenAI-compatible /v1/models endpoint."""
    import requests
    try:
        response = requests.get(f"{base_url}/v1/models", timeout=10)
        response.raise_for_status()
        data = response.json()
        models = [m.get("id", "") for m in data.get("data", [])]
        return [m for m in models if m]  # Filter empty strings
    except Exception as e:
        print(f"Failed to fetch OpenAI models: {e}")
        return []


def load_package_data(package_dir: str) -> Dict:
    """Load a runtime package directory and return structured data.

    Expected SceneFlow.py contract (IMMUTABLE):
    packages/       - scene packages
    frames/         - PNG frame files
    runtime_timeline.json - ACTIVE FILTERED RUNTIME DATABASE
    runtime_manifest.json - package metadata
    source_subtitles.json - source subtitles from SceneFlow.py
    source_audio_regions.json - source audio regions from SceneFlow.py

    NO legacy contracts:
    metadata/       - REMOVED
    audio/          - REMOVED
    manifest.json   - REMOVED
    audio_regions.json - REMOVED
    subtitles_filtered.srt - REMOVED

    Returns dict with keys:
        - manifest: parsed runtime_manifest.json (or empty dict)
        - timeline: parsed timeline.json entries (or empty list)
        - frames: sorted list of PNG frame paths
        - subtitles_data: parsed runtime_subtitles.json (or source_subtitles.json fallback)
        - audio_regions: parsed runtime_audio_regions.json (or source_audio_regions.json fallback)
    """
    pkg = Path(package_dir)
    result = {
        "package_dir": str(pkg),
        "manifest": {},
        "timeline": [],
        "frames": [],
        "subtitles_data": [],
        "audio_regions": []
    }

    # Load runtime_manifest.json (SceneFlow.py contract - ACTIVE ONLY)
    manifest_path = pkg / "runtime_manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                result["manifest"] = json.load(f)
        except Exception as e:
            print(f"Failed to load runtime_manifest: {e}")

    # Load runtime_timeline.json (SceneFlow.py ACTIVE FILTERED RUNTIME DATABASE)
    # ONLY load from this contract - NO legacy timeline.json
    timeline_path = pkg / "runtime_timeline.json"
    if timeline_path.exists():
        try:
            with open(timeline_path, "r", encoding="utf-8") as f:
                timeline_data = json.load(f)
                # Support both list and dict formats
                if isinstance(timeline_data, list):
                    result["timeline"] = timeline_data
                elif isinstance(timeline_data, dict):
                    # PRIMARY: "scenes" key (actual runtime_timeline.json contract)
                    # FALLBACK: "entries" or "segments" (legacy contracts)
                    result["timeline"] = timeline_data.get("scenes",
                                        timeline_data.get("entries",
                                        timeline_data.get("segments", [])))
        except Exception as e:
            print(f"Failed to load runtime_timeline: {e}")

    # Load frames from frames/ directory
    frames_dir = pkg / "frames"
    if frames_dir.exists() and frames_dir.is_dir():
        for f in sorted(frames_dir.iterdir()):
            if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
                result["frames"].append(str(f))

    # Load runtime_subtitles.json (NEW SceneFlow.py runtime contract)
    # This is the ACTIVE filtered subtitle database
    subtitles_path = pkg / "runtime_subtitles.json"
    if subtitles_path.exists():
        try:
            with open(subtitles_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                # Debug: log top-level keys
                if isinstance(raw, dict):
                    print(f"[DEBUG] runtime_subtitles.json keys: {list(raw.keys())}")
                # Can be list or dict with known key formats
                if isinstance(raw, list):
                    result["subtitles_data"] = parse_subtitle_json(raw)
                    print(f"[DEBUG] Loaded runtime subtitles (list): {len(result['subtitles_data'])} entries")
                elif isinstance(raw, dict):
                    # Support multiple key formats: subtitles, scenes, segments, entries, data, items
                    # "scenes" is the ACTUAL runtime export format: {"scenes": [{"scene_id": "...", "subtitles": [...]}]}
                    subs = raw.get("subtitles",
                           raw.get("scenes",
                           raw.get("segments",
                           raw.get("entries",
                           raw.get("data",
                           raw.get("items", []))))))
                    if subs:
                        # Detect "scenes" format: list of {scene_id, subtitles: [...]} with nested subtitles
                        if isinstance(subs, list) and len(subs) > 0 and isinstance(subs[0], dict) and "subtitles" in subs[0]:
                            flat_subs = []
                            for scene_obj in subs:
                                scene_subs = scene_obj.get("subtitles", [])
                                flat_subs.extend(scene_subs)
                            result["subtitles_data"] = parse_subtitle_json(flat_subs)
                            print(f"[DEBUG] Loaded runtime subtitles (scenes format): {len(result['subtitles_data'])} entries")
                        else:
                            result["subtitles_data"] = parse_subtitle_json(subs)
                            print(f"[DEBUG] Loaded runtime subtitles: {len(result['subtitles_data'])} entries")
                    else:
                        print(f"[WARNING] Unknown runtime_subtitles.json structure. Keys: {list(raw.keys())}")
        except Exception as e:
            print(f"Failed to load runtime_subtitles: {e}")

    # Fallback: try old contract if new contract not found
    if not result.get("subtitles_data"):
        old_subtitles_path = pkg / "source_subtitles.json"
        if old_subtitles_path.exists():
            try:
                with open(old_subtitles_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        print(f"[DEBUG] source_subtitles.json keys: {list(raw.keys())}")
                    if isinstance(raw, list):
                        result["subtitles_data"] = parse_subtitle_json(raw)
                    elif isinstance(raw, dict):
                        subs = raw.get("subtitles",
                               raw.get("segments",
                               raw.get("entries",
                               raw.get("data",
                               raw.get("items", [])))))
                        result["subtitles_data"] = parse_subtitle_json(subs)
            except Exception as e:
                print(f"Failed to load source_subtitles (fallback): {e}")

    # Load runtime_audio_regions.json (NEW SceneFlow.py runtime contract)
    # This is the ACTIVE filtered audio regions database
    audio_regions_path = pkg / "runtime_audio_regions.json"
    result["audio_regions"] = []
    if audio_regions_path.exists():
        try:
            with open(audio_regions_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                # Debug: log top-level keys
                if isinstance(raw, dict):
                    print(f"[DEBUG] runtime_audio_regions.json keys: {list(raw.keys())}")
                # Can be list or dict with known key formats
                if isinstance(raw, list):
                    result["audio_regions"] = raw
                    print(f"[DEBUG] Loaded runtime audio regions (list): {len(result['audio_regions'])} entries")
                elif isinstance(raw, dict):
                    # Support multiple key formats: audio_regions, regions, entries, data, items
                    audio_data = raw.get("audio_regions",
                                raw.get("regions",
                                raw.get("scenes",
                                raw.get("entries",
                                raw.get("data",
                                raw.get("items", []))))))
                    if audio_data:
                        # Detect "scenes" format: list of scene objects with nested audio regions
                        if isinstance(audio_data, list) and len(audio_data) > 0 and isinstance(audio_data[0], dict) and ("audio_regions" in audio_data[0] or "regions" in audio_data[0]):
                            flat_regions = []
                            for scene_obj in audio_data:
                                scene_regions = scene_obj.get("audio_regions", scene_obj.get("regions", []))
                                flat_regions.extend(scene_regions)
                            result["audio_regions"] = flat_regions
                        else:
                            result["audio_regions"] = audio_data
                        print(f"[DEBUG] Loaded runtime audio regions: {len(result['audio_regions'])} entries")
                    else:
                        print(f"[WARNING] Unknown runtime_audio_regions.json structure. Keys: {list(raw.keys())}")
        except Exception as e:
            print(f"Failed to load runtime_audio_regions: {e}")

    # Fallback: try old contract if new contract not found
    if not result.get("audio_regions"):
        old_audio_regions_path = pkg / "source_audio_regions.json"
        if old_audio_regions_path.exists():
            try:
                with open(old_audio_regions_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    if isinstance(raw, dict):
                        print(f"[DEBUG] source_audio_regions.json keys: {list(raw.keys())}")
                    if isinstance(raw, list):
                        result["audio_regions"] = raw
                    elif isinstance(raw, dict):
                        audio_data = raw.get("audio_regions",
                                    raw.get("regions",
                                    raw.get("entries",
                                    raw.get("data",
                                    raw.get("items", [])))))
                        result["audio_regions"] = audio_data
            except Exception as e:
                print(f"Failed to load source_audio_regions (fallback): {e}")

    return result


def build_scene_list_from_package(package_data: Dict) -> List[Dict]:
    """Build a scene list from loaded package data.

    Uses SceneFlow.py runtime_timeline.json which is the ACTIVE FILTERED RUNTIME DATABASE.
    Each entry contains:
    - runtime_scene_index
    - source_scene_id
    - frame_path
    - filtered
    - filtered_reason
    - start_sec
    - end_sec
    - duration

    Each built scene entry contains:
        - id: source_scene_id (scene_src_XXXX)
        - source_scene_id: original source scene id
        - name: display name
        - path: path to representative frame image
        - duration: scene duration in seconds
        - timeline_entry: original timeline entry data
        - frame: path to the PNG frame used for preview
        - start_time: scene start time from timeline
        - end_time: scene end time from timeline
        - subtitle_text: overlapping subtitle text
        - has_subtitle: True if subtitle overlaps
        - audio_type: dominant audio type
        - audio_energy: average energy
    """
    scenes = []
    frames = package_data.get("frames", [])
    timeline = package_data.get("timeline", [])

    if timeline:
        # Build scene list from timeline entries, matching frames by source_scene_id
        for i, entry in enumerate(timeline):
            # SceneFlow.py timeline contract: runtime_scene_index and source_scene_id
            raw_scene_id = entry.get("source_scene_id", entry.get("scene_id", i))

            # PART 2: Normalize source_scene_id from int to immutable scene_src_XXXX
            # runtime_timeline.json stores source_scene_id as int (e.g. 15)
            # semantic pipeline requires scene_src_XXXX format (e.g. scene_src_0015)
            if isinstance(raw_scene_id, int):
                scene_id = format_source_scene_id(raw_scene_id)
            else:
                scene_num = extract_scene_number(raw_scene_id)
                scene_id = format_source_scene_id(scene_num) if scene_num > 0 else str(raw_scene_id)

            scene_name = entry.get("name", entry.get("label", scene_id))

            # PART 3: Get timing - PRIMARY: start_time/end_time, FALLBACK: start_sec/end_sec
            # runtime_timeline.json uses start_time/end_time; fall back to start_sec/end_sec
            start_time = entry.get("start_time", entry.get("start_sec", entry.get("start", 0)))
            end_time = entry.get("end_time", entry.get("end_sec", entry.get("end", 0)))
            duration = entry.get("duration", 0.0)
            if duration <= 0 and end_time > start_time:
                duration = end_time - start_time

            # Match frame to scene using scene_src_XXXX pattern
            frame_path = None
            scene_num = extract_scene_number(scene_id)
            src_pattern = format_source_scene_id(scene_num)
            for fp in frames:
                fp_stem = Path(fp).stem
                if src_pattern in fp_stem or scene_id in fp_stem:
                    frame_path = fp
                    break

            scenes.append({
                "id": scene_id,
                "source_scene_id": scene_id,
                "name": scene_name,
                "path": frame_path,
                "duration": duration,
                "start_time": start_time,
                "end_time": end_time,
                "timeline_entry": entry,
                "frame": frame_path or entry.get("frame_path"),
                "subtitle_text": "",
                "has_subtitle": False,
                "audio_type": "unknown",
                "audio_energy": 0.0
            })
    else:
        # Fallback: use frames directly as scene list
        # Extract source_scene_id from frame filenames (scene_src_XXXX.png)
        for fp in frames:
            fp_stem = Path(fp).stem
            # Try to extract scene number from frame filename
            scene_num_search = re.search(r'(\d+)', fp_stem)
            if scene_num_search:
                scene_num = int(scene_num_search.group(1))
                src_id = format_source_scene_id(scene_num)
            else:
                # No numeric pattern in filename - use stem as id
                src_id = fp_stem
            scenes.append({
                "id": src_id,
                "source_scene_id": src_id,
                "name": Path(fp).stem,
                "path": fp,
                "duration": 0,
                "start_time": 0,
                "end_time": 0,
                "timeline_entry": {},
                "frame": fp,
                "subtitle_text": "",
                "has_subtitle": False,
                "audio_type": "unknown",
                "audio_energy": 0.0
            })

    # Enrich scenes with subtitle and audio context
    subtitles = package_data.get("subtitles_data", [])
    audio_regions = package_data.get("audio_regions", [])
    scenes = enrich_scenes_with_context(scenes, subtitles, audio_regions)

    return scenes


# ============================================================================
# MODEL FETCH WORKER THREAD
# ============================================================================

class ModelFetchWorker(QThread):
    """Worker thread for fetching available models."""
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, provider: str, base_url: str):
        super().__init__()
        self.provider = provider
        self.base_url = base_url

    def run(self):
        try:
            if self.provider == "ollama":
                models = fetch_ollama_models(self.base_url)
            else:
                models = fetch_openai_models(self.base_url)
            self.finished.emit(models)
        except Exception as e:
            self.error.emit(str(e))


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class PackageLoader(QMainWindow):
    """Main window for Scene Package Loader.
    Loads exported runtime packages from SceneFlow.py for browsing.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scene Package Loader")
        self.setGeometry(100, 100, 1400, 900)

        # State
        self.current_package_dir = None
        self.package_data = {}
        self.scene_list = []
        self.selected_scene = None

        # AI Provider settings (for model fetching only, no analysis)
        self.provider = DEFAULT_PROVIDER
        self.base_url = DEFAULT_BASE_URL
        self.model_name = DEFAULT_MODEL
        self.available_models = []

        ensure_dir(PROMPTS_DIR)
        self._load_config()
        
        # Load profile state for module persistence
        self._profile = _load_profile()
        self._module_states = {}  # module_name -> {"enabled": bool, "priority": int}
        self._load_module_states_from_profile()
        
        self._setup_ui()
        self._refresh_models()
        self.statusBar().showMessage("Ready - Load a package to begin")
    
    def _load_module_states_from_profile(self):
        """Load module states (enabled/priority) from profile."""
        profile_modules = self._profile.get("modules", {})
        for module_name, state in profile_modules.items():
            self._module_states[module_name] = {
                "enabled": state.get("enabled", True),
                "priority": state.get("priority", 100)
            }
    
    def _save_module_states_to_profile(self):
        """Save current module states to profile file."""
        profile_modules = {}
        for module_name, state in self._module_states.items():
            profile_modules[module_name] = {
                "filename": f"{module_name}.txt",
                "enabled": state.get("enabled", True),
                "priority": state.get("priority", 100)
            }
        self._profile["modules"] = profile_modules
        _save_profile(self._profile)
    
    def _get_next_priority(self) -> int:
        """Get the next available priority number."""
        priorities = [s.get("priority", 100) for s in self._module_states.values()]
        return max(priorities) + 10 if priorities else 10

    # -------------------------------------------------------------------------
    # PROFILE MANAGEMENT (RB3.3)
    # -------------------------------------------------------------------------

    def _refresh_profile_combo(self) -> None:
        """Refresh the profile dropdown with available profiles."""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        
        # Always add Default first
        self.profile_combo.addItem("Default")
        
        # Add other profiles from storage
        profiles = _load_profile_list()
        for p in profiles:
            self.profile_combo.addItem(p)
        
        self.profile_combo.blockSignals(False)

    def _on_profile_changed(self, profile_name: str) -> None:
        """Handle profile dropdown selection change."""
        # Auto-load on selection change
        pass  # User must click Load to apply

    def _new_profile(self) -> None:
        """Create a new profile with a default name."""
        i = 1
        while True:
            name = f"Profile_{i}"
            if not Path(PROFILES_DIR, f"{name}.json").exists():
                break
            i += 1
        
        # Create profile from current state
        profile = self._build_profile_from_current_state()
        _save_named_profile(name, profile)
        
        # Refresh combo and select new profile
        self._refresh_profile_combo()
        self.profile_combo.setCurrentText(name)

    def _rename_profile(self) -> None:
        """Rename the currently selected profile."""
        current = self.profile_combo.currentText()
        if current == "Default":
            QMessageBox.warning(self, "Protected", "Cannot rename Default profile.")
            return
        
        new_name, ok = QInputDialog.getText(self, "Rename Profile", 
            f"Enter new name for '{current}':")
        if not ok or not new_name:
            return
        
        new_name = new_name.strip()
        if not new_name:
            return
        
        # Load current profile data
        profile_path = Path(PROFILES_DIR) / f"{current}.json"
        if profile_path.exists():
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                
                # Delete old file and save with new name
                profile_path.unlink()
                _save_named_profile(new_name, profile)
                
                self._refresh_profile_combo()
                self.profile_combo.setCurrentText(new_name)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename: {e}")

    def _delete_profile(self) -> None:
        """Delete the currently selected profile."""
        current = self.profile_combo.currentText()
        if current == "Default":
            QMessageBox.warning(self, "Protected", "Cannot delete Default profile.")
            return
        
        reply = QMessageBox.question(self, "Delete Profile",
            f"Delete profile '{current}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        if _delete_named_profile(current):
            self._refresh_profile_combo()
            self.profile_combo.setCurrentText("Default")

    def _save_profile_action(self) -> None:
        """Save current module states to the selected profile."""
        current = self.profile_combo.currentText()
        
        profile = self._build_profile_from_current_state()
        _save_named_profile(current, profile)
        
        self.statusBar().showMessage(f"Profile '{current}' saved", 2000)

    def _load_profile_action(self) -> None:
        """Load the selected profile and apply module states."""
        current = self.profile_combo.currentText()
        profile = _load_named_profile(current)
        
        # Apply module states from profile
        if "modules" in profile:
            for name, state in profile["modules"].items():
                self._module_states[name] = {
                    "enabled": state.get("enabled", True),
                    "priority": state.get("priority", 100),
                    "order": state.get("order", 0)
                }
        
        # Rebuild UI
        self._refresh_module_list()
        
        # RB3.3.X FIX: Sync preview with loaded enabled states
        self._update_final_prompt_preview()
        
        self.statusBar().showMessage(f"Profile '{current}' loaded", 2000)

    def _build_profile_from_current_state(self) -> dict:
        """Build a profile dict from current module states.
        
        Uses SINGLE SOURCE OF TRUTH: _get_module_order() for consistent ordering.
        """
        sorted_names = self._get_module_order()
        
        modules = {}
        for i, name in enumerate(sorted_names):
            state = self._module_states.get(name, {"enabled": True, "priority": 100})
            modules[name] = {
                "enabled": state.get("enabled", True),
                "priority": state.get("priority", 100),
            }
        
        return {"modules": modules}

    # -------------------------------------------------------------------------
    # UI BUILDERS
    # -------------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        layout.addWidget(self._create_top_bar())

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self._create_left_panel())
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.addWidget(self._create_center_panel())
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.addWidget(self._create_right_panel())
        self.main_splitter.setStretchFactor(2, 2)
        layout.addWidget(self.main_splitter)

        self.bottom_splitter_widget = self._create_bottom_panel()
        layout.addWidget(self.bottom_splitter_widget)
        
        # Restore UI layout after all widgets created
        self._restore_ui_layout()

    def _create_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setMaximumHeight(50)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Package path section
        layout.addWidget(QLabel("Package:"))
        self.package_path_label = QLabel("Not loaded")
        self.package_path_label.setStyleSheet("color: gray;")
        self.package_path_label.setMinimumWidth(150)
        layout.addWidget(self.package_path_label)

        load_package_btn = QPushButton("Load Package")
        load_package_btn.setMaximumWidth(90)
        load_package_btn.clicked.connect(self.load_package_folder)
        layout.addWidget(load_package_btn)

        layout.addSpacing(16)

        # AI Provider section - grouped controls
        provider_group = QWidget()
        provider_layout = QHBoxLayout(provider_group)
        provider_layout.setContentsMargins(0, 0, 0, 0)
        provider_layout.setSpacing(6)

        # Provider selector
        provider_layout.addWidget(QLabel("Provider:"))
        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumWidth(110)
        self.provider_combo.addItems(["ollama", "openai"])
        self.provider_combo.setCurrentText(self.provider)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addWidget(self.provider_combo)

        # Base URL input
        provider_layout.addWidget(QLabel("URL:"))
        self.base_url_input = QTextEdit()
        self.base_url_input.setMaximumHeight(24)
        self.base_url_input.setPlainText(self.base_url)
        self.base_url_input.textChanged.connect(self._on_base_url_changed)
        provider_layout.addWidget(self.base_url_input)

        # Refresh models button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMaximumWidth(75)
        refresh_btn.clicked.connect(self._refresh_models)
        provider_layout.addWidget(refresh_btn)

        # Model selector
        provider_layout.addWidget(QLabel("Model:"))
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(140)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        provider_layout.addWidget(self.model_combo)

        layout.addWidget(provider_group)
        layout.addStretch()

        return bar

    def _create_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        lbl = QLabel("SCENES")
        lbl.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(lbl)

        self.scene_list_widget = QListWidget()
        self.scene_list_widget.itemClicked.connect(self._on_scene_selected)
        self.scene_list_widget.currentRowChanged.connect(self._on_scene_row_changed)
        layout.addWidget(self.scene_list_widget)

        info_group = QGroupBox("Selected Scene Info")
        info_layout = QVBoxLayout(info_group)
        self.scene_info_label = QLabel("No scene selected")
        self.scene_info_label.setWordWrap(True)
        self.scene_info_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self.scene_info_label)
        layout.addWidget(info_group)

        return panel

    def _create_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        # Package frame display - load PNG directly
        layout.addWidget(self._make_label("PACKAGE FRAME"))
        self.frame_display_label = self._make_frame_label("FRAME")
        layout.addWidget(self.frame_display_label)

        # Scene preview - shows selected scene frame
        pg = QGroupBox("SCENE PREVIEW")
        pgl = QVBoxLayout(pg)
        self.preview_label = QLabel("Select a scene to preview")
        self.preview_label.setMinimumHeight(180)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid #444; background: #111; color: #666;")
        pgl.addWidget(self.preview_label)
        layout.addWidget(pg)
        layout.setStretchFactor(self.frame_display_label, 1)
        layout.setStretchFactor(pg, 1)
        layout.addStretch()
        return panel

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: #aaa;")
        return lbl

    def _make_frame_label(self, title: str) -> QLabel:
        lbl = QLabel(f"{title}\nNo frame")
        lbl.setMinimumSize(180, 120)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("border: 1px solid #444; background: #1a1a1a; color: #666;")
        return lbl

    def _create_right_panel(self) -> QWidget:
        """Right panel - Prompt Module Manager UI (RB3.2)."""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)

        # === PROFILE AREA (RB3.3) ===
        profile_group = QGroupBox("PROFILE")
        profile_layout = QVBoxLayout(profile_group)
        profile_layout.setSpacing(6)
        
        # Profile selector row - combo full width
        selector_layout = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.currentTextChanged.connect(self._on_profile_changed)
        selector_layout.addWidget(QLabel("Profile:"))
        selector_layout.addWidget(self.profile_combo)
        profile_layout.addLayout(selector_layout)
        
        # Profile button row - SINGLE ROW, equal sizing, centered
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)
        
        new_btn = QPushButton("New")
        new_btn.clicked.connect(self._new_profile)
        btn_layout.addWidget(new_btn)
        
        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_profile)
        btn_layout.addWidget(rename_btn)
        
        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_profile)
        btn_layout.addWidget(delete_btn)
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_profile_action)
        btn_layout.addWidget(save_btn)
        
        load_btn = QPushButton("Load")
        load_btn.clicked.connect(self._load_profile_action)
        btn_layout.addWidget(load_btn)
        
        profile_layout.addLayout(btn_layout)
        
        layout.addWidget(profile_group)
        
        # Initialize profile combo
        self._refresh_profile_combo()

        # === PROMPT MODULE MANAGER (RB3.2) ===
        
        # Header
        header_lbl = QLabel("PROMPT MODULE MANAGER")
        header_lbl.setStyleSheet("font-weight: bold; color: #aaa;")
        layout.addWidget(header_lbl)

        # Module directory path display
        self.module_dir_label = QLabel(f"Directory: {PROMPTS_DIR}/modules/")
        self.module_dir_label.setStyleSheet("color: #888; font-size: 10px;")
        layout.addWidget(self.module_dir_label)

        # Module table (scrollable) with Order, Filename, Enabled columns
        self.module_table = QTableWidget()
        self.module_table.setMaximumHeight(300)
        self.module_table.setColumnCount(3)
        self.module_table.setHorizontalHeaderLabels(["Order", "Filename", "Enabled"])
        self.module_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.module_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.module_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.module_table.horizontalHeader().setStretchLastSection(True)
        self.module_table.setColumnWidth(0, 60)
        self.module_table.setColumnWidth(1, 200)
        self.module_table.itemClicked.connect(self._on_module_selected)
        layout.addWidget(self.module_table)

        # Button row for module operations - SINGLE ROW, equal sizing, centered
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_module)
        btn_layout.addWidget(add_btn)

        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_module)
        btn_layout.addWidget(rename_btn)

        duplicate_btn = QPushButton("Duplicate")
        duplicate_btn.clicked.connect(self._duplicate_module)
        btn_layout.addWidget(duplicate_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_module)
        btn_layout.addWidget(delete_btn)

        move_up_btn = QPushButton("Up")
        move_up_btn.clicked.connect(self._on_move_up)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Down")
        move_down_btn.clicked.connect(self._on_move_down)
        btn_layout.addWidget(move_down_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_module)
        btn_layout.addWidget(edit_btn)

        # Push buttons to left, checkbox to right
        btn_layout.addStretch()
        
        self.module_enabled_checkbox = QCheckBox("Enabled")
        self.module_enabled_checkbox.stateChanged.connect(self._on_module_enabled_toggle)
        btn_layout.addWidget(self.module_enabled_checkbox)

        layout.addLayout(btn_layout)

        # Module preview area
        preview_group = QGroupBox("Module Preview")
        preview_layout = QVBoxLayout(preview_group)
        self.module_preview_text = QTextEdit()
        self.module_preview_text.setReadOnly(True)
        self.module_preview_text.setMaximumHeight(120)
        self.module_preview_text.setStyleSheet("font-family: monospace; font-size: 10px; background: #1a1a1a; color: #9cdcfe;")
        preview_layout.addWidget(self.module_preview_text)
        layout.addWidget(preview_group)

        # Current module tracking
        self._current_module = None

        # Load modules on init
        self._refresh_module_list()

        layout.addStretch()
        return panel

    def _get_modules_dir(self) -> Path:
        """Get the modules directory path, creating if needed."""
        modules_dir = Path(PROMPTS_DIR) / "modules"
        modules_dir.mkdir(parents=True, exist_ok=True)
        return modules_dir

    def _get_module_order(self) -> List[str]:
        """Get ordered module names based on priority.
        
        SINGLE SOURCE OF TRUTH for module ordering.
        All ordering operations MUST use this function.
        
        Order is based solely on priority values from _module_states.
        Modules without priority get default 100.
        """
        return sorted(
            self._module_states.keys(),
            key=lambda m: self._module_states.get(m, {}).get("priority", 100)
        )

    def _compile_final_prompt(self) -> str:
        """Compile final prompt from enabled modules and metadata registry.
        
        Single Compiler - the ONE compiler that generates final prompt text.
        Reads TXT modules in order, skips disabled, merges content,
        appends metadata section.
        
        Returns:
            str: The compiled final prompt string.
        """
        modules_dir = self._get_modules_dir()
        module_order = self._get_module_order()
        
        parts = []
        
        for module_name in module_order:
            state = self._module_states.get(module_name, {})
            if not state.get("enabled", True):
                continue
            
            module_path = modules_dir / f"{module_name}.txt"
            if module_path.exists():
                try:
                    with open(module_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                    if content:
                        parts.append(content)
                except Exception:
                    continue
        
        # Append metadata section (safe access - may not be initialized)
        registry = getattr(self, 'metadata_registry', None) or {}
        if registry:
            metadata_lines = ["", "---", "SCENE METADATA"]
            for key, value in registry.items():
                if value is not None and str(value).strip():
                    metadata_lines.append(f"{key}={value}")
            parts.append("\n".join(metadata_lines))
        
        final_prompt = "\n\n".join(parts)
        return final_prompt

    def _refresh_module_list(self):
        """Refresh the module table from prompts_scene_analyzer/modules/ directory.

        Uses SINGLE SOURCE OF TRUTH: _get_module_order() for consistent ordering.
        Shows: Order (A/B/C), Filename, Enabled columns.
        Preserves existing enable/disable states across refreshes.
        New modules default to enabled with unique priority.
        Removed modules are purged from state.
        """
        modules_dir = self._get_modules_dir()
        current_modules = set()
        
        # Only load .txt files from top level (ignore subfolders)
        for f in sorted(modules_dir.iterdir()):
            if f.is_file() and f.suffix == ".txt":
                module_name = f.stem
                current_modules.add(module_name)
                
                # Preserve existing state, set default enabled + unique priority for new modules
                if module_name not in self._module_states:
                    self._module_states[module_name] = {
                        "enabled": True,
                        "priority": self._get_next_priority()
                    }
        
        # Purge states for modules that no longer exist on disk
        deleted_modules = [m for m in self._module_states if m not in current_modules]
        for m in deleted_modules:
            del self._module_states[m]
        
        # Use SINGLE SOURCE OF TRUTH for ordering
        sorted_modules = self._get_module_order()
        
        # Rebuild table
        self.module_table.blockSignals(True)
        self.module_table.setRowCount(len(sorted_modules))
        
        for row, module_name in enumerate(sorted_modules):
            state = self._module_states.get(module_name, {"enabled": True, "priority": 100})
            enabled = state.get("enabled", True)
            
            # Order column - display letter label based on row position
            # Row 0 = A, Row 1 = B, Row 2 = C, etc.
            order_label = chr(ord('A') + row)
            order_item = QTableWidgetItem(order_label)
            order_item.setTextAlignment(Qt.AlignCenter)
            order_item.setData(Qt.UserRole, module_name)  # Store module name for lookup
            if not enabled:
                order_item.setForeground(Qt.gray)
            self.module_table.setItem(row, 0, order_item)
            
            # Filename column
            name_item = QTableWidgetItem(module_name)
            if not enabled:
                name_item.setForeground(Qt.gray)
            self.module_table.setItem(row, 1, name_item)
            
            # Enabled column
            enabled_item = QTableWidgetItem("✓" if enabled else "✗")
            enabled_item.setTextAlignment(Qt.AlignCenter)
            enabled_item.setForeground(Qt.green if enabled else Qt.red)
            self.module_table.setItem(row, 2, enabled_item)
        
        self.module_table.blockSignals(False)

    def _on_module_selected(self, item):
        """Handle module selection from table."""
        if not item:
            return
        row = item.row()
        name_item = self.module_table.item(row, 1)
        if not name_item:
            return
        self._current_module = name_item.text()
        
        # Load and display module preview
        self._load_module_preview(self._current_module)
        
        # Update move button states
        self._update_move_button_states()

    def _load_module_preview(self, module_name: str):
        """Load and preview a module file."""
        modules_dir = self._get_modules_dir()
        module_path = modules_dir / f"{module_name}.txt"
        
        if module_path.exists():
            try:
                with open(module_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.module_preview_text.setPlainText(content[:500] + ("..." if len(content) > 500 else ""))
            except Exception as e:
                self.module_preview_text.setPlainText(f"Error loading module: {e}")
        else:
            self.module_preview_text.setPlainText("Module file not found")

    def _on_move_up(self):
        """Move selected module up (decrease priority number)."""
        if not self._current_module:
            QMessageBox.information(self, "No Selection", "Select a module to move.")
            return
        
        current_priority = self._module_states[self._current_module].get("priority", 100)
        
        # Find module with next lower priority (the one above)
        # Uses SINGLE SOURCE OF TRUTH: _get_module_order()
        sorted_modules = self._get_module_order()
        
        # Find current index
        try:
            current_idx = sorted_modules.index(self._current_module)
        except ValueError:
            return
        
        if current_idx == 0:
            # Already at top
            return
        
        # Swap priorities with the module above
        above_module = sorted_modules[current_idx - 1]
        above_priority = self._module_states[above_module].get("priority", 100)
        
        self._module_states[self._current_module]["priority"] = above_priority
        self._module_states[above_module]["priority"] = current_priority
        
        # Save to profile
        self._save_module_states_to_profile()
        
        # Refresh display
        self._refresh_module_list()
        self._log(f"Moved '{self._current_module}' up")
        
        # Re-select current module
        self._reselect_current_module()
        
        # Refresh preview after move operation
        self._update_final_prompt_preview()

    def _on_move_down(self):
        """Move selected module down (increase priority number)."""
        if not self._current_module:
            QMessageBox.information(self, "No Selection", "Select a module to move.")
            return
        
        # Find module with next higher priority (the one below)
        # Uses SINGLE SOURCE OF TRUTH: _get_module_order()
        sorted_modules = self._get_module_order()
        
        # Find current index
        try:
            current_idx = sorted_modules.index(self._current_module)
        except ValueError:
            return
        
        if current_idx >= len(sorted_modules) - 1:
            # Already at bottom
            return
        
        # Swap priorities with the module below
        below_module = sorted_modules[current_idx + 1]
        below_priority = self._module_states[below_module].get("priority", 100)
        current_priority = self._module_states[self._current_module].get("priority", 100)
        
        self._module_states[self._current_module]["priority"] = below_priority
        self._module_states[below_module]["priority"] = current_priority
        
        # Save to profile
        self._save_module_states_to_profile()
        
        # Refresh display
        self._refresh_module_list()
        self._log(f"Moved '{self._current_module}' down")
        
        # Re-select current module
        self._reselect_current_module()
        
        # Refresh preview after move operation
        self._update_final_prompt_preview()

    def _reselect_current_module(self):
        """Re-select the current module in the table after refresh.
        
        Calls selectRow to select the row, then explicitly refreshes:
        - Module preview text
        - Move button states
        
        This ensures UI fully refreshes after enable/disable and move operations.
        """
        for row in range(self.module_table.rowCount()):
            name_item = self.module_table.item(row, 1)
            if name_item and name_item.text() == self._current_module:
                self.module_table.selectRow(row)
                
                # Explicitly refresh preview (selectRow does NOT trigger itemClicked)
                self._load_module_preview(self._current_module)
                self._update_move_button_states()
                
                break
    
    def _update_move_button_states(self):
        """Update enabled/disabled state of move buttons based on position."""
        if not self._current_module:
            return
        
        # Uses SINGLE SOURCE OF TRUTH: _get_module_order()
        sorted_modules = self._get_module_order()
        
        try:
            current_idx = sorted_modules.index(self._current_module)
        except ValueError:
            return
        
        # Get move buttons from layout
        pass

    def _add_module(self):
        """Add a new module."""
        from PySide6.QtWidgets import QInputDialog
        
        modules_dir = self._get_modules_dir()
        
        # Generate default name
        existing = [f.stem for f in modules_dir.iterdir() if f.is_file() and f.suffix == ".txt"]
        counter = 1
        while f"new_module_{counter}" in existing:
            counter += 1
        default_name = f"new_module_{counter}"
        
        # Get name from user
        name, ok = QInputDialog.getText(self, "Add Module", "Enter module name:")
        if not ok or not name:
            return
        
        # Sanitize name
        name = "".join(c for c in name if c.isalnum() or c in "_-")
        if not name:
            QMessageBox.warning(self, "Invalid Name", "Module name must be alphanumeric.")
            return
        
        module_path = modules_dir / f"{name}.txt"
        if module_path.exists():
            QMessageBox.warning(self, "Exists", f"Module '{name}' already exists.")
            return
        
        # Create empty module with unique priority
        try:
            with open(module_path, "w", encoding="utf-8") as f:
                f.write(f"# {name}\n# Add your prompt content here\n")
            # Assign unique priority using _get_next_priority()
            self._module_states[name] = {
                "enabled": True,
                "priority": self._get_next_priority()
            }
            self._save_module_states_to_profile()
            self._refresh_module_list()
            self._log(f"Added module: {name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create module: {e}")

    def _rename_module(self):
        """Rename the selected module."""
        if not self._current_module:
            QMessageBox.information(self, "No Selection", "Select a module to rename.")
            return
        
        from PySide6.QtWidgets import QInputDialog
        
        old_name = self._current_module
        new_name, ok = QInputDialog.getText(self, "Rename Module", "Enter new name:", text=old_name)
        if not ok or not new_name:
            return
        
        # Sanitize name
        new_name = "".join(c for c in new_name if c.isalnum() or c in "_-")
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Module name must be alphanumeric.")
            return
        
        if new_name == old_name:
            return
        
        modules_dir = self._get_modules_dir()
        old_path = modules_dir / f"{old_name}.txt"
        new_path = modules_dir / f"{new_name}.txt"
        
        if new_path.exists():
            QMessageBox.warning(self, "Exists", f"Module '{new_name}' already exists.")
            return
        
        try:
            old_path.rename(new_path)
            
            # Transfer state
            state = self._module_states.pop(old_name, {"enabled": True})
            self._module_states[new_name] = state
            
            self._current_module = new_name
            self._refresh_module_list()
            self._log(f"Renamed module: {old_name} -> {new_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to rename module: {e}")

    def _duplicate_module(self):
        """Duplicate the selected module."""
        if not self._current_module:
            QMessageBox.information(self, "No Selection", "Select a module to duplicate.")
            return
        
        modules_dir = self._get_modules_dir()
        source_name = self._current_module
        source_path = modules_dir / f"{source_name}.txt"
        
        # Generate new name
        counter = 1
        while modules_dir / f"{source_name}_copy_{counter}.txt":
            if not (modules_dir / f"{source_name}_copy_{counter}.txt").exists():
                break
            counter += 1
        
        new_name = f"{source_name}_copy_{counter}"
        new_path = modules_dir / f"{new_name}.txt"
        
        try:
            shutil.copy2(source_path, new_path)
            
            # Copy state but assign UNIQUE priority to avoid collisions
            source_state = self._module_states.get(source_name, {"enabled": True})
            self._module_states[new_name] = {
                "enabled": source_state.get("enabled", True),
                "priority": self._get_next_priority()
            }
            
            self._save_module_states_to_profile()
            self._current_module = new_name
            self._refresh_module_list()
            self._log(f"Duplicated module: {source_name} -> {new_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to duplicate module: {e}")

    def _delete_module(self):
        """Delete the selected module."""
        if not self._current_module:
            QMessageBox.information(self, "No Selection", "Select a module to delete.")
            return
        
        module_name = self._current_module
        
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete module '{module_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        modules_dir = self._get_modules_dir()
        module_path = modules_dir / f"{module_name}.txt"
        
        try:
            module_path.unlink()
            self._module_states.pop(module_name, None)
            self._current_module = None
            self.module_preview_text.clear()
            self._refresh_module_list()
            self._log(f"Deleted module: {module_name}")
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to delete module: {e}")


    def _edit_module(self):
        """Edit the selected module in an external editor."""
        if not self._current_module:
            QMessageBox.information(self, "No Selection", "Select a module to edit.")
            return
        
        modules_dir = self._get_modules_dir()
        module_path = modules_dir / f"{self._current_module}.txt"
        
        if not module_path.exists():
            QMessageBox.warning(self, "Not Found", "Module file not found.")
            return
        
        try:
            # Open in default text editor
            import subprocess
            if sys.platform == "win32":
                os.startfile(str(module_path))
            elif sys.platform == "darwin":
                subprocess.run(["open", str(module_path)])
            else:
                subprocess.run(["xdg-open", str(module_path)])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open editor: {e}")


    def _on_module_enabled_toggle(self, state: int):
        """Toggle enabled state for the selected module from the action bar checkbox."""
        if not self._current_module:
            self.module_enabled_checkbox.setCheckState(2)  # default checked
            return
        is_enabled = state == 2  # Qt.Checked == 2
        if self._current_module in self._module_states:
            self._module_states[self._current_module]["enabled"] = is_enabled
            self._refresh_module_list()
            self._log(f"Module '{self._current_module}' enabled={is_enabled}")
        # Refresh preview after state change
        self._update_final_prompt_preview()


    def _create_bottom_panel(self) -> QWidget:
        # Container for bottom area
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Horizontal splitter: LEFT = output tabs, RIGHT = prompt workspace
        self.bottom_splitter = QSplitter(Qt.Horizontal)

        # === LEFT: OUTPUT TABS ===
        self.output_tabs = QTabWidget()

        self.raw_output_text = QTextEdit()
        self.raw_output_text.setReadOnly(True)
        self.raw_output_text.setStyleSheet("font-family: monospace; background: #1e1e1e; color: #d4d4d4;")
        self.output_tabs.addTab(self.raw_output_text, "Raw Output")

        self.clean_output_text = QTextEdit()
        self.clean_output_text.setReadOnly(True)
        self.clean_output_text.setStyleSheet("font-family: monospace; background: #1e1e1e; color: #9cdcfe;")
        self.output_tabs.addTab(self.clean_output_text, "Clean Output")

        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        self.logs_text.setStyleSheet("font-family: monospace; background: #0d0d0d; color: #00ff00;")
        self.output_tabs.addTab(self.logs_text, "Logs")

        self.bottom_splitter.addWidget(self.output_tabs)

        # === RIGHT: PROMPT WORKSPACE (RB3.3.6 Tab Refactor) ===
        prompt_panel = QWidget()
        prompt_layout = QVBoxLayout(prompt_panel)
        prompt_layout.setContentsMargins(4, 4, 4, 4)
        prompt_layout.setSpacing(8)

        # Header
        header_lbl = QLabel("PROMPT WORKSPACE")
        header_lbl.setStyleSheet("font-weight: bold; color: #aaa; font-size: 11px;")
        prompt_layout.addWidget(header_lbl)

        # Tab Widget: Final Prompt / Metadata
        self.prompt_workspace_tabs = QTabWidget()

        # Tab 1: Final Prompt (default selected, index 0)
        self.final_prompt_text = QTextEdit()
        self.final_prompt_text.setReadOnly(True)
        self.final_prompt_text.setPlaceholderText("RB3.5 Reserved")
        self.final_prompt_text.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
            }
        """)
        self.prompt_workspace_tabs.addTab(self.final_prompt_text, "Final Prompt")

        # Tab 2: Metadata
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setPlaceholderText("RB3.4 Reserved")
        self.metadata_text.setStyleSheet("""
            QTextEdit {
                font-family: monospace;
                background: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
            }
        """)
        self.prompt_workspace_tabs.addTab(self.metadata_text, "Metadata")

        # Set Final Prompt as default tab
        self.prompt_workspace_tabs.setCurrentIndex(0)

        prompt_layout.addWidget(self.prompt_workspace_tabs)

        self.bottom_splitter.addWidget(prompt_panel)

        # Set initial sizes (output 60%, prompt 40%)
        self.bottom_splitter.setSizes([400, 250])

        layout.addWidget(self.bottom_splitter)

        return container

    # -------------------------------------------------------------------------
    # PACKAGE LOADING
    # -------------------------------------------------------------------------

    def load_package_folder(self):
        """Load a runtime package directory exported by SceneFlow.py."""
        folder = QFileDialog.getExistingDirectory(
            self, "Select Package Directory",
            str(Path.cwd() / "output")
        )
        if not folder:
            return

        self.current_package_dir = folder
        self.package_path_label.setText(folder)
        self.package_path_label.setStyleSheet("color: #0f0;")

        # Validate package structure (NEW runtime contract)
        pkg_path = Path(folder)
        has_frames = (pkg_path / "frames").exists()
        has_timeline = (pkg_path / "runtime_timeline.json").exists()
        has_manifest = (pkg_path / "runtime_manifest.json").exists()

        if not has_frames and not has_timeline:
            self._log("WARNING: Package structure incomplete - missing frames/ and runtime_timeline.json")

        # Load the package data
        self.package_data = load_package_data(folder)
        self.scene_list = build_scene_list_from_package(self.package_data)

        # Populate scene list widget
        self.scene_list_widget.clear()
        manifest_display = self.package_data.get("manifest", {}).get("video_name",
                         self.package_data.get("manifest", {}).get("name", "Package"))

        for scene in self.scene_list:
            dur = scene['duration']
            dur_str = f" ({dur:.1f}s)" if dur > 0 else ""
            # Build context indicators
            indicators = []
            if scene.get("has_subtitle"):
                indicators.append("[SUB]")
            audio_type = scene.get("audio_type", "unknown")
            if audio_type == "music":
                indicators.append("[MUSIC]")
            elif audio_type == "silence" or audio_type == "silent":
                indicators.append("[SILENCE]")
            ind_str = " " + " ".join(indicators) if indicators else ""
            
            self.scene_list_widget.addItem(f"{scene['name']}{dur_str}{ind_str}")

        # Log package info
        frames_count = len(self.package_data.get("frames", []))
        timeline_count = len(self.package_data.get("timeline", []))
        has_subtitles = "Yes" if self.package_data.get("subtitles_data") else "No"
        has_audio = "Yes" if self.package_data.get("audio_regions") else "No"

        self._log(f"Loaded package: {manifest_display}")
        self._log(f"  Frames: {frames_count}")
        self._log(f"  Timeline entries: {timeline_count}")
        self._log(f"  Timeline source: runtime_timeline.json")
        # Track actual loaded file for accurate logging
        subtitles_file = "runtime_subtitles.json" if (Path(folder) / "runtime_subtitles.json").exists() else "source_subtitles.json"
        audio_file = "runtime_audio_regions.json" if (Path(folder) / "runtime_audio_regions.json").exists() else "source_audio_regions.json"
        subtitles_count = len(self.package_data.get("subtitles_data", []))
        audio_count = len(self.package_data.get("audio_regions", []))
        self._log(f"  Subtitles: {has_subtitles} ({subtitles_file})")
        self._log(f"  Loaded runtime subtitles: {subtitles_count}")
        self._log(f"  Audio regions: {has_audio} ({audio_file})")
        self._log(f"  Loaded runtime audio regions: {audio_count}")

        if len(self.scene_list) > 0:
            self._log(f"Loaded {len(self.scene_list)} scene(s) from package")

        # Auto-select first scene
        if self.scene_list_widget.count() > 0:
            self.scene_list_widget.setCurrentRow(0)
            self._on_scene_selected()

    # -------------------------------------------------------------------------
    # UI EVENTS
    # -------------------------------------------------------------------------

    def _on_provider_changed(self, provider: str):
        """Handle provider selection change."""
        self.provider = provider
        self._log(f"Provider changed to: {provider}")
        self._refresh_models()
        self._save_config()

    def _on_base_url_changed(self):
        """Handle base URL text change."""
        self.base_url = self.base_url_input.toPlainText().strip()
        self._save_config()

    def _refresh_models(self):
        """Fetch available models from current provider."""
        self._log(f"Fetching models from {self.provider} at {self.base_url}...")
        self.model_fetch_worker = ModelFetchWorker(self.provider, self.base_url)
        self.model_fetch_worker.finished.connect(self._on_models_loaded)
        self.model_fetch_worker.error.connect(self._on_models_error)
        self.model_fetch_worker.start()

    def _on_models_loaded(self, models: List[str]):
        """Handle models loaded successfully."""
        self.available_models = models
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
            # Restore selected model if still available
            if self.model_name in models:
                self.model_combo.setCurrentText(self.model_name)
            else:
                self.model_combo.setCurrentIndex(0)
                self.model_name = self.model_combo.currentText()
            self._log(f"Loaded {len(models)} models")
        else:
            self.model_combo.addItem("(no models found)")
            self._log("No models found")
        self.model_combo.blockSignals(False)

    def _on_models_error(self, error: str):
        """Handle model fetch error."""
        self._log(f"Model fetch error: {error}")
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItem("(fetch error)")
        self.model_combo.blockSignals(False)

    def _on_scene_selected(self, _item=None):
        idx = self.scene_list_widget.currentRow()
        if 0 <= idx < len(self.scene_list):
            self.selected_scene = self.scene_list[idx]
            self._load_scene_analysis_for_display()
            self._update_scene_preview()
            self._update_metadata_registry()
            self._update_final_prompt_preview()
            self._log(f"Selected scene: {self.selected_scene['name']}")

    def _on_scene_row_changed(self, _current_row):
        """Handle keyboard Up/Down navigation on scene list.
        
        Fires same callback chain as _on_scene_selected to sync all UI panels.
        """
        idx = self.scene_list_widget.currentRow()
        if 0 <= idx < len(self.scene_list):
            self.selected_scene = self.scene_list[idx]
            self._load_scene_analysis_for_display()
            self._update_scene_preview()
            self._update_metadata_registry()
            self._update_final_prompt_preview()
            self._log(f"KB nav selected scene: {self.selected_scene['name']}")

    def _load_scene_analysis_for_display(self):
        """Load saved analysis from analysis/scene_src_XXXX.json and display in output panels.

        All analysis data is loaded directly from saved files.
        """
        if not self.selected_scene or not self.current_package_dir:
            return

        scene = self.selected_scene
        scene_id = scene.get('id', scene.get('source_scene_id', ''))

        # Get immutable scene_src_XXXX filename
        scene_num = extract_scene_number(scene_id)
        source_id = format_source_scene_id(scene_num)
        analysis_file = get_analysis_dir(self.current_package_dir) / f"{source_id}.json"

        if not analysis_file.exists():
            # No saved analysis yet
            self.raw_output_text.setPlainText("")
            self.clean_output_text.setPlainText("")
            return

        try:
            with open(analysis_file, "r", encoding="utf-8") as f:
                analysis_data = json.load(f)

            # Load raw_model_output for Raw Output tab
            raw_output = analysis_data.get("raw_model_output", "")
            self.raw_output_text.setPlainText(raw_output)

            # Extract and display OUTPUT_BLOCK in Clean Output tab (if present)
            raw_text = raw_output
            block_pattern = re.compile(
                r'(<<OUTPUT_BLOCK>>\s*.*?\s*<</OUTPUT_BLOCK>>)',
                re.DOTALL | re.IGNORECASE
            )
            match = block_pattern.search(raw_text)
            if match:
                self.clean_output_text.setPlainText(match.group(1).strip())
            else:
                self.clean_output_text.setPlainText(raw_text.strip())

            self._log(f"Loaded analysis from {analysis_file.name}")

        except Exception as e:
            self._log(f"Failed to load analysis file: {e}")
            self.raw_output_text.setPlainText("")
            self.clean_output_text.setPlainText("")


    def _update_scene_preview(self):
        """Update scene preview using pre-exported PNG frame from package."""
        if not self.selected_scene:
            return

        s = self.selected_scene
        frame_path = s.get('frame') or s.get('path')
        dur = s['duration']
        dur_str = f"{dur:.1f}s" if dur > 0 else "N/A"
        timeline_entry = s.get('timeline_entry', {})

        # Get timeline info
        start_time = s.get('start_time', 0)
        end_time = s.get('end_time', 0)
        if timeline_entry:
            start_time = timeline_entry.get("start_sec", timeline_entry.get("start", start_time))
            end_time = timeline_entry.get("end_sec", timeline_entry.get("end", end_time))

        # Get subtitle info
        subtitle_text = s.get("subtitle_text", "")
        has_subtitle = s.get("has_subtitle", False)

        # Get audio info
        audio_type = s.get("audio_type", "unknown")
        audio_energy = s.get("audio_energy", 0.0)

        # Build structured info panel
        info_parts = [
            f"<b>Scene:</b> {s['name']}",
            f"<b>Timeline:</b> {start_time:.1f}s -> {end_time:.1f}s",
            f"<b>Duration:</b> {dur_str}"
        ]

        # Subtitle section
        if has_subtitle and subtitle_text:
            info_parts.append(f"<b>Subtitle:</b> <span style='color:#0f0'>YES</span>")
            info_parts.append(f"<b>Subtitle Preview:</b> <span style='color:#0ff'>{subtitle_text[:80]}{'...' if len(subtitle_text) > 80 else ''}</span>")
        else:
            info_parts.append(f"<b>Subtitle:</b> <span style='color:#f00'>NONE</span>")

        # Audio section
        info_parts.append(f"<b>Audio:</b> {audio_type} (energy: {audio_energy:.2f})")

        info = "<br>".join(info_parts)
        if frame_path:
            info += f"<br><br><b>Frame:</b> {Path(frame_path).name}"
        self.scene_info_label.setText(info)
        self.scene_info_label.setStyleSheet("color: #ccc;")

        # Load and display the PNG frame directly
        if frame_path and os.path.exists(frame_path):
            pixmap = QPixmap(frame_path)
            if not pixmap.isNull():
                # Display in frame display label
                scaled = pixmap.scaled(
                    self.frame_display_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.frame_display_label.setPixmap(scaled)
                self.frame_display_label.setStyleSheet("border: 1px solid #0f0;")

                # Display in preview label
                preview_scaled = pixmap.scaled(
                    self.preview_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(preview_scaled)
                self.preview_label.setStyleSheet("border: 1px solid #0f0;")

                self._log(f"Loaded frame: {Path(frame_path).name}")
            else:
                self._log(f"Failed to load frame: {frame_path}")
                self.frame_display_label.setText("Invalid image")
                self.frame_display_label.setStyleSheet("border: 1px solid #f00;")
                self.preview_label.setText("Invalid image")
                self.preview_label.setStyleSheet("border: 1px solid #f00;")
        else:
            self._log(f"No frame available for scene: {s['name']}")
            self.frame_display_label.clear()
            self.frame_display_label.setText("No frame available")
            self.frame_display_label.setStyleSheet("border: 1px solid #444; background: #1a1a1a;")

    def _update_metadata_registry(self):
        """Build runtime metadata registry from current scene and populate Metadata tab.

        Registry is read-only display data. No analysis, no Ollama calls.
        Uses already-loaded scene information only.
        """
        self.metadata_registry = {}

        if not self.selected_scene:
            self.metadata_text.setPlainText("No scene selected")
            return

        s = self.selected_scene
        
        scene_id = s.get('id', 'N/A')
        frame_file = s.get('frame') or s.get('path', 'N/A')
        dur = s.get('duration', 0)

        # Derive analysis file path
        analysis_file = "N/A"
        if self.current_package_dir:
            scene_num = extract_scene_number(scene_id)
            source_id = format_source_scene_id(scene_num)
            analysis_path = get_analysis_dir(self.current_package_dir) / f"{source_id}.json"
            if analysis_path.exists():
                analysis_file = f"{source_id}.json"

        # Get timeline info
        timeline_entry = s.get('timeline_entry', {})
        start_time = s.get('start_time', 0)
        end_time = s.get('end_time', 0)
        if timeline_entry:
            start_time = timeline_entry.get("start_sec", timeline_entry.get("start", start_time))
            end_time = timeline_entry.get("end_sec", timeline_entry.get("end", end_time))

        # Get subtitle
        subtitle_text = s.get("subtitle_text", "")
        has_subtitle = s.get("has_subtitle", False)
        subtitle_display = subtitle_text if (has_subtitle and subtitle_text) else "N/A"

        # Get audio
        audio_type = s.get("audio_type", "N/A")
        audio_energy = s.get("audio_energy", 0.0)
        audio_energy_str = f"{audio_energy:.2f}" if audio_energy > 0 else "N/A"

        # Duration
        duration_str = f"{dur:.1f}s" if dur > 0 else "N/A"

        # Scene timestamps
        start_str = f"{start_time:.1f}s"
        end_str = f"{end_time:.1f}s"

        self.metadata_registry = {
            "scene_id": scene_id,
            "frame_file": Path(frame_file).name if frame_file and frame_file != "N/A" else "N/A",
            "analysis_file": analysis_file,
            "subtitle": subtitle_display[:100] + "..." if subtitle_display and len(subtitle_display) > 100 else subtitle_display,
            "audio_type": audio_type,
            "audio_energy": audio_energy_str,
            "duration": duration_str,
            "scene_start": start_str,
            "scene_end": end_str
        }

        # Build display text
        lines = []
        lines.append("=" * 36)
        lines.append("SCENE METADATA")
        lines.append("=" * 36)
        lines.append(f"Scene ID:")
        lines.append(f"  {scene_id}")
        lines.append(f"Frame:")
        lines.append(f"  {self.metadata_registry['frame_file']}")
        lines.append(f"Analysis File:")
        lines.append(f"  {analysis_file}")
        lines.append(f"Duration:")
        lines.append(f"  {duration_str}")
        lines.append(f"Scene Start:")
        lines.append(f"  {start_str}")
        lines.append(f"Scene End:")
        lines.append(f"  {end_str}")
        lines.append(f"Audio Type:")
        lines.append(f"  {audio_type}")
        lines.append(f"Audio Energy:")
        lines.append(f"  {audio_energy_str}")
        lines.append(f"Subtitle:")
        if subtitle_display == "N/A":
            lines.append(f"  N/A")
        else:
            for i in range(0, len(subtitle_display), 60):
                lines.append(f"  {subtitle_display[i:i+60]}")
        lines.append("=" * 36)

        self.metadata_text.setPlainText("\n".join(lines))

    # -------------------------------------------------------------------------
    # COMPILER
    # -------------------------------------------------------------------------

    def _update_final_prompt_preview(self):
        """Update the Final Prompt tab with compiled prompt preview.
        
        Readonly display only. No editing, no saving, no runtime.
        """
        # Guard: final_prompt_text may not exist during startup
        if not hasattr(self, 'final_prompt_text') or not self.final_prompt_text:
            return
        try:
            final_prompt = self._compile_final_prompt()
            if final_prompt:
                self.final_prompt_text.setPlainText(final_prompt)
            else:
                self.final_prompt_text.setPlainText("No prompt generated")
        except Exception:
            self.final_prompt_text.setPlainText("Prompt compilation failed")

    # -------------------------------------------------------------------------
    # PROVIDER CONFIG
    # -------------------------------------------------------------------------

    def _on_model_changed(self, model: str):
        if model and model not in ("(no models found)", "(fetch error)"):
            self.model_name = model
            self._log(f"Model changed to: {model}")
            self._save_config()

    def _load_config(self):
        """Load saved provider/model configuration."""
        config_path = Path(CONFIG_FILE)
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.provider = config.get("provider", DEFAULT_PROVIDER)
                self.base_url = config.get("base_url", DEFAULT_BASE_URL)
                self.model_name = config.get("model", DEFAULT_MODEL)
            except Exception:
                pass

    def _save_config(self):
        """Save provider/model configuration."""
        config = {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model_name,
        }
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Failed to save config: {e}")



    def _load_saved_prompts(self):
        """Stub: prompts are now loaded from Python files only - no persisted prompts."""
        pass

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.logs_text.append(f"[{ts}] {msg}")
        self.logs_text.moveCursor(QTextCursor.End)

    # -------------------------------------------------------------------------
    # UI LAYOUT PERSISTENCE (RB3.3.4)
    # -------------------------------------------------------------------------

    def _save_ui_layout(self) -> None:
        """Save current UI layout to config/ui_layout.json.
        
        Saves:
        - window_width/height
        - main_splitter sizes
        - bottom_splitter sizes
        """
        try:
            ensure_dir("config")
            layout_data = {
                "window_width": self.width(),
                "window_height": self.height(),
                "main_splitter": list(self.main_splitter.sizes()) if hasattr(self, "main_splitter") and self.main_splitter else [],
                "bottom_splitter": list(self.bottom_splitter.sizes()) if hasattr(self, "bottom_splitter") and self.bottom_splitter else []
            }
            with open(UI_LAYOUT_FILE, "w", encoding="utf-8") as f:
                json.dump(layout_data, f, indent=2)
        except Exception as e:
            print(f"Failed to save UI layout: {e}")

    def _restore_ui_layout(self) -> None:
        """Restore UI layout from config/ui_layout.json.
        
        Restores:
        - window size
        - main_splitter sizes
        - bottom_splitter sizes
        
        Silently ignores missing file or invalid data.
        """
        try:
            layout_path = Path(UI_LAYOUT_FILE)
            if not layout_path.exists():
                return
            
            with open(layout_path, "r", encoding="utf-8") as f:
                layout_data = json.load(f)
            
            if not isinstance(layout_data, dict):
                return
            
            # Restore window size
            width = layout_data.get("window_width", 1400)
            height = layout_data.get("window_height", 900)
            self.resize(width, height)
            
            # Restore main splitter sizes
            if hasattr(self, "main_splitter") and self.main_splitter:
                main_sizes = layout_data.get("main_splitter", [])
                if isinstance(main_sizes, list) and len(main_sizes) >= 3:
                    self.main_splitter.setSizes(main_sizes)
            
            # Restore bottom splitter sizes
            if hasattr(self, "bottom_splitter") and self.bottom_splitter:
                bottom_sizes = layout_data.get("bottom_splitter", [])
                if isinstance(bottom_sizes, list) and len(bottom_sizes) >= 2:
                    self.bottom_splitter.setSizes(bottom_sizes)
                    
        except Exception as e:
            print(f"Failed to restore UI layout: {e}")

    def closeEvent(self, event):
        """Clean up threads and save UI layout on window close."""
        self._save_ui_layout()
        try:
            if hasattr(self, "model_fetch_worker") and self.model_fetch_worker:
                self.model_fetch_worker.quit()
                self.model_fetch_worker.wait()
        except Exception:
            pass
        event.accept()


# ============================================================================
# MAIN
# ============================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow { background-color: #1a1a1a; }
        QWidget { background-color: #1a1a1a; color: #e0e0e0; }
        QGroupBox {
            border: 1px solid #444; border-radius: 4px;
            margin-top: 8px; font-weight: bold;
        }
        QGroupBox::title {
            subcontrol-origin: margin; subcontrol-position: top left;
            padding: 0 4px; color: #aaa;
        }
        QPushButton {
            background-color: #2a2a2a; border: 1px solid #444;
            padding: 6px 12px; border-radius: 4px;
        }
        QPushButton:hover { background-color: #3a3a3a; border-color: #0f0; }
        QPushButton:pressed { background-color: #1a1a1a; }
        QPushButton:disabled { background-color: #222; color: #666; }
        QListWidget {
            background-color: #222; border: 1px solid #444; outline: none;
        }
        QListWidget::item:selected { background-color: #0f0; color: #000; }
        QListWidget::item:hover { background-color: #333; }
        QTextEdit { background-color: #1e1e1e; border: 1px solid #333; color: #d4d4d4; }
        QTabWidget::pane { border: 1px solid #444; background-color: #1e1e1e; }
        QTabBar::tab {
            background-color: #2a2a2a; padding: 6px 12px; border: 1px solid #444;
        }
        QTabBar::tab:selected { background-color: #0f0; color: #000; }
        QComboBox {
            background-color: #2a2a2a; border: 1px solid #444;
            padding: 4px 8px; border-radius: 3px;
        }
        QComboBox::drop-down { border: none; }
        QProgressBar {
            border: 1px solid #444; border-radius: 4px;
            background-color: #222; text-align: center;
        }
        QProgressBar::chunk { background-color: #0f0; }
        QLabel { color: #e0e0e0; }
        QScrollBar:vertical { background-color: #222; width: 12px; }
        QScrollBar::handle:vertical {
            background-color: #444; border-radius: 6px;
        }
        QScrollBar::handle:vertical:hover { background-color: #555; }
        QScrollBar:horizontal { background-color: #222; height: 12px; }
        QScrollBar::handle:horizontal {
            background-color: #444; border-radius: 6px;
        }
    """)

    window = PackageLoader()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()