# GRILL_LOCK — Architecture Decisions Locked

> Locked: 2026-06-01
> Status: All decisions final. Do not reopen unless new contradiction, missing contract, undefined ownership, or undefined failure mode is detected.

---

## GRILL 1 — APP1 AI Conundrum

**Status:** RESOLVED

**Question:** APP1 scene detection method — traditional CV (PySceneDetect) vs AI model?

**Decision:**
- APP1 sử dụng traditional shot boundary detection (PySceneDetect / histogram-based) cho scene segmentation
- AI inference chỉ được dùng ở APP2+ (semantic analysis, tagging)
- Lý do: deterministic output, reproducible, low latency, không cần GPU cho step đầu tiên
- APP1 không gọi prompt_engine, không dùng AI model

**Consumer impact:**
- `source/reconstruction_map.json` chứa scene boundaries từ CV detection
- APP2 nhận scene list từ APP1, thực hiện semantic analysis trên từng scene

---

## GRILL 2 — Scene ID Immutability vs APP3 Merge/Split/Reorder

**Status:** RESOLVED

**Question:** Khi APP3 split/merge group, group mới có cần `script_chunk_id` không?

**Decision:**
- `scene_id` immutable trong toàn pipeline
- Khi split group: group mới chỉ chứa `scene_ids`, KHÔNG tạo `script_chunk_id` mới
- Khi merge group: group merged chứa toàn bộ `scene_ids` từ các group gốc
- `script_chunk_id` chỉ tồn tại ở APP2 output, gắn với scene gốc
- APP3 group reference scenes qua `scene_ids` — đủ để APP4 reconstruct

**Consumer impact:**
- APP4 reconstruct dùng `scene_ids` để lookup từ APP2 analysis
- Không cần `script_chunk_id` ở group level

---

## GRILL 3 — reconstruction_map Ownership + Orphan Handling

**Status:** RESOLVED

**Question:** Re-run APP1 sau khi APP2/3 đã chạy → orphan detection? AI có consistency check không?

**Decision:**
- `source_reconstruction_map.json` owner = APP1 (source of truth for scene boundaries)
- APP4 là consumer duy nhất của reconstruction_map
- Nếu APP1 re-run → tạo reconstruction_map mới, KHÔNG tự động invalidate APP2/3 output
- User phải explicit confirm "re-process from APP2" nếu scenes thay đổi
- Không có automatic orphan cleanup — user decision

**Consumer impact:**
- APP4 validate APP1 output vs APP2/3 output consistency
- Nếu mismatch → warning, user decides next action

---

## GRILL 4 — packages/frames vs source/frames Contradiction

**Status:** RESOLVED

**Question:** Frame PNG files nằm ở đâu? `packages/frames/` hay `source/frames/`?

**Decision:**
- Frame files chỉ nằm ở `source/frames/`
- `packages/frames/` không tồn tại
- DATA_ARCHITECTURE.md line 211 là error — cần sửa
- Source of truth: `source/frames/scene_src_XXXX.png`

**Consumer impact:**
- Tất cả references tới `packages/frames/` trong các docs phải đổi thành `source/frames/`

---

## GRILL 5 — APP3 User Review Loop Bottleneck

**Status:** RESOLVED

**Question:** APP3 cần user review EVERY group? Có batch accept? Có auto-accept?

**Decision:**
- User review bắt buộc cho mọi group, nhưng có hỗ trợ batch operations:
  - Batch accept (select multiple groups → accept all)
  - "Auto-accept confidence > threshold" mode (configurable, default off)
  - Review queue với keyboard shortcuts để accelerate workflow
- Không có "auto-accept all" permanent mode — user phải review ít nhất 1 lần per session
- APP2 review: chỉ FAILED scenes, khác với APP3 review (every group)

**Consumer impact:**
- APP3 UI cần support batch selection + keyboard shortcuts
- APP3 checkpoint phải save partial review progress

---

## GRILL 6 — Checkpoint Corruption Recovery Edge Cases

**Status:** RESOLVED

**Question:** Backup checkpoint timing? Corruption detection method? Resume từ đâu nếu corrupt?

**Decision:**
- Backup checkpoint tự động tạo TRƯỚC mỗi checkpoint write (atomic write pattern)
- Corruption detection: JSON parse fail + checksum mismatch (double validation)
- Nếu current checkpoint corrupt + backup tồn tại → auto restore từ backup
- Nếu cả current và backup đều corrupt → prompt user:
  - Option A: Resume từ scene/group gần nhất còn output files
  - Option B: Restart APP từ đầu
  - Option C: Manual checkpoint injection
- Resume point: output files existence check → scene/group có output files = safe resume point
- APP2 scene 25 corrupt → quay lại scene 25 (không phải scene 1), dùng checkpoint backup

**Consumer impact:**
- Mỗi APP cần checkpoint directory với `.ckpt` + `.ckpt.bak` files
- Output files là fallback resume source of truth

---

## GRILL 7 — APP4 Missing Group File Handling

**Status:** LOCKED

**Question:** APP4 đọc manifest reference tới file không tồn tại → behavior?

**Decision:**
- APP4 phải validate `group_manifest.json` + TOÀN BỘ referenced group files trước khi reconstruct
- Nếu bất kỳ referenced file nào missing:
  - **Contract Violation**
  - STOP immediately
  - Không reconstruct
  - Không skip missing files
  - Không auto repair
  - User phải manually resolve trước khi retry

**Consumer impact:**
- APP4 cần pre-validation step ở đầu execution
- Error message phải list all missing files + expected paths
- Không có fallback behavior — strict contract enforcement

---

## GRILL 8 — APP4 Validation Depth

**Status:** LOCKED

**Question:** APP4 validation nên stop on first error hay collection mode?

**Decision:**
- APP4 = COLLECTION MODE (continue dù lỗi)
- `reconstruction_report.json` ghi lại tất cả errors per scene
- `overall_status` phản ánh mức độ success:
  - `success` → 0 errors
  - `partial` → some scenes failed
  - `failed` → structural failure (video not found, etc.)
- Validation checklist ở source → document contract (must pass before cut)
- Validation checklist ở output → document only (report generation)

**Consumer impact:**
- `reconstruction_report.json` là single source of truth cho APP4 health
- `final_manifest.json` chỉ contain success scenes
- Nếu scene fail → scene không xuất hiện trong final_manifest

---

## GRILL 9 — APP2 Review Threshold Scope

**Status:** LOCKED

**Question:** Review threshold in APP3 — áp dụng toàn bộ scene trong group hay từng scene riêng lẻ?

**Decision:**
- ✗ KHÔNG review từng scene riêng lẻ (APP2 level)
- ✓ Review ở group level (APP3 level)
- APP2 output chỉ cần pass/fail validation
- APP3 mới quyết định group nào cần user review (căn cứ vào match_confidence)

**Consumer impact:**
- APP2 không cần review UI
- APP2 chỉ cần: auto-generate analysis + log warnings
- Review workflow hoàn toàn thuộc APP3 ownership

---

## GRILL 10 — APP3 Grouping Mode Ambiguity

**Status:** LOCKED

**Question:** APP3 grouping mode: "review" mode có pre-chunk scenes không?

**Decision:**
- "review" = full scenes (không pre-chunk)
- Scene chunking không có trong V1
- V2 có thể có "highlight mode" (chunk scenes)
- "review" mode là default và duy nhất trong V1

**Consumer impact:**
- `grouping_mode` field trong group_XXXX.json luôn là "review" ở V1
- APP4 không cần handle chunked scene logic
- Scene chunking là future extension, không cần thiết kế bây giờ

---

## GRILL 11 — DATA_ARCHITECTURE.md frames/ Contradiction

**Status:** LOCKED

**Question:** DATA_ARCHITECTURE.md line 211 đề cập frames/ ở packages — mâu thuẫn với GRILL 4?

**Decision:**
- DATA_ARCHITECTURE.md LOCKED cần patch
- `packages/frames/` → `source/frames/`
- APP1_ARCHITECTURE.md cũng cần patch nếu có reference đến `packages/frames/`
- Frame files: `source/frames/scene_src_XXXX.png`

**Consumer impact:**
- Tất cả docs phải thống nhất: frames chỉ ở `source/frames/`
- `packages/frames/` là dead reference, cần xóa

---

## GRILL 12 — Output Path Root Ambiguity

**Status:** LOCKED

**Question:** Output base path — relative hay absolute? Root ở đâu?

**Decision:**
- Base path = project output directory (user-configurable)
- All output paths = relative to base path
- Default base path: `./output/<project_name>/`
- Source files path: `<base>/source/`
- Packages path: `<base>/packages/`
- Final path: `<base>/final/`

**Consumer impact:**
- Tất cả internal paths trong JSON files = relative
- Absolute path chỉ dùng cho source_video_path
- System có thể relocate project folder mà không break references

---

## GRILL 13 — Script Segment Granularity Ambiguity

**Status:** LOCKED

**Question:** APP3 chunking mode: "sentence" vs "paragraph" vs "semantic_block" — default là gì?

**Decision:**
- Default = `sentence` (1 câu = 1 chunk)
- `paragraph` và `semantic_block` chỉ dùng khi `config/grouping_profile.json` chỉ định
- Creator có thể override qua profile
- Nếu không có profile → dùng default `sentence`

**Consumer impact:**
- APP3 phải load profile trước khi chunking
- Default behavior predictable và consistent
- Profile override là optional, không bắt buộc

---

## GRILL 14 — Embeddings Ownership Contradiction

**Status:** LOCKED

**Question:** APP2 hay APP3 tạo embeddings? Embeddings location ở đâu?

**Decision:**
- APP2 tạo frame embeddings (model inference output)
- APP3 tạo script embeddings (script chunk → vector)
- Location:
  - Frame embeddings: `packages/analysis/scene_src_XXXX/embeddings/`
  - Script embeddings: `packages/grouping/script_chunks/embeddings/`
- Both dùng same embedding model (configurable)

**Consumer impact:**
- APP2 và APP3 đều có embeddings ownership
- APP3 matching engine cần đọc frame embeddings từ APP2 output
- APP3 tự tạo script embeddings cho matching

---

## GRILL 15 — APP2 Matching Hints Catch-22

**Status:** LOCKED

**Question:** APP2 `grouping_candidates` circular dependency?

**Decision:**
- XÓA `grouping_candidates` khỏi APP2 output
- APP2 KHÔNG sở hữu grouping logic
- APP2 chỉ xuất:
  - entities
  - actions
  - emotions
  - temporal_context
  - embeddings
- APP3 tự thực hiện matching và grouping

**Consumer impact:**
- APP2 output schema simplify
- APP3 là sole owner của grouping logic
- No circular dependency

---

## GRILL 16 — Retry Policy / Cost Control

**Status:** LOCKED

**Question:** APP2 retry không có cost control / circuit breaker?

**Decision:**
- Thêm circuit breaker config:
  - `max_consecutive_failures` = 20 (default)
  - `error_rate_threshold` = 30%
  - `window_seconds` = 60
- Khi vượt ngưỡng:
  - APP2 pause workers
  - Status = PARTIAL
  - Notify user
- Fallback chain:
  - Primary → Secondary → Tertiary
- Nếu không cấu hình fallback:
  - Retry Primary → FAILED after max attempts

**Consumer impact:**
- APP2 có cost control rõ ràng
- User có thể configure retry budget
- Cloud cost risk được mitigate

---

## GRILL 17 — total_scenes_used Ambiguity

**Status:** LOCKED

**Question:** `total_scenes_used` = sum (duplicate allowed) hay count (unique)?

**Decision:**
- Tách thành 2 fields:
  - `total_scene_references` = sum(duplicate allowed)
  - `total_unique_scenes` = count(unique scenes)
- Scene reuse vẫn tính vào references
- Unique chỉ đếm scene duy nhất

**Consumer impact:**
- APP3 output chứa cả 2 metrics
- APP4 biết chính xác số files cần tạo (unique)
- Provenance tracking đầy đủ (references = usage count)

---

## GRILL 18 — APP4 Final Output: Clips vs Single Video

**Status:** LOCKED

**Question:** APP4 output individual clips hay single merged video?

**Decision:**
- V1: APP4 chỉ reconstruct clips
- V1 KHÔNG:
  - merge video
  - crossfade
  - final recap render
  - timeline export
- Creator edit bằng NLE (Premiere, DaVinci, Final Cut)
- V2: Thêm timeline export (Premiere XML, Resolve XML)

**Consumer impact:**
- APP4 scope V1 = clip extraction only
- APP4 không cần video concatenation logic
- V2 timeline export là candidate feature

---

## GRILL 19 — Prompt Assembly Order

**Status:** LOCKED

**Question:** Prompt assembly order hardcoded hay configurable?

**Decision:**
- IMMUTABLE modules (không được move):
  - S_System (base role, behavioral rules)
  - M_Metadata (APP1 data injection)
- Các module còn lại:
  - Move, enable, disable, duplicate được phép
- `default_order.json` = profile default (không phải dead file)
- S_System và M_Metadata luôn ở đầu prompt

**Consumer impact:**
- S_System và M_Metadata không thể bị user disabled
- User có thể customize ordering của A→G modules
- `default_order.json` là live config

---

## GRILL 20 — Scene Reuse Waste

**Status:** LOCKED

**Question:** Scene reuse → duplicate MP4 files → disk waste?

**Decision:**
- V1: cho phép duplicate clip output
- KHÔNG thay đổi kiến trúc V1
- V1 optimization = đưa vào V2 candidate
- V1 KHÔNG dùng:
  - symlink
  - hardlink
  - reference files
- Lý do: V1 simplicity, avoid complexity

**Consumer impact:**
- Reused scenes = duplicate files in output
- Disk space optimization deferred to V2
- V1 architecture không phức tạp

---

## Summary Table

| GRILL | Status | Type |
|-------|--------|------|
| 1 — APP1 AI Method | RESOLVED | Implementation decision |
| 2 — Scene ID / script_chunk_id | RESOLVED | Data contract |
| 3 — Reconstruction Ownership | RESOLVED | Ownership & lifecycle |
| 4 — Frames Location | RESOLVED | Path correction |
| 5 — User Review Loop | RESOLVED | Workflow optimization |
| 6 — Checkpoint Recovery | RESOLVED | Failure handling |
| 7 — Missing Group Files | LOCKED | Contract violation |
| 8 — APP4 Validation Depth | LOCKED | Error handling mode |
| 9 — APP2 Review Scope | LOCKED | Threshold application |
| 10 — Grouping Mode | LOCKED | Review vs Highlight |
| 11 — Frames Path Contradiction | LOCKED | Path standardization |
| 12 — Output Path Root | LOCKED | Path conventions |
| 13 — Script Granularity | LOCKED | Default chunking |
| 14 — Embeddings Ownership | LOCKED | Ownership split |
| 15 — Matching Hints | LOCKED | Remove circular dep |
| 16 — Retry / Cost Control | LOCKED | Circuit breaker |
| 17 — Scene Count Metrics | LOCKED | Dual metrics |
| 18 — Final Output Scope | LOCKED | V1 clips only |
| 19 — Prompt Assembly | LOCKED | Immutable S/M |
| 20 — Reuse Waste | LOCKED | V1 accept waste |

---

## Lock Enforcement

Các decision trong file này là **IMMUTABLE** sau khi lock.

Chỉ được phép reopen nếu:
1. Phát hiện contradiction mới giữa các docs
2. Phát hiện missing contract
3. Phát hiện undefined ownership
4. Phát hiện undefined failure mode

Không được phép:
- Mở lại GRILL đã RESOLVED/LOCKED
- Thay đổi decision đã lock
- Bỏ qua constraint đã defined

---

## Next Steps

1. ✅ GRILL_LOCK.md — UPDATED (Q1-Q20 LOCKED)
2. ⬜ CONSISTENCY_AUDIT.md — Audit tất cả docs
3. ⬜ PATCH_PLAN.md — Fix contradictions
4. ⬜ APP2_ARCHITECTURE.md — Document generation

**END OF GRILL_LOCK.md**