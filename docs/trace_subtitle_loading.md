# TRACE: Subtitle Loading Flow (package_loader.py)

## Flow Path

1. `load_package_folder()` (line 1463)
   → `load_package_data(folder)` (line 1486)
   → reads `runtime_subtitles.json` (lines 800-838)
   → stores in `result["subtitles_data"]`
   → returns `package_data`

2. `build_scene_list_from_package(package_data)` (line 1487)
   → extracts `subtitles = package_data.get("subtitles_data", [])` (line 1028)
   → calls `enrich_scenes_with_context(scenes, subtitles, audio_regions)` (line 1030)
   → sets `scene["has_subtitle"]` and `scene["subtitle_text"]`

3. UI logs:
   - `has_subtitles = "Yes" if self.package_data.get("subtitles_data") else "No"` (line 1516)
   - `subtitles_count = len(self.package_data.get("subtitles_data", []))` (line 1526)

## Root Cause Analysis

### Problem
`subtitles_data` is `[]` (empty) after loading, even though `runtime_subtitles.json` exists.

### Why

The function `parse_subtitle_json()` (line 239) is the final step that extracts subtitle entries from raw JSON data. It has a strict key check:

```python
text = sub.get("text", "").strip()
if text:
    parsed.append(...)
```

**Bug:** It ONLY checks for key `"text"`. If the actual `runtime_subtitles.json` file uses a different key name for the subtitle text field (e.g., `"subtitle_text"`, `"content"`, `"caption"`), then `text` is `""` for ALL items → ALL items are filtered out → `subtitles_data` = `[]`.

This matches the reported symptom:
- File exists ✓
- JSON loads ✓
- Structure is recognized (key "subtitles" or flat list) ✓
- But `parse_subtitle_json` returns `[]` because text field key mismatch

### Same issue affects time fields

`parse_subtitle_json` also only checks `"start"` and `"end"` keys. If the file uses `"start_sec"`/`"end_sec"` or `"start_time"`/`"end_time"`, timestamps default to 0/1, causing overlap matching to silently fail even if text IS found.

## Fix

Make `parse_subtitle_json` check alternative key names for both text and time fields.

## NOT touched
- Audio loading
- Batch parser
- Semantic parser
- Prompt compile
- AI/Ollama requests
- Group analysis
- Architecture rewrite