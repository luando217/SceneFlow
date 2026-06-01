# PROJECT VISION

**Version:** Phase 4.0 (Rebuild)
**Status:** Discovery Complete
**Date:** 2026-05-31

---

## 1. PURPOSE

Xây hệ thống **AI-powered semantic video-to-script matching engine** dành cho content creator.

**Core Function:**
```
Script Review → [AI Match Scenes] → Timeline + Clip List → Video Production
```

**User không cần:**
- Xem lại toàn bộ phim để tìm cảnh
- Gán scene thủ công cho từng câu script
- Cắt video bằng tay từng clip
- Review từng bước phân tích trung gian

Mục tiêu cuối: **Giảm ≥80% thời gian tìm cảnh thủ công khi dựng video review.**

---

## 2. USERS

### Người dùng cuối

**Content Creator** sản xuất video review:
- Anime Review
- Movie Review
- TV Show Review
- Long-form YouTube
- Short-form YouTube
- TikTok / Reels

### Không phải đối tượng

- Researcher
- Fan anime thuần túy
- Coder / Developer
- Studio chuyên nghiệp

Creator cần sản xuất **nhiều video nhanh hơn**. Họ viết script review, hệ thống tự động tìm cảnh phù hợp và xuất timeline/clip.

---

## 3. INPUTS

Hệ thống gồm 4 APP, mỗi APP nhận input riêng.

### APP 1 — SceneFlow (Video → Scenes)

| Input | Description |
|---|---|
| Video file | .mp4, .mkv (trực tiếp) |
| Subtitle file | .srt, .ass (tùy chọn) |
| Intro/Outro profile | Cấu hình cắt intro/outro |

Không dùng: package scene, frame images, script review, audio track riêng.

### APP 2 — AI Scene Analyzer (Scenes → Semantic Metadata)

| Input | Description |
|---|---|
| Runtime package | Export từ APP 1: frames, manifest, timeline, subtitles, audio regions |

Không đọc video gốc. Chỉ đọc dataset scene đã cắt.

### APP 3 — Grouping + Story Builder (Metadata → Story Groups)

| Input | Description |
|---|---|
| AI analysis từ APP 2 | Scene semantic metadata |
| Script review | Text kịch bản review của creator |
| Transcript / voice script | (tùy chọn) |
| Prompt profile | Hướng dẫn cách ghép nhóm |

### APP 4 — Video Reconstruction (Groups → Clips)

| Input | Description |
|---|---|
| scene_groups.json | Từ APP 3 |
| Source package | Từ APP 1: master timeline, reconstruction map, subtitles, audio regions |

---

## 4. OUTPUTS

### APP 1 Outputs
- Scene metadata (runtime)
- Scene package: PNG frames + runtime manifest
- Source package: timeline gốc + reconstruction map + subtitles + audio regions
- *Tùy chọn:* MP4 đã cắt intro/outro

### APP 2 Outputs
- AI scene analysis per scene
- Character detection
- Action detection
- Environment detection
- Scene semantic metadata

### APP 3 Outputs
- `scene_groups.json` — nhóm scene theo từng đoạn script
- Story groups
- Review timeline groups
- Script mapping (câu script → scene group)

### APP 4 Outputs (OUTPUT CUỐI CÙNG CỦA TOÀN HỆ THỐNG)
- **MP4 clips đã ghép nhóm** — video cắt sẵn theo từng đoạn script
- **MP4 clips theo câu thoại**
- **MP4 clips theo script section**
- Timeline JSON (có timestamp)
- Project data (reconstruction metadata)
- scene_groups.json

Đây là OUTPUT CUỐI CÙNG. MP4 clip là sản phẩm chính giao cho creator.

**Không cần XML/FCPXML ở phiên bản đầu.** JSON/CSV là đủ.

---

## 5. CORE FEATURES

### APP 1 — SceneFlow
- Scene preview
- Intro/Outro profile
- PNG export
- Metadata export
- Source package export
- Runtime package export
- *Không cần AI*

### APP 2 — AI Scene Analyzer
- Batch analyze scenes
- Session management (resume, retry)
- Prompt profile system
- Progress tracking
- Analysis persistence
- Structured semantic description (character, action, emotion, environment, event)

### APP 3 — Grouping + Story Builder
- Batch grouping
- Resume session
- Prompt profile
- Script ↔ scene matching (không chỉ keyword)
- Export scene_groups.json

### APP 4 — Video Reconstruction (OUTPUT CUỐI CÙNG)
- **Batch MP4 clip export** theo scene groups
- Resume export
- Retry failed export
- Session persistence
- Source timestamp reconstruction
- Timeline + metadata kèm theo

### Toàn hệ thống
- **Local-first:** không cloud, không subscription
- **Script-to-scene matching** (≥70% accuracy mục tiêu tối thiểu)
- **Prompt modularization:** Character, Event, Emotion, Relationship, Environment, Story modules

---

## 6. NON-GOALS

- ❌ Live streaming / realtime analysis
- ❌ Multi-user / team collaboration
- ❌ Cloud sync / online database
- ❌ Remote workers / distributed processing
- ❌ Video editing timeline (kiểu Premiere)
- ❌ Motion graphics / VFX
- ❌ Subtitle editor
- ❌ AI video generation / image generation
- ❌ Voice cloning
- ❌ NLE editor toàn năng

**Giới hạn:** Video → Dataset → AI Analysis → Grouping → Clip Export.

---

## 7. SUCCESS CRITERIA

### Thành công tối thiểu (MVP)
- Match đúng **≥70%** script → scene
- Giảm **≥80%** thời gian tìm cảnh thủ công
- Creator có thể sản xuất video review thực tế
- Không cần xem lại toàn bộ phim để tìm cảnh

### Thành công tốt
- Match **≥80%**
- Chỉ cần chỉnh sửa nhẹ trước khi xuất bản

### Thành công rất tốt
- Match **≥90%**
- Creator gần như chỉ review kết quả

### Đo lường
```
Script Sentence
↓
Suggested Scene Group
↓
Creator đánh giá: Đúng / Chấp nhận được / Sai
↓
Tính tỷ lệ match
```

**Không đo bằng benchmark AI. Đo bằng hiệu quả dựng video thực tế.**

---

## 8. PROJECT SCOPE

### Phạm vi dữ liệu
- Video dài: 5–30 phút (episode), 30–120 phút (movie)
- Hỗ trợ >120 phút (series movie)
- Anime là ưu tiên chính
- Hàng nghìn PNG frames / movie
- Nhiều season / nhiều package

### Platform
- **Local-first:** toàn bộ chạy local
- **OS ưu tiên:** Windows
- **OS sau:** Linux (không ưu tiên MacOS)

### Hardware target
| Component | Tối thiểu | Khuyến nghị |
|---|---|---|
| GPU | NVIDIA (CUDA) | RTX 3060+ 6GB+ |
| Fallback | AMD GPU / CPU | Chậm hơn vẫn chạy được |
| RAM | 16GB | 32GB |
| CPU | Ryzen 5+ / Intel i5+ | Ryzen 7 5700X+ |
| Storage | Không giới hạn cứng | Chấp nhận dataset lớn |

### Export formats
- **Output chính:** MP4 clips đã ghép nhóm (sẵn sàng cho dựng video)
- **Metadata kèm theo:** JSON, CSV, Parquet
- **Sau này:** XML/FCPXML có thể bổ sung

---

## 9. KNOWN CHALLENGES

| Challenge | Description |
|---|---|
| Prompt stability | Prompt A → kết quả A, Prompt B → kết quả B. Cần prompt module system |
| Semantic consistency | "chạy" / "vội vã di chuyển" / "bỏ chạy" — AI sinh khác nhau, khó grouping |
| Character consistency | Nhân vật qua nhiều góc/quần áo/flashback bị AI coi là khác nhau |
| Event recognition | "A đánh B" → "B trả đũa A" — AI thấy hai cảnh riêng biệt |
| Grouping accuracy | Scene grouping không chỉ dựa hình ảnh, phải hiểu cốt truyện |
| Script → Scene matching | Không chỉ keyword, phải hiểu ngữ cảnh và story arc |
| Long video scale | Series movie >2h, nhiều season, hàng nghìn scenes |
| Modular prompting | Cần chia Character / Event / Emotion / Relationship / Environment / Story modules riêng |

---

## 10. ARCHITECTURE OVERVIEW

```
[Video] → APP 1 SceneFlow → [Scenes + Metadata]
                            ↓
                    APP 2 AI Analyzer → [Semantic Metadata]
                            ↓
           [Script] → APP 3 Grouping → [scene_groups.json]
                            ↓
                    APP 4 Reconstructor → [MP4 Clips + Timeline] ← OUTPUT CUỐI CÙNG
```

Mỗi APP độc lập, giao tiếp qua file package.

Không có runtime dependency giữa các APP (trừ APP 4 cần source package từ APP 1).

---

*End of PROJECT_VISION.md*