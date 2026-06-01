# DATA ARCHITECTURE

**Version:** Phase 4.0
**Status:** Schema Contract Defined
**Date:** 2026-06-01

---

## GOLDEN RULE — SCENE ID IS SOURCE OF TRUTH

Toàn bộ hệ thống **APP1 → APP2 → APP3 → APP4** phải giữ nguyên Scene ID.

```
scene_src_0067
↓
scene_src_0067.png      (APP1)
scene_src_0067.json     (APP1)
scene_src_0067.mp4      (APP4)
```

**FORBIDDEN:**
- rename scene
- re-index scene
- group_scene_001
- clip_001.mp4
- internal temporary IDs

Scene ID là source of truth xuyên suốt toàn bộ pipeline.

---

## PIPELINE OVERVIEW

```
[Video + Subtitle] → APP1 → [packages/ + source/]
                              ↓
                      APP2 → [packages/analysis/*.json]
                              ↓
                      APP3 → [packages/grouping/*.json]
                              ↓
                      APP4 → [final/000X/*.mp4 + group_manifest.json]
```

---

## APP1 — SceneFlow

### Input

Không có schema contract cho input. Chấp nhận file trực tiếp.

| File | Type | Description |
|---|---|---|
| video.mp4 / .mkv | Video | Video gốc |
| subtitle.srt / .ass | Subtitle | Subtitle (tùy chọn) |
| profile.json | Config | Intro/Outro profile |

---

### Output: runtime_manifest.json

**Location:** `packages/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP2, APP3, APP4 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `project_name` | string | Tên project |
| `video_path` | string | Path video gốc |
| `total_scenes` | integer | Tổng số scene |
| `scenes` | array[object] | Danh sách scene |

**Required fields per scene object:**
| Field | Type | Description |
|---|---|---|
| `scene_id` | string | ID duy nhất (vd: scene_src_0067) |
| `source_scene_id` | string | ID gốc từ source |
| `frame_path` | string | Path đến file PNG |
| `frame_count` | integer | Số frame |
| `timestamps.start` | number | Timestamp bắt đầu (seconds) |
| `timestamps.end` | number | Timestamp kết thúc (seconds) |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `scene_index` | integer | Thứ tự scene trong runtime |
| `duration` | number | Độ dài scene (seconds) |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth xuyên pipeline |
| `source_scene_id` | Mapping gốc không thay đổi |
| `timestamps.start` | Timestamp gốc |
| `timestamps.end` | Timestamp gốc |

---

### Output: runtime_timeline.json

**Location:** `packages/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP2 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `total_duration` | number | Tổng thời lượng runtime (seconds) |
| `scenes` | array[object] | Danh sách scene theo thứ tự |
| `scenes[].scene_id` | string | Scene ID |
| `scenes[].order` | integer | Thứ tự trong timeline |
| `scenes[].start_time` | number | Timestamp bắt đầu |
| `scenes[].end_time` | number | Timestamp kết thúc |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `scenes[].subtitle_segments` | array | Subtitle segments gắn với scene |
| `scenes[].audio_segments` | array | Audio segments gắn với scene |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth |
| `start_time` | Timestamp gốc |
| `end_time` | Timestamp gốc |
| `order` | Thứ tự scene không thay đổi |

---

### Output: runtime_subtitles.json

**Location:** `packages/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP2 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `segments` | array[object] | Danh sách subtitle segments |
| `segments[].scene_id` | string | Scene ID gắn với subtitle |
| `segments[].text` | string | Nội dung subtitle |
| `segments[].start_time` | number | Timestamp bắt đầu |
| `segments[].end_time` | number | Timestamp kết thúc |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `segments[].language` | string | Ngôn ngữ |
| `segments[].speaker` | string | Nhân vật nói (nếu xác định được) |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth |
| `text` | Subtitle text gốc |
| `start_time` | Timestamp gốc |
| `end_time` | Timestamp gốc |

---

### Output: runtime_audio_regions.json

**Location:** `packages/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP2 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `regions` | array[object] | Danh sách audio regions |
| `regions[].scene_id` | string | Scene ID |
| `regions[].start_time` | number | Timestamp bắt đầu |
| `regions[].end_time` | number | Timestamp kết thúc |
| `regions[].region_type` | string | Loại region (speech/silence/music) |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `regions[].volume` | number | Mức âm lượng trung bình |
| `regions[].sample_rate` | integer | Sample rate |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth |
| `start_time` | Timestamp gốc |
| `end_time` | Timestamp gốc |

---

### Output: source/frames/scene_src_XXXX.png

**Location:** `source/frames/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP2 |

**Required:**
| Field | Description |
|---|---|
| File name | `scene_src_XXXX.png` theo đúng Scene ID |
| Format | PNG |
| Resolution | Giữ nguyên tỷ lệ gốc |

**Optional:**
| Field | Description |
|---|---|
| Compression level | Có thể nén để giảm dung lượng |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` trong tên file | Source of truth |
| Timestamp mapping | Không thay đổi scene → frame mapping |

---

### Output: source_master_timeline.json

**Location:** `source/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP4 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `video_source_path` | string | Path video gốc |
| `total_duration` | number | Tổng thời lượng video gốc (seconds) |
| `scenes` | array[object] | Danh sách scene gốc |
| `scenes[].source_scene_id` | string | ID trong source gốc |
| `scenes[].scene_id` | string | Scene ID trong runtime |
| `scenes[].start_time` | number | Timestamp gốc bắt đầu |
| `scenes[].end_time` | number | Timestamp gốc kết thúc |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `scenes[].frame_rate` | number | Frame rate gốc |
| `scenes[].resolution` | string | Độ phân giải gốc |

**Immutable fields:**
| Field | Reason |
|---|---|
| `video_source_path` | Path gốc |
| `scene_id` | Source of truth |
| `start_time` | Timestamp gốc |
| `end_time` | Timestamp gốc |

---

### Output: source_reconstruction_map.json

**Location:** `source/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP4 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `entries` | array[object] | Danh sách mapping |
| `entries[].scene_id` | string | Scene ID runtime |
| `entries[].source_scene_id` | string | Scene ID gốc |
| `entries[].source_path` | string | Path video gốc |
| `entries[].source_start_time` | number | Timestamp gốc bắt đầu |
| `entries[].source_end_time` | number | Timestamp gốc kết thúc |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `entries[].transform` | object | Thông tin transform (nếu có scaling/crop) |
| `entries[].transform.scale` | object | Tỷ lệ scale |
| `entries[].transform.crop` | object | Thông tin crop |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth |
| `source_scene_id` | Mapping gốc |
| `source_start_time` | Timestamp gốc |
| `source_end_time` | Timestamp gốc |

---

### Output: source_subtitles.json

**Location:** `source/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP4 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `segments` | array[object] | Danh sách subtitle segments gốc |
| `segments[].scene_id` | string | Scene ID gắn với subtitle |
| `segments[].text` | string | Nội dung subtitle gốc |
| `segments[].start_time` | number | Timestamp gốc bắt đầu |
| `segments[].end_time` | number | Timestamp gốc kết thúc |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `segments[].language` | string | Ngôn ngữ gốc |
| `segments[].format` | string | Format gốc (srt/ass/vtt) |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth |
| `text` | Subtitle text gốc |
| `start_time` | Timestamp gốc |
| `end_time` | Timestamp gốc |

---

### Output: source_audio_regions.json

**Location:** `source/`

| Attribute | Value |
|---|---|
| **Owner** | APP1 |
| **Producer** | APP1 |
| **Consumer** | APP4 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `regions` | array[object] | Danh sách audio regions gốc |
| `regions[].scene_id` | string | Scene ID |
| `regions[].start_time` | number | Timestamp gốc bắt đầu |
| `regions[].end_time` | number | Timestamp gốc kết thúc |
| `regions[].region_type` | string | Loại region gốc (speech/silence/music) |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `regions[].source_channel` | integer | Kênh audio gốc |
| `regions[].sample_rate` | integer | Sample rate gốc |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth |
| `start_time` | Timestamp gốc |
| `end_time` | Timestamp gốc |

---

### APP1 Ownership Rules

APP1 là owner của:
- scene_id
- source_scene_id
- timestamps
- subtitle mapping
- audio mapping
- frame_path

Các APP sau **chỉ được đọc, không được sửa** bất kỳ immutable field nào.

---

## APP2 — AI Scene Analyzer

### Input

**Location:** `packages/`

| File | Description |
|---|---|
| `runtime_manifest.json` | List scene IDs, timestamps, frame paths |
| `runtime_timeline.json` | Scene timeline |
| `runtime_subtitles.json` | Subtitle data gắn với scene |
| `runtime_audio_regions.json` | Audio regions |
| `source/frames/scene_src_XXXX.png` | PNG frames |

---

### Output: scene_src_XXXX.json

**Location:** `output/<project>/packages/analysis/`

| Attribute | Value |
|---|---|
| **Owner** | APP2 |
| **Producer** | APP2 |
| **Consumer** | APP3 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `scene_id` | string | ID duy nhất (vd: scene_src_0067) |
| `source_scene_id` | string | ID gốc từ APP1 |
| `frame_path` | string | Path đến file PNG |
| `timestamps.start` | number | Timestamp bắt đầu (seconds) |
| `timestamps.end` | number | Timestamp kết thúc (seconds) |
| `prompt_version` | string | Version prompt dùng để analyze |
| `analysis_model` | string | Model AI dùng để analyze |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `character_analysis` | object | Phân tích nhân vật trong scene |
| `character_analysis.characters` | array[string] | Danh sách nhân vật |
| `character_analysis.count` | integer | Số lượng nhân vật |
| `character_analysis.description` | string | Mô tả chi tiết |
| `action_analysis` | object | Phân tích hành động |
| `action_analysis.primary_action` | string | Hành động chính |
| `action_analysis.secondary_actions` | array[string] | Hành động phụ |
| `action_analysis.movement` | string | Mô tả di chuyển |
| `emotion_analysis` | object | Phân tích cảm xúc |
| `emotion_analysis.primary_emotion` | string | Cảm xúc chính |
| `emotion_analysis.secondary_emotions` | array[string] | Cảm xúc phụ |
| `emotion_analysis.intensity` | number | Cường độ cảm xúc (0-1) |
| `environment_analysis` | object | Phân tích môi trường |
| `environment_analysis.setting` | string | Bối cảnh (indoor/outdoor/fantasy) |
| `environment_analysis.time_of_day` | string | Thời gian trong ngày |
| `environment_analysis.location` | string | Địa điểm |
| `environment_analysis.objects` | array[string] | Vật thể trong scene |
| `story_analysis` | object | Phân tích cốt truyện |
| `story_analysis.story_beat` | string | Story beat (intro/conflict/resolution) |
| `story_analysis.narrative_role` | string | Vai trò trong narrative |
| `story_analysis.scene_type` | string | Loại scene (dialogue/action/transition) |
| `semantic_analysis` | object | Phân tích ngữ nghĩa tổng hợp |
| `semantic_analysis.tags` | array[string] | Tags ngữ nghĩa |
| `semantic_analysis.summary` | string | Tóm tắt ngữ nghĩa |
| `semantic_analysis.keywords` | array[string] | Từ khóa chính |
| `subtitle_data` | object | Subtitle gắn với scene (copy từ APP1) |
| `audio_data` | object | Audio data gắn với scene (copy từ APP1) |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` | Source of truth (copy từ APP1, không thay đổi) |
| `source_scene_id` | Source of truth (copy từ APP1, không thay đổi) |
| `frame_path` | Mapping gốc (copy từ APP1, không thay đổi) |
| `timestamps.start` | Timestamp gốc (copy từ APP1, không thay đổi) |
| `timestamps.end` | Timestamp gốc (copy từ APP1, không thay đổi) |

Tất cả immutable fields là **copy từ APP1**.
APP2 **không được thay đổi** các field này, chỉ thêm analysis fields.

### APP2 Rules

- **LIVE PROMPT EDITING:** User được phép chỉnh prompt, thay block prompt
- APP2 phải hiển thị live output để user đánh giá prompt
- scene_id metadata và tất cả immutable fields **không được thay đổi**
- Mỗi scene một file riêng (`scene_src_XXXX.json`)

---

## APP3 — Grouping + Story Builder

### Input

**Source 1:** APP2 Analysis
**Location:** `packages/analysis/`
**Files:** `scene_src_XXXX.json`

**Source 2:** User Script
**Location:** `projects/<project>/`
| File | Schema Purpose | Required |
|---|---|---|
| `script.txt` | Kịch bản review (plain text) | Required (hoặc transcript) |
| `transcript.txt` | Voice transcript (plain text) | Required (hoặc script) |

**Source 3:** Prompt Profile
**Location:** `config/grouping_profile.json`
**Purpose:** Hướng dẫn cách ghép nhóm (tùy chọn)

---

### Output: group_XXXX.json

**Location:** `output/<project>/packages/grouping/`

| Attribute | Value |
|---|---|
| **Owner** | APP3 |
| **Producer** | APP3 |
| **Consumer** | APP4 |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `group_id` | string | ID duy nhất (vd: group_0001) |
| `group_order` | integer | Thứ tự group trong script (bắt đầu từ 1) |
| `script_text` | string | Nội dung script/transcript cho group này |
| `scene_ids` | array[string] | Danh sách scene_id thuộc group (theo thứ tự) |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `match_confidence` | number | Độ tin cậy match (0-1) |
| `source_type` | string | Loại input (script/transcript) |
| `script_section` | string | Section của script (nếu chia section) |
| `alternative_scene_ids` | array[string] | Scene IDs thay thế (nếu group không đủ) |
| `notes` | string | Ghi chú từ grouping process |

**Immutable fields:**
| Field | Reason |
|---|---|
| `group_id` | ID duy nhất không thay đổi sau khi tạo |
| `group_order` | Thứ tự trong script |
| `scene_ids` | Quyết định grouping không thay đổi sau khi APP3 hoàn thành |

---

### APP3 Rules

- APP3 **không cắt video**
- APP3 **chỉ quyết định** scene nào thuộc câu nào
- Input script chia theo: câu, đoạn, dấu chấm, story block
- Mỗi group_XXXX.json chứa scene_ids thuộc từng nhóm
- scene_ids trong group phải giữ thứ tự xuất hiện trong timeline

---

## APP4 — Video Reconstruction

### Input

**Source 1:** Grouping Package
**Location:** `packages/grouping/`
**Files:** `group_XXXX.json`

**Source 2:** Source Package (APP1)
**Location:** `source/`
| File | Description |
|---|---|
| `source_master_timeline.json` | Timeline gốc |
| `source_reconstruction_map.json` | scene_id → timestamp mapping |

---

### Output: scene_src_XXXX.mp4

**Location:** `output/<project>/final/000X/`

| Attribute | Value |
|---|---|
| **Owner** | APP4 |
| **Producer** | APP4 |
| **Consumer** | Creator (người dùng cuối) |

**Required conventions:**
| Field | Rule |
|---|---|
| File name | `scene_src_XXXX.mp4` (giữ nguyên Scene ID) |
| Format | MP4 (H.264) |
| Resolution | Giữ nguyên resolution gốc |
| Frame rate | Giữ nguyên frame rate gốc |
| Audio | Giữ nguyên audio gốc |

**Optional:**
| Field | Description |
|---|---|
| Codec parameters | Có thể tối ưu (CRF, preset) |
| Padding | Có thể thêm padding nếu cần |

**Immutable fields:**
| Field | Reason |
|---|---|
| `scene_id` trong tên file | Source of truth |
| Nội dung video | Chính xác scene gốc, không chỉnh sửa |

---

### Output: group_manifest.json

**Location:** `output/<project>/final/000X/`

| Attribute | Value |
|---|---|
| **Owner** | APP4 |
| **Producer** | APP4 |
| **Consumer** | Creator (người dùng cuối) |

**Required fields:**
| Field | Type | Description |
|---|---|---|
| `group_id` | string | Group ID (copy từ APP3) |
| `group_order` | integer | Thứ tự group (copy từ APP3) |
| `scene_ids` | array[string] | Danh sách scene_id (copy từ APP3) |

**Optional fields:**
| Field | Type | Description |
|---|---|---|
| `reconstruction_source` | string | Path đến source_reconstruction_map.json |
| `timestamps` | object | Timestamps tổng hợp cho group |
| `timestamps.total_duration` | number | Tổng thời lượng group |
| `timestamps.scenes` | array[object] | Timestamps từng scene trong group |
| `timestamps.scenes[].scene_id` | string | Scene ID |
| `timestamps.scenes[].start_time` | number | Timestamp bắt đầu |
| `timestamps.scenes[].end_time` | number | Timestamp kết thúc |
| `file_paths` | object | Path đến các file MP4 |
| `file_paths.clips` | array[string] | Danh sách path MP4 |
| `export_date` | string | Ngày export |
| `export_version` | string | Version export |

**Immutable fields:**
| Field | Reason |
|---|---|
| `group_id` | Copy từ APP3, không thay đổi |
| `group_order` | Copy từ APP3, không thay đổi |
| `scene_ids` | Copy từ APP3, không thay đổi |

---

### APP4 Rules

- **FORBIDDEN:** Dùng AI
- **FORBIDDEN:** Phân tích lại
- **FORBIDDEN:** Đổi tên file MP4
- APP4 **chỉ reconstruct** từ source package
- Dùng `source_reconstruction_map.json` để truy ngược: scene_id → timestamp → video gốc
- Tên thư mục 0001, 0002, ... tương ứng `group_order` từ APP3

**CORRECT:**
```
scene_src_0008.mp4  ✓
scene_src_0012.mp4  ✓
```

**FORBIDDEN:**
```
clip_001.mp4      ✗
final_clip.mp4    ✗
temp_001.mp4      ✗
```

---

## IMMUTABLE FIELD SUMMARY

| File | Immutable Fields |
|---|---|
| `runtime_manifest.json` | `scene_id`, `source_scene_id`, `timestamps.start`, `timestamps.end` |
| `runtime_timeline.json` | `scene_id`, `start_time`, `end_time`, `order` |
| `runtime_subtitles.json` | `scene_id`, `text`, `start_time`, `end_time` |
| `runtime_audio_regions.json` | `scene_id`, `start_time`, `end_time` |
| `source/frames/scene_src_XXXX.png` | Tên file (scene_id), timestamp mapping |
| `source_master_timeline.json` | `video_source_path`, `scene_id`, `start_time`, `end_time` |
| `source_reconstruction_map.json` | `scene_id`, `source_scene_id`, `source_start_time`, `source_end_time` |
| `source_subtitles.json` | `scene_id`, `text`, `start_time`, `end_time` |
| `source_audio_regions.json` | `scene_id`, `start_time`, `end_time` |
| `scene_src_XXXX.json` (analysis) | `scene_id`, `source_scene_id`, `frame_path`, `timestamps.start`, `timestamps.end` |
| `group_XXXX.json` | `group_id`, `group_order`, `scene_ids` |
| `scene_src_XXXX.mp4` | Tên file (scene_id), nội dung video |
| `group_manifest.json` | `group_id`, `group_order`, `scene_ids` |

---

## STORAGE STRUCTURE

```
output/<project>/
├── packages/              ← APP2 + APP3 data
│   ├── analysis/          ← scene_src_XXXX.json (APP2)
│   │   ├── scene_src_0001.json
│   │   ├── scene_src_0002.json
│   │   └── ...
│   └── grouping/          ← group_XXXX.json (APP3)
│       ├── group_0001.json
│       ├── group_0002.json
│       └── ...
├── source/                ← APP1 source package (APP4 đọc)
│   ├── source_master_timeline.json
│   ├── source_reconstruction_map.json
│   ├── source_subtitles.json
│   └── source_audio_regions.json
└── final/                 ← APP4 output (OUTPUT CUỐI CÙNG)
    ├── 0001/
    │   ├── group_manifest.json
    │   ├── scene_src_XXXX.mp4
    │   └── ...
    ├── 0002/
    │   └── ...
    └── 0003/
        └── ...
```

**Tất cả APP2 và APP3 data phải nằm trong `packages/`**

---

## DATA CONTRACT SUMMARY TABLE

| File | Owner | Producer | Consumer | Immutable Fields |
|---|---|---|---|---|
| `runtime_manifest.json` | APP1 | APP1 | APP2, APP3, APP4 | scene_id, source_scene_id, timestamps |
| `runtime_timeline.json` | APP1 | APP1 | APP2 | scene_id, start_time, end_time, order |
| `runtime_subtitles.json` | APP1 | APP1 | APP2 | scene_id, text, start_time, end_time |
| `runtime_audio_regions.json` | APP1 | APP1 | APP2 | scene_id, start_time, end_time |
| `source/frames/scene_src_XXXX.png` | APP1 | APP1 | APP2 | Tên file |
| `source_master_timeline.json` | APP1 | APP1 | APP4 | scene_id, start_time, end_time |
| `source_reconstruction_map.json` | APP1 | APP1 | APP4 | scene_id, source_scene_id, source_timestamps |
| `source_subtitles.json` | APP1 | APP1 | APP4 | scene_id, text, start_time, end_time |
| `source_audio_regions.json` | APP1 | APP1 | APP4 | scene_id, start_time, end_time |
| `scene_src_XXXX.json` (analysis) | APP2 | APP2 | APP3 | scene_id, source_scene_id, frame_path, timestamps |
| `group_XXXX.json` | APP3 | APP3 | APP4 | group_id, group_order, scene_ids |
| `scene_src_XXXX.mp4` | APP4 | APP4 | Creator | Tên file, nội dung video |
| `group_manifest.json` | APP4 | APP4 | Creator | group_id, group_order, scene_ids |

---

## CACHE & VERSIONING (FUTURE)

Được phép thêm sau:
- `.parquet` files
- `cache/` directories
- `embeddings/` vectors

**Nhưng phải luôn giữ `scene_id` làm khóa chính xuyên suốt pipeline.**

---

*End of DATA_ARCHITECTURE.md*