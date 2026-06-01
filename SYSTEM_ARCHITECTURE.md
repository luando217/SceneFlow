# SYSTEM ARCHITECTURE

**Version:** Phase 3.3
**Status:** Structure Defined
**Date:** 2026-06-01

---

## 1. SYSTEM STRUCTURE

### Top-Level Layout

```
SceneFlow/
├── prompts/                          ← ASSET LAYER (no ownership)
│   ├── app2/
│   │   ├── v1/
│   │   │   ├── 001_Luat.txt
│   │   │   ├── 002_NhanVat.txt
│   │   │   ├── 003_NhiemVu.txt
│   │   │   ├── 004_Environment.txt
│   │   │   ├── 005_Emotion.txt
│   │   │   ├── 006_ReturnOnly.txt
│   │   │   └── _module_manifest.json
│   │   ├── v2/
│   │   └── profiles/
│   │       ├── anime_a.json
│   │       ├── anime_b.json
│   │       └── movie_a.json
│   ├── app3/
│   │   ├── v1/
│   │   │   ├── 001_MatchingRules.txt
│   │   │   ├── 002_TimelineRules.txt
│   │   │   ├── 003_NarrativeRules.txt
│   │   │   ├── 004_ReuseRules.txt
│   │   │   ├── 005_ConfidenceRules.txt
│   │   │   ├── 006_OutputSchema.txt
│   │   │   └── _module_manifest.json
│   │   └── profiles/
│   └── shared/
│       ├── system_rules.txt
│       └── output_format.txt
│
├── modules/
│   ├── app1/                        ← APP1: Video Ingestion
│   ├── app2/                        ← APP2: Scene Analysis
│   ├── app3/                        ← APP3: Grouping
│   ├── app4/                        ← APP4: Reconstruction
│   ├── prompt_engine/               ← Prompt Engine (independent)
│   │   ├── engine.py
│   │   ├── module_stack.py
│   │   ├── profile_manager.py
│   │   ├── preview.py
│   │   ├── importer_exporter.py
│   │   └── workspace.py
│   └── core/
│       ├── models/                  ← Shared Contract Layer
│       │   ├── __init__.py
│       │   ├── scene.py
│       │   ├── analysis.py
│       │   ├── group.py
│       │   ├── session.py
│       │   └── manifest.py
│       ├── providers/               ← AI Provider Adapter Layer
│       │   ├── base.py
│       │   ├── openai_adapter.py
│       │   ├── ollama_adapter.py
│       │   ├── openrouter_adapter.py
│       │   ├── lmstudio_adapter.py
│       │   └── provider_factory.py
│       ├── storage/                 ← Storage interfaces
│       ├── config/                  ← Config loader
│       ├── logging/                 ← Logging service
│       └── errors/                  ← Centralized error handling
│
├── ui/                              ← UI Layer
│   ├── controllers/                 ← Gọi trực tiếp modules
│   │   ├── project_controller.py
│   │   ├── analysis_controller.py
│   │   ├── grouping_controller.py
│   │   ├── reconstruction_controller.py
│   │   └── prompt_controller.py
│   └── views/                       ← Pure UI (no business logic)
│       ├── main_window.py
│       ├── graph_view.py
│       ├── inspector_view.py
│       ├── prompt_workspace_view.py
│       ├── log_view.py
│       └── widgets/
│
├── config/                          ← Configuration
│   ├── settings.json
│   ├── providers/
│   ├── prompts/
│   │   ├── active_version.json
│   │   └── profiles/
│   └── ui/
│       ├── theme.json
│       └── layout.json
│
├── output/                          ← Project Output
│   └── <project>/
│       ├── session.json
│       ├── .state/
│       ├── source/
│       ├── packages/
│       │   ├── analysis/
│       │   ├── grouping/
│       │   ├── embeddings/          ← Embeddings = project artifact
│       │   └── source/
│       └── final/
│
├── cache/                           ← Temporary data only
│   ├── frames/
│   └── models/
│
├── logs/                            ← Application logs
│   ├── app1/
│   ├── app2/
│   ├── app3/
│   ├── app4/
│   └── combined.log
│
├── tests/                           ← Testing
│   ├── unit/
│   │   ├── app1/
│   │   ├── app2/
│   │   ├── app3/
│   │   ├── app4/
│   │   ├── prompt_engine/
│   │   └── core/
│   ├── integration/
│   └── e2e/
│
├── data/                            ← Built-in data (ontology, etc.)
├── plugins/                         ← FUTURE EXTENSION
└── SceneFlow.py                     ← Entry point
```

### Design Decisions

| Decision | Value |
|---|---|
| Application Structure | Single app (`SceneFlow`) với modules/ |
| Module Isolation | Mỗi APP có thư mục riêng, không chia sẻ code |
| Shared Code | Chỉ `modules/core/` là shared |
| Prompt Location | `prompts/` là Asset Layer riêng, không thuộc modules |
| UI Role | Thin UI: views → controllers → modules (no service layer) |
| Plugin | Future Extension — không build V1 |

---

## 2. MODULE STRUCTURE

### APP1 — Video Ingestion

```
modules/app1/
├── __init__.py
├── detector.py              ← Scene change detection
├── segmenter.py             ← Video segmentation
├── sampler.py               ← Keyframe sampling
├── extractor.py             ← Frame/OCR/ASR extraction
├── reconstructor_map.py     ← Build reconstruction_map.json
├── pipeline.py              ← Main pipeline orchestration
├── cli.py                   ← CLI entry point
└── models/                  ← APP1-specific types (not shared contracts)
```

**Output:** `output/<project>/source/`
**Consumers:** APP2, APP4

### APP2 — Scene Analysis

```
modules/app2/
├── __init__.py
├── runtime/
│   ├── __init__.py
│   ├── queue.py              ← Queue management
│   ├── worker.py             ← Worker process
│   ├── retry.py              ← Retry policy
│   ├── validator.py          ← Output validation
│   └── checkpoint.py         ← Save/resume state
├── services/
│   ├── analysis_service.py   ← Main analysis orchestration
│   └── batch_service.py      ← Batch processing
├── cli.py                    ← CLI entry point
└── models/                   ← APP2-specific types
```

**Input:** APP1 output (`source/`)
**Output:** `output/<project>/packages/analysis/`
**AI Calls:** Through Prompt Engine (receives Final Prompt)
**Consumers:** APP3

### APP3 — Grouping

```
modules/app3/
├── __init__.py
├── runtime/
│   ├── __init__.py
│   ├── matcher.py            ← Matching engine
│   ├── scorer.py             ← Scoring engine
│   ├── validator.py          ← Group validation
│   ├── reuse_tracker.py      ← Scene reuse tracking
│   └── checkpoint.py         ← Save/resume state
├── services/
│   ├── grouping_service.py   ← Main grouping orchestration
│   └── batch_service.py      ← Batch processing
├── strategies/               ← FUTURE EXTENSION
│   └── base.py               ← Abstract strategy
├── cli.py                    ← CLI entry point
└── models/                   ← APP3-specific types
```

**Input:** APP2 output (`analysis/`)
**Output:** `output/<project>/packages/grouping/`
**AI Calls:** Through Prompt Engine (receives Final Prompt)
**Consumers:** APP4

### APP4 — Reconstruction

```
modules/app4/
├── __init__.py
├── runtime/
│   ├── __init__.py
│   ├── cutter.py             ← Video cutting engine
│   ├── validator.py          ← Output validation
│   ├── checkpoint.py         ← Save/resume state
│   └── exporter.py           ← Export orchestration
├── services/
│   ├── reconstruction_service.py
│   └── batch_service.py
├── presets/                  ← Quality presets
│   ├── frame_accurate.py
│   ├── source_copy.py
│   └── balanced.py
├── cli.py                    ← CLI entry point
└── models/                   ← APP4-specific types
```

**Input:** APP3 output (`grouping/`) + APP1 output (`source/`)
**Output:** `output/<project>/final/`
**AI Calls:** None (pure reconstructor)

### Prompt Engine

```
modules/prompt_engine/
├── __init__.py
├── engine.py                 ← Core: module management + composition
├── module_stack.py           ← Module ordering (ComfyUI-style)
├── profile_manager.py        ← Profile loading + switching
├── workspace.py              ← Workspace management (APP2, APP3)
├── preview.py                ← Prompt preview
├── importer_exporter.py      ← Import/Export TXT
├── pipeline.py               ← Final Prompt assembly pipeline
└── models/
    ├── module.py             ← Module model
    ├── profile.py            ← Profile model
    └── workspace.py          ← Workspace model
```

**Responsibilities:**
- Module management (Add/Delete/Rename/Duplicate/Enable/Disable/Move Up/Move Down)
- Module ordering (unlimited modules, numbered 001-999)
- Profile management (Anime_A, Anime_B, Movie_A, Movie_B, Custom_A)
- Version management (v1, v2)
- Profile = enabled modules + order + version (does NOT copy prompt content)
- Import/Export TXT
- Prompt preview
- Final Prompt assembly

**Non-Responsibilities (FORBIDDEN):**
- ❌ Gọi AI
- ❌ Phân tích ảnh
- ❌ Business logic APP2
- ❌ Business logic APP3

**Output:** Final Prompt string → passed to APP2 or APP3

### Core — Shared Services

```
modules/core/
├── __init__.py
├── models/                   ← Shared Contract Layer
│   ├── __init__.py
│   ├── scene.py
│   ├── analysis.py
│   ├── group.py
│   ├── session.py
│   └── manifest.py
├── providers/                ← AI Provider Adapter Layer
│   ├── __init__.py
│   ├── base.py
│   ├── openai_adapter.py
│   ├── ollama_adapter.py
│   ├── openrouter_adapter.py
│   ├── lmstudio_adapter.py
│   └── provider_factory.py
├── storage/
│   ├── __init__.py
│   ├── base.py               ← Storage interface
│   └── file_storage.py       ← File-based implementation
├── config/
│   ├── __init__.py
│   ├── loader.py             ← Config loader
│   └── validator.py          ← Config validation
├── logging/
│   ├── __init__.py
│   ├── logger.py             ← Logger setup
│   └── formatter.py          ← JSON formatter
├── errors/
│   ├── __init__.py
│   ├── base.py               ← Base exception
│   ├── app_errors.py         ← Per-app error types
│   ├── provider_errors.py    ← Provider error types
│   ├── system_errors.py      ← System error types
│   └── error_service.py      ← Centralized error handling
└── utils/
    ├── __init__.py
    ├── time_utils.py
    └── file_utils.py
```

---

## 3. OWNERSHIP MAP

### Module Ownership Boundaries

| Module | Owner | Input | Output | AI? |
|---|---|---|---|---|
| `modules/app1/` | APP1 | Video file | `source/` | No |
| `modules/app2/` | APP2 | `source/` | `analysis/` | Yes (via Prompt Engine) |
| `modules/app3/` | APP3 | `analysis/` | `grouping/` | Yes (via Prompt Engine) |
| `modules/app4/` | APP4 | `grouping/` + `source/` | `final/` | No |
| `modules/prompt_engine/` | Shared | `prompts/` | Final Prompt | No |
| `modules/core/` | Shared | — | — | No |

### Dependency Direction

```
prompts/ (Asset Layer — no ownership, read-only by Prompt Engine)
    ↓
modules/prompt_engine/
    ↓ (provides Final Prompt string)
modules/app2/ ← reads from core/providers/
    ↓
modules/app3/ ← reads from core/providers/
    ↓
modules/app4/ ← reads from core/storage/
    ↓
output/<project>/final/
```

**Strict Rules:**
```
app1 → core (storage, config, logging)
app2 → core + prompt_engine + prompts
app3 → core + prompt_engine + prompts + app2 output
app4 → core + app3 output + app1 output
prompt_engine → core + prompts (read-only)
ui/controllers → modules (any)
ui/views → NO modules
```

**FORBIDDEN Dependencies:**
```
app1 → app2 ✗
app2 → app3 ✗
app3 → app4 ✗
app2 → prompts (direct) ✗ (must go through prompt_engine)
ui/views → modules (direct) ✗ (must go through controllers)
```

### File Ownership

| Data | Owner | Producer | Consumer | Immutable |
|---|---|---|---|---|
| `source/` | APP1 | APP1 | APP2, APP4 | scene_id, timestamps |
| `analysis/` | APP2 | APP2 | APP3 | scene_id |
| `grouping/` | APP3 | APP3 | APP4 | group_id, scene_ids |
| `final/` | APP4 | APP4 | Creator | scene_id, filenames |
| `embeddings/` | APP2 | APP2 | APP3 | scene_id |

---

## 4. RUNTIME STRUCTURE

### APP2 Runtime (Queue + Worker)

```
modules/app2/runtime/
├── queue.py
│   ├── SceneQueue class
│   ├── add(scene_id)
│   ├── get_next() -> scene_id | None
│   ├── mark_done(scene_id)
│   ├── mark_failed(scene_id, error)
│   ├── get_status(scene_id) -> status
│   └── get_all() -> list[scene_status]
│
├── worker.py
│   ├── SceneWorker class
│   ├── process(scene_id) -> result
│   ├── run_batch(queue, max_workers)
│   └── _call_ai(prompt) -> response
│
├── retry.py
│   ├── RetryPolicy class
│   ├── max_attempts: int = 3
│   ├── backoff: float = 2.0
│   └── should_retry(error, attempt) -> bool
│
├── validator.py
│   ├── validate_analysis(result) -> ValidationResult
│   └── schema: dict  # references core/models/
│
└── checkpoint.py
    ├── CheckpointManager class
    ├── save(state)
    ├── load() -> state | None
    └── clear()
```

### APP3 Runtime (Matcher + Scorer)

```
modules/app3/runtime/
├── matcher.py
│   ├── SceneMatcher class
│   ├── match(script_chunk, scenes) -> list[Match]
│   └── _compute_scores(match) -> Scores
│
├── scorer.py
│   ├── SceneScorer class
│   ├── semantic_score(match) -> float
│   ├── timeline_score(match) -> float
│   ├── narrative_flow_score(match) -> float
│   └── confidence_score(match) -> float
│
├── validator.py
│   ├── GroupValidator class
│   ├── validate_group(group) -> ValidationResult
│   └── validate_manifest(manifest) -> ValidationResult
│
├── reuse_tracker.py
│   ├── ReuseTracker class
│   ├── track_use(scene_id, group_id)
│   ├── get_reuse_count(scene_id) -> int
│   └── get_penalty(scene_id) -> float
│
└── checkpoint.py
    ├── CheckpointManager class
    ├── save(state)
    ├── load() -> state | None
    └── clear()
```

### APP4 Runtime (Cutter + Exporter)

```
modules/app4/runtime/
├── cutter.py
│   ├── VideoCutter class
│   ├── cut(scene_id, start, end, output_path) -> Result
│   ├── _frame_accurate_cut(...)
│   ├── _stream_copy_cut(...)
│   └── _retry_cut(...)
│
├── validator.py
│   ├── ReconstructionValidator class
│   ├── validate_scene(scene_id, file) -> ValidationResult
│   ├── validate_group(group) -> ValidationResult
│   └── validate_batch(manifest) -> ValidationResult
│
├── checkpoint.py
│   ├── CheckpointManager class
│   ├── save(state)
│   ├── load() -> state | None
│   └── clear()
│
└── exporter.py
    ├── Exporter class
    ├── export_final_manifest(groups) -> FinalManifest
    ├── export_reconstruction_report(stats) -> Report
    └── export_timeline(groups) -> TimelineExport
```

### Core Runtime Interfaces

```
modules/core/storage/
├── base.py
│   ├── StorageInterface (ABC)
│   │   ├── read(path) -> str | bytes
│   │   ├── write(path, data)
│   │   ├── delete(path)
│   │   ├── exists(path) -> bool
│   │   └── list(dir) -> list[str]
│
└── file_storage.py
    └── FileStorage(StorageInterface)
```

---

## 5. SESSION STRUCTURE

### Session Lifecycle

```
1. User creates/opens project
    ↓
2. Initialize session.json in output/<project>/
    ↓
3. APP begins processing
    ↓
4. Checkpoint updated per scene/group
    ↓
5. On resume:
    ├─ Load session.json
    ├─ Load .state/ checkpoints
    ├─ Identify last incomplete step
    └─ Resume from checkpoint
    ↓
6. On completion:
    └─ Finalize session (status = "complete")
```

### Session JSON Schema

```json
{
  "session_version": "1.0",
  "session_id": "sess_20260601_001",
  "project": "naruto_review_v2",
  "status": "app2_in_progress",
  "last_app_completed": "app1",
  "next_app": "app2",
  "total_scenes": 50,
  "processed_scenes": 23,
  "failed_scenes": 1,
  "created_at": "2026-06-01T12:00:00Z",
  "updated_at": "2026-06-01T12:30:00Z",
  "completed_at": null
}
```

### Status Transitions

```
created → app1_in_progress → app1_complete
    ↓
app2_in_progress → app2_complete
    ↓
app3_in_progress → app3_complete
    ↓
app4_in_progress → app4_complete → complete

Any status can transition to paused (on user interrupt)
paused can resume to previous status
```

### Checkpoint Location

```
output/<project>/
├── session.json
└── .state/
    ├── app1_checkpoint.json
    ├── app2_checkpoint.json
    ├── app3_checkpoint.json
    └── app4_checkpoint.json
```

---

## 6. PROVIDER ARCHITECTURE

### Provider Adapter Layer

```
modules/core/providers/
├── base.py                    ← Abstract base class
├── openai_adapter.py         ← OpenAI, OpenRouter (OpenAI-compatible API)
├── ollama_adapter.py         ← Ollama local
├── openrouter_adapter.py     ← OpenRouter (explicit)
├── lmstudio_adapter.py       ← LM Studio local
├── vision_adapter.py         ← Local vision models
└── provider_factory.py       ← Factory: provider_name → adapter
```

### Base Adapter Interface

```python
class BaseProvider(ABC):
    """Minimum interface — không hỗ trợ vision nếu provider không có."""

    @abstractmethod
    async def complete(self, prompt: str, **kwargs) -> str:
        """Text completion. Có kèm image_url trong kwargs nếu vision task."""
        ...

    @abstractmethod
    async def embed(self, text: str, **kwargs) -> list[float]:
        """Embedding. Optional — provider có thể raise NotImplementedError."""
        ...

    @abstractmethod
    def get_model_info(self) -> dict:
        """Trả về model metadata."""
        ...
```

### Provider Config

```json
{
  "provider": "ollama",
  "model": "llama3.2-vision",
  "base_url": "http://localhost:11434",
  "timeout": 120,
  "max_retries": 3,
  "concurrent_requests": 2
}
```

### Provider Discovery

```
provider_factory:
    → Load config/settings.json → "active_provider"
    → Instantiate adapter from registry
    → Return adapter instance
    → Fallback: if provider fails, try next in priority list
```

### Provider Support Matrix

| Feature | OpenAI | Ollama | OpenRouter | LM Studio |
|---|---|---|---|---|
| Text Completion | ✅ | ✅ | ✅ | ✅ |
| Vision | ✅ | ✅ | ✅ | ✅ |
| Embedding | ✅ | ✅ | ✅ | ✅ |
| Streaming | ✅ | ✅ | ✅ | ✅ |
| Concurrent | ✅ | ✅ | ✅ | ✅ |
| Local | ❌ | ✅ | ❌ | ✅ |

---

## 7. PROMPT ARCHITECTURE INTEGRATION

### Prompt Flow

```
prompts/ (Asset Layer — git-tracked, versioned)
    ↓ (read-only by Prompt Engine)
modules/prompt_engine/
    ├─ Load prompts from prompts/ based on workspace
    ├─ Compose modules based on profile
    ├─ Inject metadata
    └─ Output Final Prompt string
    ↓ (Final Prompt passed to APP2 or APP3)
modules/app2/ or modules/app3/
    ← Receives Final Prompt
    ← Calls AI Provider with Final Prompt
    ← Returns structured output
```

### Prompt Engine Workspace

```
modules/prompt_engine/
├── engine.py
│   ├── PromptEngine class
│   ├── set_workspace(workspace: "app2" | "app3")
│   ├── set_version(version: str)
│   ├── set_profile(profile: str)
│   ├── get_modules() → list[Module]
│   ├── add_module(name, path)
│   ├── delete_module(module_id)
│   ├── rename_module(module_id, new_name)
│   ├── duplicate_module(module_id)
│   ├── enable_module(module_id)
│   ├── disable_module(module_id)
│   ├── move_up(module_id)
│   ├── move_down(module_id)
│   └── compose() → str  # Final Prompt
│
├── module_stack.py
│   ├── ModuleStack class
│   ├── modules: list[Module]
│   ├── ordering: dict[int, Module]  # order_number → Module
│   └── sort() → list[Module]
│
├── profile_manager.py
│   ├── ProfileManager class
│   ├── list_profiles(workspace) → list[str]
│   ├── load_profile(workspace, profile) → Profile
│   ├── save_profile(workspace, profile, state)
│   ├── switch_profile(workspace, profile)
│   └── Profile model
│       ├── name: str
│       ├── version: str
│       ├── enabled_modules: list[str]
│       ├── module_order: list[int]
│       └── metadata: dict
│
├── preview.py
│   ├── PromptPreview class
│   ├── render(module_ids, metadata) → str
│   └── highlight_syntax(prompt) → str
│
├── importer_exporter.py
│   ├── import_txt(path) → Module
│   ├── export_txt(module_id, path)
│   └── batch_import(paths) → list[Module]
│
└── workspace.py
    ├── Workspace class
    ├── name: str ("app2" | "app3")
    ├── versions: list[str]
    ├── profiles: list[Profile]
    ├── active_version: str
    └── active_profile: Profile
```

### Final Prompt Composition Formula

```
Module Stack (ordered, enabled only)
    +
Profile (active version + module order + enabled/disabled)
    +
Metadata Injection (scene data, timestamps, etc.)
    =
Final Prompt
```

### Profile = Preset (NOT Copy)

```json
{
  "profile_name": "anime_a",
  "version": "v1",
  "enabled_modules": [
    "001_Luat",
    "002_NhanVat",
    "003_NhiemVu",
    "004_Environment",
    "006_ReturnOnly"
  ],
  "disabled_modules": [
    "005_Emotion"
  ],
  "module_order": [1, 2, 3, 4, 6],
  "notes": "Standard anime analysis profile"
}
```

**Profile does NOT copy prompt content.**
**Profile chỉ lưu trạng thái module + order + version.**

### Module File Structure

```
prompts/
├── app2/
│   ├── v1/
│   │   ├── 001_Luat.txt              ← Module content (unlimited)
│   │   ├── 002_NhanVat.txt
│   │   ├── 003_NhiemVu.txt
│   │   ├── 004_Environment.txt
│   │   ├── 005_Emotion.txt
│   │   ├── 006_ReturnOnly.txt
│   │   ├── ... (up to 999)
│   │   └── _module_manifest.json
│   ├── v2/
│   │   └── ...
│   └── profiles/
│       ├── anime_a.json
│       ├── anime_b.json
│       └── movie_a.json
├── app3/
│   ├── v1/
│   │   ├── 001_MatchingRules.txt
│   │   ├── 002_TimelineRules.txt
│   │   ├── 003_NarrativeRules.txt
│   │   ├── 004_ReuseRules.txt
│   │   ├── 005_ConfidenceRules.txt
│   │   └── 006_OutputSchema.txt
│   └── profiles/
│       ├── review.json
│       └── highlight.json
└── shared/
    ├── system_rules.txt
    └── output_format.txt
```

---

## 8. STORAGE STRUCTURE

### Directory Layout

```
output/<project>/
├── session.json                  ← Session state
├── .state/                       ← Checkpoints (hidden)
│   ├── app1_checkpoint.json
│   ├── app2_checkpoint.json
│   ├── app3_checkpoint.json
│   └── app4_checkpoint.json
├── source/                       ← APP1 output
│   ├── source_reconstruction_map.json
│   ├── source_master_timeline.json
│   ├── source_subtitles.json
│   └── source_audio_regions.json
├── packages/
│   ├── analysis/                 ← APP2 output
│   │   ├── scene_src_0001.json
│   │   └── ...
│   ├── grouping/                 ← APP3 output
│   │   ├── group_0001.json
│   │   ├── group_manifest.json
│   │   └── ...
│   └── embeddings/               ← Project artifact (NOT cache)
│       ├── scene_embeddings.json
│       └── metadata.json
└── final/                        ← APP4 output
    ├── final_manifest.json
    ├── reconstruction_report.json
    ├── 0001/
    ├── 0002/
    └── ...

cache/
├── frames/                       ← Downloaded keyframes (temporary)
├── models/                       ← Cached model responses
└── temp/                         ← Per-session temp files

logs/
├── app1/
├── app2/
├── app3/
├── app4/
└── combined.log
```

### Lifecycle Rules

| Directory | Type | Lifecycle | Cleanup |
|---|---|---|---|
| `output/<project>/` | Artifact | Persistent | Manual delete per project |
| `output/<project>/embeddings/` | Artifact | Persistent | Manual delete per project |
| `cache/frames/` | Temporary | Session | Auto-cleanup after session |
| `cache/models/` | Temporary | TTL (24h) | Auto-cleanup by TTL |
| `cache/temp/` | Temporary | Per-session | Auto-cleanup after session |
| `logs/` | Rotating | 30-day retention | Auto-rotate |

### Embedding Storage Rules

```
Embedding là dữ liệu dự án → lưu trong output/<project>/packages/
Embedding KHÔNG phải cache → KHÔNG lưu trong cache/

Lý do:
- Embedding cần tái sử dụng qua nhiều session
- Embedding là artifact của APP2
- Cache chỉ dành cho dữ liệu tạm (frames, model responses)
```

---

## 9. UI STRUCTURE

### Architecture

```
ui/
├── controllers/              ← User input → module calls
│   ├── __init__.py
│   ├── project_controller.py
│   │   ├── create_project(name, video_path)
│   │   ├── open_project(path)
│   │   ├── save_project()
│   │   └── get_project_status()
│   │
│   ├── analysis_controller.py
│   │   ├── run_analysis(config)
│   │   ├── pause_analysis()
│   │   ├── resume_analysis()
│   │   ├── get_analysis_progress() → Progress
│   │   └── get_analysis_results() → list[Analysis]
│   │
│   ├── grouping_controller.py
│   │   ├── run_grouping(config)
│   │   ├── get_groups() → list[Group]
│   │   ├── get_group_detail(group_id) → Group
│   │   └── export_manifest()
│   │
│   ├── reconstruction_controller.py
│   │   ├── run_reconstruction(config)
│   │   ├── get_progress() → Progress
│   │   └── get_report() → Report
│   │
│   └── prompt_controller.py
│       ├── get_workspace(name) → Workspace
│       ├── list_modules(workspace) → list[Module]
│       ├── list_profiles(workspace) → list[Profile]
│       ├── switch_profile(workspace, profile)
│       ├── add_module(workspace, name, content)
│       ├── delete_module(workspace, module_id)
│       ├── enable_module(workspace, module_id, enabled)
│       ├── move_module(workspace, module_id, position)
│       ├── preview_prompt(workspace) → str
│       └── import_txt(path)
│
└── views/                     ← Pure UI (NO business logic)
    ├── __init__.py
    ├── main_window.py
    ├── project_view.py
    ├── graph_view.py
    ├── inspector_view.py
    ├── prompt_workspace_view.py
    ├── log_view.py
    └── widgets/
        ├── node_widget.py
        ├── timeline_widget.py
        ├── preview_widget.py
        └── module_list_widget.py
```

### Interaction Flow

```
User clicks "Run Analysis" button
    ↓
view/analysis_view.py                       ← captures click
    → calls controller/analysis_controller.py
        → calls modules/app2/ (direct, no service layer)
            → processes scenes
            → returns results
        ← returns results
    ← returns results to view
    ↓
view displays results
```

### Ownership Rules

| Layer | Contains | Cannot Contain |
|---|---|---|
| `views/` | UI components, layouts, event capture | Business logic, queue, AI calls, storage |
| `controllers/` | Orchestration, user action handling | UI rendering |

### Strict Rules

```
views:
    ← Gọi controller methods
    ← Hiển thị kết quả
    ← Capture user events
    ← KHÔNG import modules trực tiếp
    ← KHÔNG chứa business logic

controllers:
    ← Gọi modules trực tiếp
    ← Xử lý user input
    ← Return data cho views
    ← KHÔNG chứa UI rendering
    ← KHÔNG chứa runtime implementation
```

---

## 10. CONFIG STRUCTURE

### Config Layout

```
config/
├── settings.json              ← Global system settings
├── providers/                 ← Provider profiles
│   ├── default.json
│   ├── openai.json
│   ├── ollama.json
│   ├── openrouter.json
│   └── lmstudio.json
├── prompts/                   ← Prompt engine settings
│   ├── active_version.json
│   └── profiles/
│       ├── app2/
│       │   ├── anime_a.json
│       │   ├── anime_b.json
│       │   ├── movie_a.json
│       │   └── movie_b.json
│       └── app3/
│           ├── review.json
│           └── highlight.json
└── ui/                        ← UI appearance
    ├── theme.json
    └── layout.json
```

### Settings.json Schema

```json
{
  "version": "1.0",
  "active_provider": "ollama",
  "provider_config": "ollama.json",
  "active_prompt_version": "v1",
  "active_prompt_profile_app2": "anime_a",
  "active_prompt_profile_app3": "review",
  "active_export_profile": "frame_accurate",
  "system": {
    "max_concurrent_workers": 2,
    "default_timeout": 120,
    "max_retries": 3,
    "log_level": "info",
    "log_retention_days": 30
  }
}
```

### Config Loading Strategy

```
1. Load config/settings.json
2. Resolve active_provider → load config/providers/{provider_config}
3. Resolve active prompt profiles → load prompt profiles
4. Merge: settings.json + provider config + profile config
5. Validate merged config
6. Return to application
```

---

## 11. PLUGIN STRUCTURE

### Status: FUTURE EXTENSION

Plugin architecture được ghi nhận nhưng **KHÔNG được implement ở V1.**

### Future Plugin Types

| Type | Description | V1 |
|---|---|---|
| Prompt Modules | Custom prompt blocks | Built-in |
| AI Providers | Custom provider adapters | Built-in |
| Grouping Strategies | Custom matching/scoring | Not in V1 |
| Exporters | Custom export formats | Not in V1 |

### Plugin Manifest (Future)

```json
{
  "name": "my_plugin",
  "type": "grouping_strategy",
  "version": "1.0.0",
  "entry": "strategy.py",
  "dependencies": ["python>=3.10"],
  "compatibility": {
    "system_version": ">=1.0"
  }
}
```

---

## 12. ERROR HANDLING STRUCTURE

### Error Hierarchy

```
BaseAppError (ABC)
├── ValidationError          ← Input validation
├── ProcessingError          ← Processing failure
├── ProviderError            ← AI provider failure
├── ConfigError              ← Configuration error
└── StorageError             ← Storage/IO error
```

### Error Ownership

| Error Type | Owner | Behavior | Logged To |
|---|---|---|---|
| APP2 ValidationError | APP2 | Skip scene, log error, continue | `logs/app2/` |
| APP2 ProviderError | APP2 | Retry (up to max_attempts), then skip | `logs/app2/` |
| APP3 ProcessingError | APP3 | Log error, mark group failed | `logs/app3/` |
| APP3 ConfidenceError | APP3 | Flag for review, continue | `logs/app3/` |
| APP4 CutError | APP4 | Retry 2x, then mark failed | `logs/app4/` |
| ProviderError | Core | Log, try fallback provider | `logs/combined.log` |
| ConfigError | Core | STOP, notify user | `logs/combined.log` |
| StorageError | Core | Log, retry, STOP if critical | `logs/combined.log` |

### Error Handling Flow

```
Scene processing fails in APP2:
    1. Worker catches exception
    2. Log error to logs/app2/
    3. RetryPolicy.should_retry()?
        → Yes → retry with backoff
        → No → mark scene as failed
    4. Continue to next scene
    5. On completion: report failed scenes
```

---

## 13. TESTING STRUCTURE

### Test Layout

```
tests/
├── __init__.py
├── unit/                     ← Fast, isolated, mock providers
│   ├── app1/
│   │   ├── test_detector.py
│   │   └── test_segmenter.py
│   ├── app2/
│   │   ├── test_queue.py
│   │   ├── test_worker.py
│   │   ├── test_retry.py
│   │   └── test_validator.py
│   ├── app3/
│   │   ├── test_matcher.py
│   │   ├── test_scorer.py
│   │   └── test_validator.py
│   ├── app4/
│   │   ├── test_cutter.py
│   │   ├── test_validator.py
│   │   └── test_exporter.py
│   ├── prompt_engine/
│   │   ├── test_engine.py
│   │   ├── test_module_stack.py
│   │   ├── test_profile_manager.py
│   │   └── test_preview.py
│   └── core/
│       ├── providers/
│       │   └── test_provider_factory.py
│       ├── models/
│       │   └── test_contracts.py
│       └── test_config.py
│
├── integration/              ← Real storage, mock providers
│   ├── test_app2_pipeline.py
│   ├── test_app3_grouping.py
│   └── test_app4_reconstruction.py
│
└── e2e/                      ← Full pipeline, real providers (optional)
    ├── test_full_pipeline.py
    ├── test_resume_session.py
    └── test_error_recovery.py
```

### Test Rules

| Level | External Dependencies | Providers | Speed |
|---|---|---|---|
| Unit | Mock everything | Mock | Fast (< 1s per test) |
| Integration | Real storage | Mock | Medium |
| E2E | Real storage + files | Real (optional) | Slow |

### Test Categories

```
Unit tests:
    - Module-level logic
    - Data validation
    - Error handling
    - Queue operations
    - Retry logic
    - Config loading

Integration tests:
    - APP2 full pipeline (queue → worker → validation → save)
    - APP3 grouping flow (matcher → scorer → validator)
    - APP4 reconstruction flow (cutter → validator → exporter)
    - Core + app module interaction
    - Provider adapter integration

E2E tests:
    - Full pipeline: import → process → export
    - Session save/resume
    - Error recovery
    - Concurrent processing
```

---

## 14. DEPENDENCY GRAPH

### Module Dependency Graph

```
                      prompts/
                         ↓
                  prompt_engine/
                         ↓
prompts ────────────────┘
                         
modules/core/
├── models/                       ← No dependencies
├── providers/                    ← No dependencies
├── storage/                      ← No dependencies
├── config/                       ← No dependencies
├── logging/                      ← No dependencies
└── errors/                       ← No dependencies

modules/app1/                     ← core/*
    ↓
output/<project>/source/

modules/app2/                     ← core/*, prompt_engine
    ↓
output/<project>/packages/analysis/
output/<project>/packages/embeddings/

modules/app3/                     ← core/*, prompt_engine
    ↓ (reads app2 output)
output/<project>/packages/grouping/

modules/app4/                     ← core/*
    ↓ (reads app1 + app3 output)
output/<project>/final/
```

### Strict Dependency Direction

```
core/ (no deps)
    ↑
app1/
    ↑
app2/ → app1 output
    ↑
app3/ → app2 output
    ↑
app4/ → app1 output + app3 output
    ↑
ui/controllers/ → any module
    ↑
ui/views/ → controllers
```

### Dependency Rules (Locked)

```
# ALWAYS TRUE:
appX → core (shared services)
app2 → prompt_engine (to receive Final Prompt)
app3 → prompt_engine (to receive Final Prompt)

# NEVER TRUE:
app1 → app2 (direct)
app2 → app3 (direct)
app3 → app4 (direct)
ui/views → modules (direct)
app2 → prompts (direct) — must go through prompt_engine
app3 → prompts (direct) — must go through prompt_engine
```

---

*End of SYSTEM_ARCHITECTURE.md*