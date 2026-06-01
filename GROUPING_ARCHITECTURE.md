# GROUPING ARCHITECTURE

**Version:** Phase 4.0
**Status:** Contract Defined
**Date:** 2026-06-01

---

## 1. PURPOSE

APP3 — Grouping + Story Builder nhận input từ APP2 (scene analysis) + script review của creator, match script → scene, output groups để APP4 reconstruct video.

**Core function:**
```
Script Review + Scene Analysis → [Match Engine] → Grouped Scenes → APP4 Handoff
```

---

## 2. GOLDEN RULES

### Rule 1 — Scene ID là source of truth xuyên suốt

```
scene_src_0067  (APP1)
    ↓
scene_src_0067.json  (APP2 analysis)
    ↓
group_XXXX.json chứa scene_src_0067  (APP3)
    ↓
scene_src_0067.mp4  (APP4)
```

**FORBIDDEN:**
- rename scene
- re-index scene
- group_scene_001
- clip_001.mp4
- internal temporary IDs

### Rule 2 — APP3 không cắt video

APP3 chỉ quyết định scene nào thuộc group nào.
APP4 reconstruct từ decision của APP3.

### Rule 3 — APP3 output là immutable contract cho APP4

Sau khi APP3 hoàn thành, group_XXXX.json không thay đổi.
APP4 chỉ đọc, không phân tích lại, không gọi AI.

---

## 3. INPUT SOURCES

### Source 1 — APP2 Analysis

**Location:** `output/<project>/packages/analysis/`
**Files:** `scene_src_XXXX.json`

APP3 đọc toàn bộ analysis files để có:
- scene_id
- character_analysis
- action_analysis
- emotion_analysis
- environment_analysis
- story_analysis
- semantic_analysis
- subtitle_data
- audio_data

### Source 2 — User Script

**Location:** `projects/<project>/`

| File | Schema Purpose | Required |
|---|---|---|
| `script.txt` | Kịch bản review (plain text) | Required (hoặc transcript) |
| `transcript.txt` | Voice transcript (plain text) | Required (hoặc script) |
| `script.md` | Markdown script | Optional |
| `script.srt` | Timed subtitle as script | Optional |

### Source 3 — Prompt Profile (tùy chọn)

**Location:** `config/grouping_profile.json`

Hướng dẫn cách ghép nhóm:
- chunking_mode: sentence | paragraph | semantic_block
- matching_strategy: hybrid
- confidence_thresholds

---

## 4. SCRIPT INPUT CONTRACT

### Unified JSON format

Tất cả input formats (.txt, .md, .transcript, .srt) được convert sang `script_parsed.json`:

```json
{
  "script_id": "script_review_001",
  "source_file": "review_script.txt",
  "source_type": "script",
  "language": "vi",
  "chunking_mode": "sentence",
  "total_chunks": 24,
  "chunks": [
    {
      "chunk_id": "chunk_001",
      "chunk_order": 1,
      "chunk_text": "Minato học phép thuật dưới sự quan sát của Sơn Thần",
      "chunk_type": "sentence",
      "characters": ["Minato", "Sơn Thần"],
      "keywords": ["học phép thuật", "quan sát"],
      "locations": []
    }
  ]
}
```

### Chunking modes

| Mode | Kích thước | Usage |
|---|---|---|
| `sentence` | 1 câu | Default, match chi tiết |
| `paragraph` | 1 đoạn (~3-8 câu) | Group dài, context rộng |
| `semantic_block` | Block tự nhận diện | Complex narrative |
| `mixed` | Tự chọn theo nội dung | User profile chỉ định |

**Default: sentence.** Paragraph / semantic_block chỉ dùng khi profile chỉ định.

---

## 5. MATCHING ENGINE

### Hybrid architecture

```
SCRIPT CHUNK
    ↓
[Match Engine]
    ├─ Keyword Match      (script keywords ∩ scene keywords)
    ├─ Metadata Match     (character + location + story purpose)
    ├─ Embedding Match    (semantic vector similarity)
    ├─ Timeline Match     (order + continuity)
    └─ Narrative Flow     (story arc progression)
    ↓
Multiple candidates → Ranked list → Select top
```

### Matching components

| Component | Input | Output |
|---|---|---|
| Keyword Match | script keywords, scene tags/keywords | overlap score (0-1) |
| Metadata Match | character names, locations, story purpose | match score (0-1) |
| Embedding Match | script chunk embedding, scene embedding | similarity score (0-1) |
| Timeline Match | scene order, timeline position | continuity score (0-1) |
| Narrative Flow | story arc, scene narrative role | flow score (0-1) |

**Không loại bỏ embedding.**
**Không chỉ dùng keyword.**
**Hybrid = tất cả components.**

---

## 6. SCORING SYSTEM

### 4-component weighted score

```
Final Score = (S × Ws) + (T × Wt) + (N × Wn) + (C × Wc)
```

### Component breakdown

#### S — Semantic Match Score (0-1)

```
semantic_score = f(
    keyword_overlap_score,      // script keywords ∩ scene keywords
    character_match_score,      // script chars ∩ scene chars
    location_match_score,       // script locations ∩ scene locations
    embedding_similarity_score  // script → scene vector similarity
)
```

#### T — Timeline Score (0-1)

```
timeline_score = f(
    order_validity,            // scene order phù hợp với script flow
    continuity_consistency     // scene liên tiếp không gây gap narrative
)
```

**Không có hard limit forward jump.**
**Backward jump chỉ được chấp nhận nếu flashback_justified.**

#### N — Narrative Flow Score (0-1) — MỚI

```
narrative_flow_score = f(
    story_arc_progression,      // scene có nằm trong arc đang xử lý
    story_beat_continuity,      // continuity của story beat
    script_section_coherence    // scene thuộc section của script
)
```

#### C — Confidence Score (0-1)

```
confidence_score = f(
    match_candidates_count,     // ≤3 scenes = bonus, >5 = penalty
    alternative_vs_primary,     // alternative scenes = 0.7×
    reuse_penalty               // scene đã dùng → decay score
)
```

### Weights (default, có thể override qua profile)

| Component | Weight |
|---|---|
| Semantic Score (S) | 0.30 |
| Timeline Score (T) | 0.25 |
| Narrative Flow Score (N) | 0.30 |
| Confidence Score (C) | 0.15 |

**Total = 1.00**

---

## 7. SCENE REUSE

### Reuse Penalty Score

Không có hard limit số lần reuse.

```
reuse_penalty = min(reuse_count × decay_factor, max_reuse_penalty)
decay_factor = 0.15
max_reuse_penalty = 0.7
scene_score_adjusted = scene_score × (1 − reuse_penalty)
```

**Ví dụ:**
- Reuse lần 1: penalty = 0.15 → score × 0.85
- Reuse lần 2: penalty = 0.30 → score × 0.70
- Reuse lần 3: penalty = 0.45 → score × 0.55
- Reuse lần 4: penalty = 0.60 → score × 0.40
- Reuse lần 5: penalty = 0.70 (max) → score × 0.30

### Khi nào reuse tự động loại bỏ

- Nếu scene_score_adjusted < 0.20, scene không còn là candidate
- Nếu match_confidence gốc đã < 0.40, reuse không được phép

---

## 8. TIMELINE RULES

### REVIEW MODE (default)

| Rule | Behavior |
|---|---|
| Scene order | Phải theo timeline gốc |
| Forward jump | Cho phép, không hard limit |
| Backward jump | Chỉ cho phép nếu flashback_justified |
| Skip scene | Cho phép (bỏ scene không match script) |
| Timeline Score | Tính tự động dựa trên order + continuity |

### HIGHLIGHT MODE (future)

Cho phép:
- Đảo thứ tự scene
- Chọn scene đẹp nhất
- Bỏ qua story continuity

**Mode mặc định = review.**
**Highlight mode là optional feature sau này.**

---

## 9. LOW CONFIDENCE RULES

### 3-tier threshold

| Threshold | Action |
|---|---|
| **≥ 0.70** | Auto-accept. Mark `match_confidence` |
| **0.40 – 0.69** | Flag for user review. `review_needed: true` |
| **< 0.40** | Leave unmatched. `match_failed: true`, skip group |

### Fallback strategy

```
Attempt 1: Re-rank with lower threshold
    ↓
Attempt 2: Use nearest timeline scene (auto-match)
    ↓
Attempt 3: Log FAILED, user must manually assign
```

---

## 10. GROUP OUTPUT CONTRACT

### group_XXXX.json

**Location:** `output/<project>/packages/grouping/`

| Field | Type | Required | Description |
|---|---|---|---|
| `group_id` | string | **IMMUTABLE** | ID duy nhất (vd: group_0001) |
| `group_order` | integer | **IMMUTABLE** | Thứ tự group trong script (bắt đầu từ 1) |
| `scene_ids` | array[string] | **IMMUTABLE** | Danh sách scene_id thuộc group (theo thứ tự timeline) |
| `script_chunk_id` | string | **IMMUTABLE** | ID của chunk từ script_parsed.json |
| `script_text` | string | **IMMUTABLE** | Nội dung script chunk gốc |
| `script_section` | string | optional | Section của script (nếu chia section) |
| `group_summary` | string | **REQUIRED** | Tóm tắt nội dung group (vd: "Minato học phép thuật dưới sự quan sát của Sơn Thần") |
| `semantic_score` | number | required | Semantic match score (0-1) |
| `timeline_score` | number | required | Timeline continuity score (0-1) |
| `narrative_flow_score` | number | required | Narrative flow consistency (0-1) |
| `confidence_score` | number | required | Confidence score (0-1) |
| `match_confidence` | number | required | Overall match confidence (0-1) |
| `embedding_similarity_score` | number | required | Embedding vector similarity (0-1) |
| `matching_method` | string | required | "hybrid_keyword_metadata_embedding_timeline_narrative" |
| `grouping_mode` | string | required | "review" hoặc "highlight" |
| `generated_at` | string | required | Timestamp tạo group |
| `reuse_count` | integer | required | Số lần scene đã được dùng (tính đến trước group này) |
| `reuse_penalty` | number | required | Reuse penalty applied (0-1) |
| `review_needed` | boolean | required | true nếu confidence 0.40-0.69 |
| `flashback_justified` | boolean | required | true nếu có backward jump hợp lệ |
| `match_failed` | boolean | required | true nếu confidence < 0.40 |
| `alternative_scene_ids` | array[string] | optional | Scene IDs thay thế |
| `skipped_scene_ids` | array[string] | optional | Scene IDs bị skip giữa group này và group trước |
| `notes` | string | optional | Ghi chú từ grouping process |

**Derived fields (không phải source of truth):**
- `scene_orders` (derived từ scene_ids position trong timeline)

**Immutable fields:**
```
group_id
group_order
scene_ids
script_chunk_id
script_text
```

**Không được thay đổi sau khi APP3 hoàn thành.**

### Example

```json
{
  "group_id": "group_0001",
  "group_order": 1,
  "scene_ids": ["scene_src_0010", "scene_src_0015", "scene_src_0021"],
  "script_chunk_id": "chunk_001",
  "script_text": "Minato học phép thuật dưới sự quan sát của Sơn Thần",
  "script_section": "Act 1 - Training",
  "group_summary": "Minato học phép thuật dưới sự quan sát của Sơn Thần",

  "semantic_score": 0.78,
  "timeline_score": 0.95,
  "narrative_flow_score": 0.88,
  "confidence_score": 0.82,
  "match_confidence": 0.85,
  "embedding_similarity_score": 0.72,

  "matching_method": "hybrid_keyword_metadata_embedding_timeline_narrative",
  "grouping_mode": "review",
  "generated_at": "2026-06-01T12:00:00Z",

  "reuse_count": 1,
  "reuse_penalty": 0.15,

  "review_needed": false,
  "flashback_justified": false,
  "match_failed": false,

  "alternative_scene_ids": ["scene_src_0025"],
  "skipped_scene_ids": ["scene_src_0011", "scene_src_0012"],

  "notes": "Match confidence high, no timeline issues"
}
```

---

## 11. group_manifest.json — ENTRY POINT CHO APP4

**Location:** `output/<project>/packages/grouping/group_manifest.json`

```json
{
  "manifest_version": "1.0",
  "project": "naruto_review_v2",
  "grouping_mode": "review",
  "total_groups": 5,
  "total_scenes_used": 18,
  "average_confidence": 0.82,
  "average_semantic_score": 0.75,
  "average_timeline_score": 0.90,
  "average_narrative_flow_score": 0.85,
  "low_confidence_count": 1,
  "failed_count": 0,
  "generated_at": "2026-06-01T12:00:00Z",
  "groups": [
    {
      "group_id": "group_0001",
      "group_order": 1,
      "scene_ids": ["scene_src_0010", "scene_src_0015", "scene_src_0021"],
      "match_confidence": 0.85
    },
    {
      "group_id": "group_0002",
      "group_order": 2,
      "scene_ids": ["scene_src_0030", "scene_src_0035"],
      "match_confidence": 0.72
    }
  ]
}
```

APP4 đọc `group_manifest.json` → biết có bao nhiêu group → reconstruct từ source package.

---

## 12. APP4 HANDOFF CONTRACT

### APP3 → APP4 handoff package

```
output/<project>/packages/grouping/
├── group_0001.json
├── group_0002.json
├── group_0003.json
└── group_manifest.json      ← ENTRY POINT
```

### APP4 FORBIDDEN actions

| Action | Reason |
|---|---|
| ❌ Gọi AI | APP3 đã quyết định grouping |
| ❌ Phân tích lại scene | APP2 đã analyze |
| ❌ Đổi scene_ids | Scene ID là source of truth |
| ❌ Reorder scene_ids trong group | Thứ tự scene do APP3 quyết định |
| ❌ Đổi tên file MP4 | Phải giữ `scene_src_XXXX.mp4` |
| ❌ Bỏ qua scene trong group | APP3 đã chọn scene phù hợp |

### APP4 CORRECT behavior

```
Đọc group_manifest.json
    ↓
Với mỗi group:
    ├─ Đọc group_XXXX.json
    ├─ Lấy scene_ids
    ├─ Tra source_reconstruction_map.json → timestamp
    ├─ Cắt video gốc → scene_src_XXXX.mp4
    └─ Export vào final/XXXX/
    ↓
Tạo group_manifest.json trong final/XXXX/
```

---

## 13. OUTPUT STORAGE STRUCTURE

```
output/<project>/
├── packages/
│   ├── analysis/              ← APP2
│   │   ├── scene_src_0001.json
│   │   ├── scene_src_0002.json
│   │   └── ...
│   └── grouping/              ← APP3
│       ├── group_0001.json
│       ├── group_0002.json
│       ├── group_0003.json
│       └── group_manifest.json  ← ENTRY POINT
├── source/                    ← APP1 (APP4 đọc)
│   ├── source_master_timeline.json
│   ├── source_reconstruction_map.json
│   ├── source_subtitles.json
│   └── source_audio_regions.json
└── final/                     ← APP4 output
    ├── 0001/
    │   ├── group_manifest.json
    │   ├── scene_src_XXXX.mp4
    │   └── ...
    ├── 0002/
    │   └── ...
    └── ...
```

---

## 14. MATCHING METRICS VALIDATION

### Per-group validation checklist

```
☐ scene_ids: non-empty, scene_id valid format (scene_src_XXXX)
☐ scene_ids: tất cả đều tồn tại trong APP2 analysis
☐ script_text: non-empty, max 1000 chars
☐ group_summary: non-empty
☐ match_confidence: 0-1 range
☐ semantic_score: 0-1 range
☐ timeline_score: 0-1 range
☐ narrative_flow_score: 0-1 range
☐ confidence_score: 0-1 range
☐ embedding_similarity_score: 0-1 range
☐ No backward jump without flashback_justified = true
☐ No skipped scenes without review_needed flag (nếu confidence < 0.70)
☐ matching_method ≠ empty
☐ grouping_mode ∈ ["review", "highlight"]
```

### Batch validation (group_manifest.json)

```
☐ total_groups = length of groups array
☐ total_scenes_used = tổng scene_ids từ tất cả groups
☐ average_confidence = mean match_confidence
☐ low_confidence_count = số group có match_confidence < 0.70
☐ failed_count = số group có match_confidence < 0.40
```

---

## 15. MATCHING METRICS SUMMARY

| Metric | Formula / Source | Purpose |
|---|---|---|
| `keyword_overlap_score` | overlap(script_keywords, scene_keywords) | Keyword match quality |
| `character_match_score` | match(script_chars, scene_chars) | Character match accuracy |
| `location_match_score` | match(script_locations, scene_locations) | Location match |
| `embedding_similarity_score` | cosine_sim(script_embedding, scene_embedding) | Semantic vector match |
| `semantic_score` | aggregate(keyword + character + location + embedding) | Overall semantic quality |
| `timeline_score` | f(order_validity, continuity_consistency) | Order validity |
| `narrative_flow_score` | f(story_arc, story_beat, script_section) | Story arc consistency |
| `confidence_score` | f(candidate_count, alternatives, reuse) | Match reliability |
| `match_confidence` | weighted_sum(semantic, timeline, narrative, confidence) | Overall reliability |
| `reuse_count` | counter(scene_id across all groups) | Scene usage tracking |
| `reuse_penalty` | min(reuse_count × 0.15, 0.7) | Score decay for overused scenes |

---

## 16. OWNERSHIP SUMMARY

| File | Owner | Producer | Consumer | Immutable Fields |
|---|---|---|---|---|
| `group_XXXX.json` | APP3 | APP3 | APP4 | group_id, group_order, scene_ids, script_chunk_id, script_text |
| `group_manifest.json` | APP3 | APP3 | APP4 | groups[].group_id, groups[].group_order, groups[].scene_ids |

**APP3 là owner duy nhất của grouping decision.**
**APP4 chỉ reconstruct, không phân tích lại.**

---

## 17. FUTURE EXTENSIONS

Được phép thêm sau:
- `scene_orders` (derived field, không immutable)
- `scene_weight` cho từng scene trong group
- `narrative_graph.json` (graph quan hệ giữa groups)
- `timeline_position` cho từng group trong script flow

**Nhưng phải luôn giữ:**
- `group_id` làm khóa chính
- `scene_id` làm source of truth
- Output contract không thay đổi

---

*End of GROUPING_ARCHITECTURE.md*