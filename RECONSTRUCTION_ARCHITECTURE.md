# RECONSTRUCTION ARCHITECTURE

**Version:** Phase 4.0
**Status:** Contract Defined
**Date:** 2026-06-01

---

## 1. PURPOSE

APP4 — Reconstruction nhận grouping decisions từ APP3, reconstruct video clips từ source package.

**APP4 KHÔNG:**
- ❌ Dùng AI
- ❌ Gọi LLM
- ❌ Phân tích ảnh
- ❌ Phân tích metadata

**APP4 CHỈ:**
- ✅ Đọc grouping decisions
- ✅ Tra timestamp từ source package
- ✅ Cut video clips
- ✅ Export với đúng naming

---

## 2. GOLDEN RULES

### Rule 1 — APP4 is a pure reconstructor

APP4 không quyết định scene nào dùng, scene nào bỏ.
APP3 đã quyết định. APP4 chỉ thực thi.

### Rule 2 — Scene ID là immutable xuyên suốt

```
scene_src_0067  (APP1)
    ↓
scene_src_0067.mp4  (APP4 output, giữ nguyên ID)
```

**FORBIDDEN:**
- Đổi ID
- Re-index
- Tạo scene ID mới
- Đổi tên file

### Rule 3 — Audio giữ nguyên gốc

Khi cut MP4:
- Giữ nguyên audio stream gốc
- Không re-encode audio
- Không xử lý audio
- Copy audio stream thẳng vào output

### Rule 4 — Frame Accurate Output

**Default: Frame Accurate Mode**
- Re-encode video để đảm bảo frame-perfect cuts
- Target: ffmpeg với frame-accurate seeking
- Use case: production-quality recap

**Optional: Stream Copy Mode**
- Chỉ dùng khi user chọn hoặc quality='source_copy'
- Copy stream không re-encode
- Faster nhưng không đảm bảo frame-perfect

---

## 3. INPUTS

### Source 1 — Grouping Package

**Location:** `output/<project>/packages/grouping/`

| File | Required | Usage |
|---|---|---|
| `group_manifest.json` | **YES** | Entry point. Đọc trước tiên |
| `group_0001.json` | **YES** | Scene IDs + metadata per group |
| `group_0002.json` | **YES** | Scene IDs + metadata per group |
| ... | ... | ... |

### Source 2 — Source Package

**Location:** `output/<project>/source/`

| File | Required | Usage |
|---|---|---|
| `source_reconstruction_map.json` | **YES** | **PRIMARY** — scene_id → timestamp lookup |
| `source_master_timeline.json` | **YES** | Fallback — verify continuity |
| `source_subtitles.json` | Optional | Embed vào output nếu cần |
| `source_audio_regions.json` | Optional | Audio segment info |

### Source 3 — Video File

**Location:** Đường dẫn trong `source_reconstruction_map.json`
**Format:** MP4 (H.264/AAC)

---

## 4. TIMESTAMP AUTHORITY

### Priority Stack

| Priority | Source | Khi nào dùng |
|---|---|---|
| **1 (HIGHEST)** | `source_reconstruction_map.json` | Luôn dùng trước |
| **2** | `source_master_timeline.json` | Fallback nếu reconstruction_map không có |
| **3** | `group_XXXX.json` | **CHỈ** lấy scene_ids, KHÔNG lấy timestamp |

### Lookup Process

```
Với mỗi scene_id từ group_XXXX.json:
    1. Tra source_reconstruction_map.json[scene_id]
    2. Nếu có → dùng source_start_time, source_end_time
    3. Nếu không có → tra source_master_timeline.json[scene_id]
    4. Nếu không có → ERROR: missing timestamp for scene_id
```

### reconstruction_map.json Schema

```json
{
  "version": "1.0",
  "video_source_path": "/path/to/naruto_ep01.mp4",
  "total_scenes": 50,
  "scenes": [
    {
      "scene_id": "scene_src_0001",
      "source_scene_id": "src_0001",
      "source_start_time": 0.0,
      "source_end_time": 15.3,
      "source_duration": 15.3,
      "frame_count": 460
    }
  ]
}
```

---

## 5. OUTPUT STRUCTURE

### Directory Layout

```
output/<project>/
├── final/
│   ├── final_manifest.json      ← ROOT: tổng hợp tất cả groups
│   ├── reconstruction_report.json ← ROOT: provenance + errors
│   ├── 0001/                    ← Group folder (group_order = 1)
│   │   ├── scene_src_0008.mp4
│   │   ├── scene_src_0012.mp4
│   │   └── scene_src_0015.mp4
│   ├── 0002/                    ← Group folder (group_order = 2)
│   │   ├── scene_src_0030.mp4
│   │   └── scene_src_0035.mp4
│   └── 0003/
│       └── ...
```

### Naming Convention

```
CORRECT:
scene_src_0008.mp4
scene_src_0012.mp4
scene_src_0015.mp4
```

```
FORBIDDEN:
clip_001.mp4           ✗
group_001_scene.mp4    ✗
final_video.mp4        ✗
temp.mp4               ✗
scene_8.mp4            ✗
video_12.mp4           ✗
```

**Giữ nguyên scene_id từ APP1. KHÔNG re-index. KHÔNG rename.**

---

## 6. FINAL_MANIFEST.JSON

**Location:** `output/<project>/final/final_manifest.json`
**Owner:** APP4
**Purpose:** Tổng hợp tất cả groups cho creator

```json
{
  "manifest_version": "1.1",
  "project": "naruto_review_v2",
  "grouping_mode": "review",
  "total_groups": 5,
  "total_scenes": 18,
  "total_duration": 245.7,
  "export_quality": "frame_accurate",
  "export_date": "2026-06-01T12:00:00Z",
  "groups": [
    {
      "group_id": "group_0001",
      "group_order": 1,
      "scene_ids": ["scene_src_0010", "scene_src_0015", "scene_src_0021"],
      "match_confidence": 0.85,
      "group_summary": "Minato học phép thuật dưới sự quan sát của Sơn Thần",
      "clips": [
        {
          "scene_id": "scene_src_0010",
          "file": "scene_src_0010.mp4",
          "duration": 15.2,
          "start_time": 120.5,
          "end_time": 135.7
        },
        {
          "scene_id": "scene_src_0015",
          "file": "scene_src_0015.mp4",
          "duration": 22.1,
          "start_time": 145.2,
          "end_time": 167.3
        },
        {
          "scene_id": "scene_src_0021",
          "file": "scene_src_0021.mp4",
          "duration": 18.5,
          "start_time": 178.9,
          "end_time": 197.4
        }
      ],
      "total_duration": 55.8
    },
    {
      "group_id": "group_0002",
      "group_order": 2,
      "scene_ids": ["scene_src_0030", "scene_src_0035"],
      "match_confidence": 0.72,
      "group_summary": "Minato gặp lại Naruto",
      "clips": [
        {
          "scene_id": "scene_src_0030",
          "file": "scene_src_0030.mp4",
          "duration": 20.3,
          "start_time": 210.0,
          "end_time": 230.3
        },
        {
          "scene_id": "scene_src_0035",
          "file": "scene_src_0035.mp4",
          "duration": 15.9,
          "start_time": 245.0,
          "end_time": 260.9
        }
      ],
      "total_duration": 36.2
    }
  ]
}
```

### Immutable Fields (from APP3)

```
group_id
group_order
scene_ids
match_confidence
group_summary
```

### APP4-Generated Fields

```
clips[].duration
clips[].start_time
clips[].end_time
clips[].file
total_duration
total_groups
total_scenes
total_duration
export_quality
export_date
```

---

## 7. RECONSTRUCTION_REPORT.JSON

**Location:** `output/<project>/final/reconstruction_report.json`
**Owner:** APP4
**Purpose:** Provenance + debugging

```json
{
  "report_version": "1.0",
  "project": "naruto_review_v2",
  "reconstruction_start": "2026-06-01T12:00:00Z",
  "reconstruction_end": "2026-06-01T12:05:32Z",
  "duration_seconds": 332,
  "total_groups_processed": 5,
  "total_scenes_processed": 18,
  "success_count": 17,
  "failed_count": 1,
  "quality_mode": "frame_accurate",
  "ffmpeg_version": "6.0",
  "source_package": "output/naruto_review_v2/source/",
  "grouping_package": "output/naruto_review_v2/packages/grouping/",
  "source_video": "/path/to/naruto_ep01.mp4",
  "reconstruction_map_version": "1.0",
  "failed_scenes": [
    {
      "scene_id": "scene_src_0015",
      "group_id": "group_0001",
      "error": "ffmpeg cut failed: seek error at 145.2",
      "retry_count": 2,
      "timestamp": "2026-06-01T12:02:15Z"
    }
  ],
  "skipped_scenes": [],
  "validation_results": {
    "scene_count_match": true,
    "naming_valid": true,
    "timestamp_accurate": true,
    "grouping_preserved": true,
    "duration_accurate": true
  },
  "overall_status": "partial"
}
```

### Status Values

| Status | Meaning |
|---|---|
| `success` | Tất cả scenes reconstructed thành công |
| `partial` | Có scenes failed, nhưng không critical |
| `failed` | Quá nhiều failures, cần manual intervention |

---

## 8. RECONSTRUCTION RULES

### Standard Process

```
1. Load group_manifest.json
    ↓
2. Validate grouping package
    ├─ Check version
    ├─ Check total_groups
    └─ Check all group_XXXX.json exist
    ↓
3. Load reconstruction_map.json
    ↓
4. For each group (by group_order):
    ├─ Create output/000X/ folder
    ├─ For each scene_id in group:
    │   ├─ Lookup timestamp from reconstruction_map
    │   ├─ Run ffmpeg cut
    │   ├─ Validate output file
    │   └─ Update checkpoint
    └─ Log group completion
    ↓
5. Generate final_manifest.json
    ↓
6. Generate reconstruction_report.json
```

### Frame Accurate Cut Command (Default)

```bash
ffmpeg -i source.mp4 \
  -ss ${START_TIME} \
  -to ${END_TIME} \
  -c:v libx264 -preset slow -crf 18 \
  -c:a copy \
  -avoid_negative_ts make_zero \
  -y output/scene_src_XXXX.mp4
```

### Stream Copy Command (Optional)

```bash
ffmpeg -i source.mp4 \
  -ss ${START_TIME} \
  -to ${END_TIME} \
  -c:v copy -c:a copy \
  -avoid_negative_ts make_zero \
  -y output/scene_src_XXXX.mp4
```

---

## 9. FAILURE RULES

### Per-Scene Failure Handling

| Failure Type | Behavior |
|---|---|
| scene_id not in reconstruction_map | ERROR per scene, continue others |
| ffmpeg cut failed | Retry 2x, then mark failed |
| Video file not found | ERROR, STOP entire batch |
| Invalid timestamp | ERROR per scene, continue others |
| Output file corrupted | Retry 1x, then mark failed |

### Group-Level Behavior

```
If any scene in group fails:
    → Continue processing other scenes in group
    → Mark failed scene in reconstruction_report.json
    → Complete group with available scenes
    → Do NOT stop entire batch
```

### Retry Logic

```
Attempt 1: Normal cut
Attempt 2: Retry with -accurate_seek flag
Attempt 3: Retry with adjusted timestamps (±0.1s)

If all attempts fail → Mark failed, continue
```

---

## 10. RESUME RULES

### Checkpoint File

**Location:** `output/<project>/final/.checkpoint.json`

```json
{
  "checkpoint_version": "1.0",
  "project": "naruto_review_v2",
  "last_updated": "2026-06-01T12:03:00Z",
  "completed_scene_ids": [
    "scene_src_0010",
    "scene_src_0015",
    "scene_src_0021",
    "scene_src_0030"
  ],
  "failed_scene_ids": [
    "scene_src_0035"
  ],
  "pending_scene_ids": [
    "scene_src_0040",
    "scene_src_0045",
    "scene_src_0050"
  ]
}
```

### Resume Process

```
1. Check .checkpoint.json exists
    ↓
2. If exists → Load completed_scene_ids
    ↓
3. For each group:
    ├─ For each scene_id:
    │   ├─ If scene_id in completed_scene_ids → SKIP (already done)
    │   ├─ If scene_id in failed_scene_ids → SKIP (failed before)
    │   └─ Else → Process scene
    ↓
4. Update checkpoint after each scene
```

### Idempotent Operations

- Cut same scene twice → overwrite (same output)
- Checkpoint write → atomic (write to temp, then rename)
- Output folder create → idempotent (mkdir -p)

---

## 11. EXPORT QUALITY RULES

### Quality Presets

| Preset | Video | Audio | Use Case |
|---|---|---|---|
| `frame_accurate` (default) | Re-encode H.264, CRF 18, preset slow | Copy | Production recap |
| `source_copy` | Stream copy | Copy | Fast preview, same quality |
| `balanced` | Re-encode H.264, CRF 23, preset medium | Copy | Good quality, smaller file |

### Default: `frame_accurate`

**Lý do:**
- Đảm bảo frame-perfect cuts
- Không có keyframe artifacts
- Chất lượng consistent

**Stream Copy chỉ dùng khi:**
- User chọn `--quality source_copy`
- Preview mode
- Source video đã aligned với scene boundaries

### Audio Rule (LOCKED)

```
APP4 KHÔNG xử lý audio:
- Copy audio stream nguyên gốc
- Không re-encode audio
- Không thêm audio effects
- Không mix audio
- Không normalize audio
```

---

## 12. VALIDATION RULES

### Per-Scene Validation

```
After each cut:
☐ Output file exists
☐ Output file size > 0
☐ Duration matches expected (±0.5s tolerance)
☐ File readable by ffmpeg
☐ Scene ID in filename matches expected
```

### Per-Group Validation

```
After each group:
☐ All expected scenes present
☐ All scenes successfully cut (or marked failed)
☐ Group folder structure correct
☐ No extra files in folder
```

### Batch Validation (before final_manifest)

```
☐ scene_count_match: output_scenes == sum(scene_ids from all groups)
☐ naming_valid: All files match scene_src_XXXX.mp4 pattern
☐ timestamp_accurate: Output timestamps match reconstruction_map (±0.1s)
☐ grouping_preserved: scene_ids in output match group_XXXX.json
☐ duration_accurate: Output duration matches expected duration (±0.5s)
```

---

## 13. SUCCESS CRITERIA

### 5-Metric Validation

| Metric | Success Condition | Measurement |
|---|---|---|
| **Scene Count** | output_scenes == expected_scenes | Count comparison |
| **Naming** | All files = scene_src_XXXX.mp4 | Regex validation |
| **Timestamp Accuracy** | cut timestamps match reconstruction_map | ±0.1s tolerance |
| **Duration Accuracy** | output duration matches expected duration | ±0.5s tolerance |
| **Grouping** | scene_ids in final_manifest == group_XXXX.json | Cross-validation |

### Success Formula

```
IF scene_count_match AND naming_valid AND timestamp_accurate 
   AND grouping_preserved AND duration_accurate
    THEN reconstruction = SUCCESS
ELSE IF scene_count_match AND naming_valid AND grouping_preserved
    THEN reconstruction = PARTIAL (durations or timestamps slightly off)
ELSE
    THEN reconstruction = FAILED
```

### Report Status Mapping

| Result | Status in reconstruction_report.json |
|---|---|
| All 5 metrics pass | `success` |
| 3-4 metrics pass | `partial` |
| < 3 metrics pass | `failed` |

---

## 14. OWNERSHIP SUMMARY

| File | Owner | Producer | Consumer | Immutable Fields |
|---|---|---|---|---|
| `group_XXXX.json` | APP3 | APP3 | APP4 | group_id, group_order, scene_ids |
| `group_manifest.json` | APP3 | APP3 | APP4 | groups[].group_id, groups[].group_order, groups[].scene_ids |
| `source_reconstruction_map.json` | APP1 | APP1 | APP4 | scene_id, source_timestamps |
| `source_master_timeline.json` | APP1 | APP1 | APP4 | scene_id, start_time, end_time |
| `scene_src_XXXX.mp4` | APP4 | APP4 | Creator | Tên file, nội dung video |
| `final_manifest.json` | APP4 | APP4 | Creator | group_id, group_order, scene_ids |
| `reconstruction_report.json` | APP4 | APP4 | Debugger | report_version, project |

**APP4 is the final producer. Creator is the only consumer of APP4 output.**

---

## 15. FORBIDDEN ACTIONS

| Action | Reason |
|---|---|
| ❌ Gọi AI / LLM | APP4 is pure reconstructor |
| ❌ Phân tích ảnh | APP2 đã analyze |
| ❌ Phân tích metadata | APP3 đã match |
| ❌ Quyết định scene nào dùng | APP3 đã quyết định |
| ❌ Đổi scene_ids | Scene ID is immutable |
| ❌ Re-index scenes | Scene ID is source of truth |
| ❌ Đổi tên file | Phải giữ scene_src_XXXX.mp4 |
| ❌ Bỏ qua scene trong group | APP3 đã chọn |
| ❌ Reorder scene_ids | Thứ tự do APP3 quyết định |
| ❌ Xử lý audio | Audio = copy only |

---

## 16. FUTURE EXTENSIONS

### timeline_export.json (NEW)

**Location:** `output/<project>/final/timeline_export.json`

Export tổng hợp timeline cho editor workflows:

```json
{
  "timeline_version": "1.0",
  "project": "naruto_review_v2",
  "total_duration": 245.7,
  "source_video_duration": 1440.0,
  "segments": [
    {
      "timeline_index": 1,
      "scene_id": "scene_src_0010",
      "source_start": 120.5,
      "source_end": 135.7,
      "output_start": 0.0,
      "output_end": 15.2,
      "group_id": "group_0001",
      "in_markers": [],
      "out_markers": []
    }
  ]
}
```

**Fields:**
| Field | Type | Description |
|---|---|---|
| `timeline_index` | integer | Thứ tự trong timeline |
| `scene_id` | string | Scene ID |
| `source_start` | number | Timestamp trong video gốc |
| `source_end` | number | Timestamp kết thúc trong video gốc |
| `output_start` | number | Timeline position bắt đầu (0-based) |
| `output_end` | number | Timeline position kết thúc |
| `group_id` | string | Group ID |
| `in_markers` | array | Custom in markers (optional) |
| `out_markers` | array | Custom out markers (optional) |

**Use cases:**
- Import vào video editors (Premiere, DaVinci, Final Cut)
- Generate EDL / XML export
- Timeline visualization

### Other Allowed Extensions

- `final_manifest.json` → thêm `export_settings` field
- `reconstruction_report.json` → thêm `ffmpeg_command_log`
- Quality presets → thêm `low_quality` preset cho mobile

---

*End of RECONSTRUCTION_ARCHITECTURE.md*