# PROMPT_ARCHITECTURE

**Version:** Phase 4.1
**Scope:** APP2 — AI Scene Analyzer
**Status:** Architecture Contract Defined
**Date:** 2026-06-01

---

## CORE RESPONSIBILITY

```
PNG Frame Image
+
Subtitle Text
+
Audio Metadata
      ↓
Prompt Builder (Modular Assembly)
      ↓
LLM Inference
      ↓
scene_src_XXXX.json (Analysis Output)
      ↓
APP3 Scene Grouping ← Metadata for script matching
```

**Mục tiêu APP2:** Sinh metadata đủ mạnh để APP3 match script chính xác.

APP2 không chỉ mô tả ảnh. APP2 sinh searchable, matchable metadata.

---

## 1. PROMPT MODULE SYSTEM

### 1.1 Module Architecture

Prompt chia module độc lập. Mỗi module có thể enable/disable, edit riêng, version riêng.

```
┌─────────────────────────────────────────────┐
│  G_OutputSchema     │ Output contract        │
├─────────────────────┼───────────────────────┤
│  F_Semantic         │ Tags, keywords, hints  │
├─────────────────────┼───────────────────────┤
│  E_Story            │ Beat, purpose, type    │
├─────────────────────┼───────────────────────┤
│  D_Environment      │ Location, objects     │
├─────────────────────┼───────────────────────┤
│  C_Emotion          │ Emotion, intensity    │
├─────────────────────┼───────────────────────┤
│  B_Action           │ Actions, movement     │
├─────────────────────┼───────────────────────┤
│  A_Character        │ Characters, names     │
├─────────────────────┼───────────────────────┤
│  M_Metadata         │ Subtitle, audio, time │
├─────────────────────┼───────────────────────┤
│  S_System           │ Base role, rules      │
└─────────────────────────────────────────────┘
```

### 1.2 Module Definitions

| Module | ID | Purpose |
|---|---|---|
| **System** | S_System | Base role, boundaries |
| **Metadata** | M_Metadata | Scene context (PROTECTED) |
| **Character** | A_Character | Character extraction |
| **Action** | B_Action | Action extraction |
| **Emotion** | C_Emotion | Emotion extraction |
| **Environment** | D_Environment | Environment extraction |
| **Story** | E_Story | Story beat, purpose |
| **Semantic** | F_Semantic | Tags, keywords, hints |
| **Output Schema** | G_OutputSchema | JSON structure |

### 1.3 Module Properties

Each module has:

| Property | Description |
|---|---|
| `module_id` | Unique identifier (A_Character, etc.) |
| `enabled` | boolean — include in assembly |
| `version` | v{major}.{minor} |
| `editable` | User can modify |
| `content` | Prompt text |
| `output_field` | Which JSON field this generates |

### 1.4 Module File Organization

```
prompts_app2/
├── S_system/
│   ├── base_role.txt
│   └── behavioral_rules.txt
├── M_metadata/
│   ├── subtitle_injection.txt
│   ├── audio_injection.txt
│   └── timestamp_injection.txt
├── A_character/
│   ├── instructions.txt
│   ├── ontology.txt
│   └── version.json
├── B_action/
│   ├── instructions.txt
│   ├── vocabulary.txt
│   └── version.json
├── C_emotion/
│   ├── instructions.txt
│   ├── mapping.txt
│   └── version.json
├── D_environment/
│   ├── instructions.txt
│   ├── descriptors.txt
│   └── version.json
├── E_story/
│   ├── instructions.txt
│   ├── beats.txt
│   └── version.json
├── F_semantic/
│   ├── instructions.txt
│   ├── keywords.txt
│   └── version.json
├── G_output_schema/
│   └── schema.json
└── assembly/
    └── default_order.json
```

### 1.5 Prompt Builder

```
Input: Selected modules + scene data
        ↓
Load enabled modules
        ↓
Inject M_Metadata (subtitles, audio, timestamps)
        ↓
Assemble in order: S → M → A → B → C → D → E → F → G
        ↓
Output: Complete prompt string
```

---

## 2. ANALYSIS JSON SCHEMA

### 2.1 Immutable Fields (From APP1)

**THESE FIELDS ARE PROTECTED. APP2 MUST NOT MODIFY.**

| Field | Type | Source | Reason |
|---|---|---|---|
| `scene_id` | string | APP1 | Source of truth |
| `source_scene_id` | string | APP1 | Mapping gốc |
| `frame_path` | string | APP1 | Path từ APP1 |
| `timestamps.start` | number | APP1 | Timestamp gốc |
| `timestamps.end` | number | APP1 | Timestamp gốc |

### 2.2 APP2 Provenance Fields

| Field | Type | Description |
|---|---|---|
| `prompt_version` | string | Version của prompt dùng |
| `analysis_model` | string | Model used for inference |
| `generated_at` | string | ISO timestamp |

### 2.3 Production Required Fields (APP3 Matching)

**FIELDS BẮT BUỘC cho APP3 grouping:**

| Field | Type | Required | APP3 Usage |
|---|---|---|---|
| `scene_summary` | string | **PRODUCTION REQUIRED** | Match script sentences |
| `visual_keywords` | array[string] | **PRODUCTION REQUIRED** | Visual similarity matching |
| `dialogue_keywords` | array[string] | **PRODUCTION REQUIRED** | Subtitle matching |
| `character_names` | array[string] | **PRODUCTION REQUIRED** | Character-based grouping |
| `location_names` | array[string] | **PRODUCTION REQUIRED** | Location-based grouping |
| `important_objects` | array[string] | **PRODUCTION REQUIRED** | Object-based matching |
| `story_purpose` | string | **PRODUCTION REQUIRED** | Narrative purpose matching |
| `searchable_tags` | array[string] | **PRODUCTION REQUIRED** | Full-text search |
| `matching_hints` | object | **PRODUCTION REQUIRED** | APP3 grouping hints (confidence + temporal_context only) |

### 2.4 Extended Analysis Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `character_analysis.count` | integer | Recommended | Số nhân vật |
| `character_analysis.positions` | array[object] | Optional | Vị trí nhân vật |
| `action_analysis.primary_action` | string | Recommended | Hành động chính |
| `action_analysis.secondary_actions` | array[string] | Optional | Hành động phụ |
| `emotion_analysis.primary_emotion` | string | Recommended | Cảm xúc chính |
| `emotion_analysis.intensity` | number | Recommended | Cường độ 0-1 |
| `environment_analysis.setting` | string | Recommended | Bối cảnh |
| `environment_analysis.objects` | array[string] | Recommended | Vật thể trong scene |
| `story_analysis.story_beat` | string | Recommended | Story beat |
| `story_analysis.scene_type` | string | Recommended | Loại scene |

### 2.5 Complete Schema Contract

```json
{
  "// IMMUTABLE FROM APP1": "--- DO NOT MODIFY ---",
  "scene_id": "string (PROTECTED)",
  "source_scene_id": "string (PROTECTED)",
  "frame_path": "string (PROTECTED)",
  "timestamps": {
    "start": "number (PROTECTED)",
    "end": "number (PROTECTED)"
  },

  "// APP2 PROVENANCE": "--- VERSION TRACKING ---",
  "prompt_version": "string",
  "analysis_model": "string",
  "generated_at": "string (ISO timestamp)",

  "// APP3 MATCHING (PRODUCTION REQUIRED)": "--- FOR SCRIPT MATCHING ---",
  "scene_summary": "string (max 500 chars)",
  "visual_keywords": "array[string] (max 20 items)",
  "dialogue_keywords": "array[string] (max 20 items)",
  "character_names": "array[string] (max 10 items)",
  "location_names": "array[string] (max 5 items)",
  "important_objects": "array[string] (max 15 items)",
  "story_purpose": "string (max 200 chars)",
  "searchable_tags": "array[string] (max 30 items)",
  "matching_hints": {
    "confidence": "number 0-1",
    "temporal_context": "string (before/after/isolated)"
  },

  "// EXTENDED ANALYSIS": "--- OPTIONAL FOR ADVANCED USE ---",
  "character_analysis": {
    "characters": "array[string]",
    "count": "integer",
    "description": "string"
  },
  "action_analysis": {
    "primary_action": "string",
    "secondary_actions": "array[string]"
  },
  "emotion_analysis": {
    "primary_emotion": "string",
    "secondary_emotions": "array[string]",
    "intensity": "number 0-1"
  },
  "environment_analysis": {
    "setting": "string",
    "location": "string",
    "objects": "array[string]"
  },
  "story_analysis": {
    "story_beat": "string",
    "scene_type": "string",
    "narrative_role": "string"
  }
}
```

---

## 3. EDITABLE PROMPT LAYERS

### 3.1 User Can Edit

| Module | Editable | What to Edit |
|---|---|---|
| S_System | ✗ No | System contract |
| M_Metadata | ✗ No | APP1 data injection |
| A_Character | ✓ Yes | Character extraction logic |
| B_Action | ✓ Yes | Action vocabulary |
| C_Emotion | ✓ Yes | Emotion mapping |
| D_Environment | ✓ Yes | Environment descriptors |
| E_Story | ✓ Yes | Story beat definitions |
| F_Semantic | ✓ Yes | Keywords, tags |
| G_OutputSchema | ✓ Yes | JSON structure |

### 3.2 User Cannot Edit (PROTECTED)

| Module | Protected Because |
|---|---|
| S_System | Model contract, system stability |
| M_Metadata | Data contract from APP1 |

### 3.3 Metadata Layer Protection

**M_Metadata is PROTECTED. User cannot modify:**

- Scene ID injection
- Timestamp injection
- Subtitle mapping
- Audio metadata injection
- Frame path reference

These are read-only contracts from APP1.

### 3.4 Edit Mechanism

```
User edits module content
        ↓
Module version increments (v1.0 → v1.1)
        ↓
Live test on sample scene
        ↓
Validation passes → Approval
        ↓
Use for production
        ↓
Log change with timestamp + author
```

---

## 4. LIVE TESTING WORKFLOW

### 4.1 Single Scene Test

```
User selects scene
        ↓
Load scene data: PNG + Subtitle + Audio + Timestamps
        ↓
Assemble prompt (enabled modules in order)
        ↓
Send to LLM
        ↓
Parse JSON output
        ↓
Validate against schema
        ↓
Display: Input → Assembled Prompt → Raw Response → Parsed JSON
```

### 4.2 Batch Test

```
User selects scenes (1-10)
        ↓
Assemble prompts for each (respect module settings)
        ↓
Sequential or parallel LLM calls
        ↓
Validate each output
        ↓
Show pass/fail per scene
        ↓
Export results
```

### 4.3 Live Preview Components

| Component | Display | Always Visible |
|---|---|---|
| PNG frame | Scene image | ✓ Yes |
| Scene ID | From APP1 (protected) | ✓ Yes |
| Timestamps | From APP1 (protected) | ✓ Yes |
| Assembled prompt | Full prompt with syntax highlight | ✓ Yes |
| Raw LLM response | Original output | ✓ Yes |
| Parsed JSON | Formatted, color-coded | ✓ Yes |
| Validation result | Pass/Fail + errors | ✓ Yes |
| Module toggle | Enable/disable modules | ✓ Yes |

### 4.4 Test Scene Selection

- Random scene từ dataset
- User-specified scene
- Edge case scenes (complex scenes, low confidence)

---

## 5. MODEL AGNOSTIC STRATEGY

### 5.1 Supported Providers

APP2 hỗ trợ **bất kỳ model nào** hỗ trợ image + text input.

| Provider | Type | API Style |
|---|---|---|
| **OpenAI Compatible API** | Cloud | REST, openai-python |
| **Ollama** | Local | REST, llama.cpp |
| **OpenRouter** | Gateway | OpenAI-compatible |
| **Local Vision Models** | Local | Custom endpoints |
| **Cloud Vision Models** | Cloud | Multi-provider |

### 5.2 Model Adapter Pattern

```
┌─────────────────────────────────────┐
│  Prompt Modules (Unified Format)   │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│  Model Adapter Layer                │
│  - Provider detection               │
│  - Format conversion                │
│  - Payload normalization            │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│  Provider-specific API              │
│  - OpenAI / Ollama / OpenRouter     │
│  - Local endpoints                  │
│  - Cloud providers                  │
└─────────────────────────────────────┘
```

### 5.3 Adapter Responsibilities

| Provider | Adaptation |
|---|---|
| All | Image format normalization |
| All | Temperature settings |
| All | Max token handling |
| OpenAI | JSON mode |
| Ollama | Stream handling |
| OpenRouter | Provider routing |
| Claude-style | XML tag wrapping |

### 5.4 Model Configuration

```yaml
model:
  provider: "openai" | "ollama" | "openrouter" | "custom"
  endpoint: "https://api.openai.com/..." # or localhost:11434
  model_name: "gpt-4o" | "llava" | "qwen-vl" | "custom"
  api_key: "${ENV_VAR}" # or none for local
  vision_enabled: true
  max_tokens: 4096
  temperature: 0.1
```

### 5.5 Fallback Strategy

```
Primary model fails
        ↓
Retry same model (1x, wait 1s)
        ↓
Try fallback model (if configured)
        ↓
Try fallback provider (if configured)
        ↓
Mark FAILED, log error for review
```

### 5.6 Model Requirements

Minimum model requirements:

| Requirement | Minimum |
|---|---|
| Vision | Must accept image input |
| Text | Must accept text prompt |
| JSON | Must support structured output |
| Context | Must handle 1000+ tokens |

**No model is hardcoded. APP2 adapts to whatever is available.**

---

## 6. METADATA INJECTION RULES

### 6.1 Metadata Layer Structure (PROTECTED)

```
┌─────────────────────────────────────┐
│  M_METADATA (PROTECTED)             │
├─────────────────────────────────────┤
│  scene_id: scene_src_0067         │
│  timestamps: 123.45 - 126.78        │
│  duration: 3.33s                    │
│  frame_path: source/frames/.../0067.png │
├─────────────────────────────────────┤
│  SUBTITLE:                          │
│  "akura wa sekai wo kaeru koto ga│
│   dekinai..."                       │
├─────────────────────────────────────┤
│  AUDIO:                             │
│  type: speech                       │
│  has_dialogue: true                 │
│  has_music: false                   │
└─────────────────────────────────────┘
```

### 6.2 Subtitle Injection Rules

| Condition | Action |
|---|---|
| Subtitle available | Inject full text |
| No subtitle | Inject "No subtitle available" |
| Multiple segments | Concatenate with " \| " |
| Exceeds 500 chars | Truncate to 500 chars |

### 6.3 Audio Metadata Injection

| Field | Value Source |
|---|---|
| `audio_type` | runtime_audio_regions.json |
| `has_dialogue` | Boolean from APP1 |
| `has_background_music` | Boolean from APP1 |
| `audio_intensity` | Number 0-1 from APP1 |

### 6.4 Timestamp Injection

| Field | Format | Example |
|---|---|---|
| `scene_start` | seconds | 123.45 |
| `scene_end` | seconds | 126.78 |
| `scene_duration` | seconds | 3.33 |
| `frame_index` | integer | 67 |

---

## 7. ANALYSIS SEARCHABILITY

### 7.1 Search Index Fields (For APP3)

APP2 output optimized for **searchable metadata**.

| Field | APP3 Search Use |
|---|---|
| `character_names` | Match character mentions in script |
| `visual_keywords` | Visual similarity matching |
| `dialogue_keywords` | Subtitle keyword matching |
| `location_names` | Location-based grouping |
| `important_objects` | Object context matching |
| `story_purpose` | Narrative purpose filtering |
| `searchable_tags` | Full-text search index |
| `matching_hints` | Grouping context (confidence + temporal) |

### 7.2 Search Optimization Rules

| Field | Max Items | Max Chars |
|---|---|---|
| `character_names` | 10 | 50 per name |
| `visual_keywords` | 20 | 30 per keyword |
| `dialogue_keywords` | 20 | 30 per keyword |
| `location_names` | 5 | 50 per location |
| `important_objects` | 15 | 30 per object |
| `searchable_tags` | 30 | 20 per tag |

### 7.3 Matching Hints Structure

```json
{
  "matching_hints": {
    "confidence": 0.85,
    "temporal_context": "continues_from_previous",
    "script_alignment_hint": "dialogue_continuation"
  }
}
```

### 7.4 Index Readiness

```
Scene Analysis
        ↓
Extract searchable fields
        ↓
Normalize text (lowercase, trim)
        ↓
Validate against schema
        ↓
Store in scene_src_XXXX.json
        ↓
Ready for APP3 grouping
```

---

## 8. OUTPUT VALIDATION RULES

### 8.1 Validation Levels

| Level | Check | Action on Fail |
|---|---|---|
| **PRODUCTION** | All PRODUCTION REQUIRED fields + schema | Reject, retry |
| **WARN** | All recommended fields present | Accept, log warning |
| **LENIENT** | Core fields + scene_id | Accept, log warning |

### 8.2 Production Validation Checklist

```
☐ scene_id matches APP1 input (IMMUATBLE)
☐ source_scene_id matches APP1 input (IMMUTABLE)
☐ timestamps match APP1 input (IMMUTABLE)
☐ scene_summary: non-empty, max 500 chars
☐ visual_keywords: 1-20 items, max 30 chars each
☐ dialogue_keywords: 0-20 items, max 30 chars each
☐ character_names: 0-10 items, max 50 chars each
☐ location_names: 0-5 items, max 50 chars each
☐ important_objects: 0-15 items, max 30 chars each
☐ story_purpose: non-empty, max 200 chars
☐ searchable_tags: 1-30 items, max 20 chars each
☐ matching_hints: valid structure
☐ No hallucinated character names (check ontology)
```

### 8.3 Field Validation Rules

| Field Type | Rule |
|---|---|
| string | Non-empty (for required), max length |
| array | Min/max items, each item max length |
| number | Within range (intensity 0-1) |
| object | Required keys present |

### 8.4 Validation Output

```json
{
  "valid": true,
  "level": "PRODUCTION",
  "warnings": [],
  "errors": [],
  "field_count": {
    "character_names": 3,
    "visual_keywords": 8,
    "searchable_tags": 12
  }
}
```

---

## 9. FAILURE HANDLING RULES

### 9.1 Failure Types

| Type | Cause | Action |
|---|---|---|
| `API_ERROR` | Network/timeout | Retry, fallback provider |
| `PARSE_ERROR` | Invalid JSON | Retry with same model |
| `VALIDATION_ERROR` | Schema mismatch | Retry with same prompt |
| `TIMEOUT` | Model too slow | Retry with faster model |
| `PARTIAL` | Some fields missing | Accept with warnings |
| `PROVIDER_ERROR` | Provider down | Try fallback provider |

### 9.2 Retry Policy

```
Attempt 1: Primary model, same prompt
        ↓
Attempt 2: Same model, wait 1s
        ↓
Attempt 3: Same model, wait 2s
        ↓
Attempt 4: Fallback model/provider
        ↓
Attempt 5: Fallback, wait 2s
        ↓
Mark FAILED, log for manual review
```

### 9.3 Partial Failure Handling

| Missing Fields | Action |
|---|---|
| 1-2 production fields | Accept, fill with null, log warning |
| 3+ production fields | Reject, retry |
| Schema invalid | Reject, retry with adjusted prompt |

### 9.4 Failure Logging

```json
{
  "scene_id": "scene_src_0067",
  "attempt": 3,
  "error_type": "VALIDATION_ERROR",
  "error_fields": ["scene_summary", "story_purpose"],
  "error_message": "Missing production required fields",
  "raw_output": "...",
  "timestamp": "2026-06-01T12:00:00Z",
  "provider": "ollama",
  "model": "llava"
}
```

---

## 10. PROMPT VERSIONING STRATEGY

### 10.1 Version Format

```
v{major}.{minor}
   │       └── Incremented on module content edit
   └────────── Incremented on breaking schema changes
```

### 10.2 Module-Level Versioning

Each module has independent version:

```
A_character/v1.0  →  A_character/v1.1 (user edited instructions)
B_action/v1.0      →  B_action/v1.0 (unchanged)
F_semantic/v2.3    →  F_semantic/v2.4 (user added tags)
```

Overall prompt version = highest module version:

```
prompt_version: "v2.4"  (from F_semantic/v2.4)
```

### 10.3 Version Tracking

| Version | Date | Module | Change |
|---|---|---|---|
| v1.0 | 2026-06-01 | System | Initial |
| v1.1 | 2026-06-01 | A_Character | User edited ontology |
| v2.0 | 2026-06-01 | G_OutputSchema | Added production fields |
| v2.4 | 2026-06-01 | F_Semantic | Added searchable tags |

### 10.4 Version Compatibility

| Change | Bump | Backward Compatible |
|---|---|---|
| Add optional field | minor | ✓ Yes |
| Add production field | minor | ✓ Yes |
| Add required field | major | ✗ No |
| Remove field | major | ✗ No |
| Rename field | major | ✗ No |
| Change field type | major | ✗ No |

### 10.5 Version in Output

```json
{
  "prompt_version": "v2.4",
  "module_versions": {
    "A_character": "v1.1",
    "B_action": "v1.0",
    "C_emotion": "v1.0",
    "D_environment": "v1.0",
    "E_story": "v1.0",
    "F_semantic": "v2.4",
    "G_output_schema": "v2.0"
  },
  "analysis_model": "ollama/llava",
  "generated_at": "2026-06-01T12:00:00Z"
}
```

---

## 11. IMMUTABLE DATA CONTRACT

### 11.1 PROTECTED FIELDS

**ABSOLUTE RULE: APP2 MUST NOT MODIFY THESE FIELDS.**

| Field | Source | Protection Level |
|---|---|---|
| `scene_id` | APP1 | **STRICTLY PROTECTED** |
| `source_scene_id` | APP1 | **STRICTLY PROTECTED** |
| `frame_path` | APP1 | **STRICTLY PROTECTED** |
| `timestamps.start` | APP1 | **STRICTLY PROTECTED** |
| `timestamps.end` | APP1 | **STRICTLY PROTECTED** |

### 11.2 APP2 Data Contract

APP2 MUST:

- Copy immutable fields from APP1
- Never modify immutable field values
- Never derive new IDs from immutable fields
- Preserve timestamp accuracy to milliseconds

APP2 MUST NOT:

- Rename scene IDs
- Re-index scenes
- Create internal IDs
- Generate proxy IDs
- Modify timestamp calculations

### 11.3 Violation Detection

```python
# Pseudocode for contract enforcement
def validate_analysis_json(analysis_json, runtime_manifest):
    errors = []

    # Check immutable fields match APP1
    if analysis_json['scene_id'] != runtime_manifest['scene_id']:
        errors.append("scene_id mismatch - CONTRACT VIOLATION")

    if analysis_json['timestamps']['start'] != runtime_manifest['timestamps']['start']:
        errors.append("timestamps.start mismatch - CONTRACT VIOLATION")

    return errors
```

---

## 12. OUTPUT LOCATION

### 12.1 Directory Structure

```
output/<project>/
└── packages/
    └── analysis/
        ├── scene_src_0001.json
        ├── scene_src_0002.json
        └── ...
```

### 12.2 File Naming Convention

**CORRECT:**
```
scene_src_0001.json  ✓
scene_src_0067.json  ✓
```

**FORBIDDEN:**
```
analysis_all.json          ✗
single_mega_file.json      ✗
database_only_storage      ✗
clip_001.json             ✗
temp_scene.json           ✗
```

### 12.3 One Scene Per File

- Each `scene_src_XXXX.json` contains analysis for exactly ONE scene
- Filename matches `scene_id` field in JSON
- No multi-scene aggregation files
- No database-only storage (must have file)

### 12.4 File Content Contract

Each file contains:

```json
{
  "scene_id": "scene_src_0067",
  "// ... all other fields",
  "// Provenance",
  "prompt_version": "v2.4",
  "analysis_model": "ollama/llava",
  "generated_at": "2026-06-01T12:00:00Z"
}
```

---

## 13. FUTURE EXTENSIONS

### 13.1 Allowed Extensions

After production schema is stable, these can be added:

| Extension | Format | Purpose |
|---|---|---|
| `embeddings/` | `.npy` / `.bin` | Vector embeddings |
| `cache/` | `.json` | LLM response cache |
| `metadata.parquet` | `.parquet` | Analytics |
| `index.json` | `.json` | Search index |

### 13.2 Extension Rules

**RULE: `scene_id` is always primary key.**

```
scene_src_0067/
├── scene_src_0067.json        ← Primary analysis
├── embeddings/
│   └── scene_src_0067.npy    ← Optional
├── cache/
│   └── scene_src_0067.json   ← Optional
└── metadata/
    └── scene_src_0067.json   ← Optional
```

### 13.3 Schema Evolution

When adding extensions:

1. Never modify existing production fields
2. Add new fields as optional
3. Maintain `scene_id` as required
4. Document extension in version notes

---

## CONTRACT SUMMARY

| Rule | Contract |
|---|---|
| Prompt Structure | 9-module independent system |
| Module Editing | A/B/C/D/E/F/G editable; S/M protected |
| Model Strategy | Model agnostic (any vision+text model) |
| Production Fields | 9 required for APP3 matching |
| Searchability | Optimized for APP3 grouping |
| Validation | PRODUCTION/WARN/LENIENT levels |
| Failure | Retry policy, partial handling |
| Versioning | Module-level, prompt = highest |
| Immutable Contract | scene_id, source_scene_id, timestamps |
| Output Location | `packages/analysis/scene_src_XXXX.json` |
| Extensions | Allowed, scene_id always primary key |

---

*End of PROMPT_ARCHITECTURE.md (v4.1)*