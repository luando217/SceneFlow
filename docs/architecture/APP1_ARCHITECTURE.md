# APP1 ARCHITECTURE

**Version:** 1.0
**Status:** Locked
**Date:** 2026-06-01
**Owner:** APP1 (Data Generation Layer)

---

## PHILOSOPHY

APP1 là Data Generation Layer trong hệ thống modular.

APP1 không sử dụng AI analysis.

APP1 chỉ tạo dữ liệu nền cho APP2, APP3, APP4.

```
APP1 → APP2 → APP3 → APP4
 (data)  (AI)  (group) (reconstruct)
```

---

## LOCKED DECISIONS

### 1. Scene Detection

**Method:** PySceneDetect + ContentDetector

**Forbidden:**
- AI Scene Detection
- Vision Models
- TransNetV2

**Hardware:**
- CPU only ✓
- NVIDIA GPU ✓
- AMD GPU ✓

GPU không phải requirement. Scene detection kết quả giống nhau giữa CPU và GPU.

**Source of Truth:** PySceneDetect output

---

### 2. Frame Extraction

| Property | Value |
|----------|-------|
| Format | PNG (lossless) |
| Count | 1 keyframe / scene |
| Position | Middle Frame |
| Resolution | 480p Proxy |

**Lý do:**
- PNG giữ chất lượng text/signs
- Middle frame là representative
- 480p proxy giảm VRAM/RAM

**Forbidden:**
- JPEG / WEBP
- Start/End frame
- All frames (V1)
- Original resolution (V1)

---

### 3. Scene ID Rule

**Format:** `scene_src_XXXX`

| Property | Value |
|----------|-------|
| Prefix | `scene_src_` (bắt buộc) |
| Padding | 4 digits |
| Example | `scene_src_0001`, `scene_src_9999` |

**Immutable:** YES

APP1 là owner. APP2, APP3, APP4 chỉ được đọc.

**Forbidden:**
- rename
- re-index
- tạo ID mới
- internal temporary IDs

---

### 4. Audio Pipeline

Audio là pipeline độc lập.

```
Video → FFmpeg → WAV → Audio Analyzer → source_audio_regions.json
```

Scene Detection và Audio Analysis không phụ thuộc nhau.

---

### 5. Subtitle Pipeline

**Priority:**
1. Embedded Subtitle (MKV/MP4)
2. External Subtitle (SRT/ASS)
3. Whisper Generate

**MKV Support:** FIRST CLASS (anime-first)

**Translation:** NOT OWNED

APP1 chỉ extract hoặc generate subtitle gốc. Không dịch.

**Whisper:** Chỉ là fallback khi không có subtitle.

---

### 6. Output Structure

```
output/<project>/
├── source/                    # APP4 consumer
│   ├── source_master_timeline.json
│   ├── source_reconstruction_map.json
│   ├── source_subtitles.json
│   └── source_audio_regions.json
│
├── packages/                  # APP2/APP3 consumer
│   ├── runtime_manifest.json
│   ├── runtime_timeline.json
│   ├── runtime_subtitles.json
│   ├── runtime_audio_regions.json
│   ├── frames/
│   │   ├── scene_src_0001.png
│   │   ├── scene_src_0002.png
│   │   └── ...
│
└── .state/                    # Checkpoint
    └── app1_checkpoint.json
```

**Frame Location:** `source/frames/`

**Separation Rule:** source/ và packages/ không được trộn.

---

### 7. Module Structure

ComfyUI-style modular architecture.

```
app1/
├── scene_detector.py      # PySceneDetect wrapper
├── frame_extractor.py     # FFmpeg keyframe extraction
├── subtitle_extractor.py  # Embedded + external subtitle
├── audio_pipeline.py      # Audio extraction + analysis
├── packager.py            # Build source + runtime packages
├── checkpoint.py          # State management
└── run.py                 # Entry point
```

**Mỗi module có thể:**
- Chạy độc lập
- Debug riêng
- Test riêng

**Forbidden:** app1.py monolithic file

---

### 8. Config Format

**JSON**

Giữ thống nhất toàn hệ thống.

---

### 9. Pipeline Trigger

**V1 Support:**
- UI Button "Run APP1"
- CLI: `python -m app1 ...`
- Internal API call

**V1 Forbidden:**
- Auto Watch Folder
- Auto Trigger Background

---

### 10. Error Handling

#### Critical Fail (APP1 STOP)

- Video không mở được
- FFmpeg không đọc được video
- PySceneDetect fail toàn bộ
- Không tạo được reconstruction map
- Disk full

#### Non-Critical Fail (APP1 CONTINUE)

- Không có subtitle
- Whisper fail
- Audio analysis fail
- Một số frame export fail
- Metadata thiếu một phần

**Behavior:** Continue with warning, generate partial package.

---

### 11. Output Status

`runtime_manifest.json` phải chứa pipeline status:

```json
{
  "project": "test_5p",
  "status": "partial_success",
  "scene_detection": "success",
  "frame_extraction": "success",
  "subtitle_extraction": "failed",
  "audio_analysis": "success"
}
```

---

## GOLDEN RULE

PNG chỉ tồn tại để APP2 AI nhìn.

APP4 không cần PNG.

APP4 reconstruct hoàn toàn bằng:
- scene_id
- source_reconstruction_map.json
- source_master_timeline.json
- video gốc

---

## APP OWNERSHIP

| APP | Owner | Consumer | Output |
|-----|-------|----------|--------|
| APP1 | APP1 | APP2, APP3, APP4 | source/ + packages/ |
| APP2 | APP2 | APP3, APP4 | packages/analysis/ |
| APP3 | APP3 | APP4 | packages/grouping/ |
| APP4 | APP4 | - | final/ |

---

## FUTURE (V2+)

Có thể bổ sung:
- Whisper local auto subtitle
- Original resolution mode
- 3 frames per scene mode
- Full scene frames export

KHÔNG thay đổi:
- scene_id format
- source package structure
- runtime package structure
- ownership rules

---

**END OF APP1 ARCHITECTURE**