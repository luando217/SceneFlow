# EXECUTION WORKFLOW

**Version:** Phase 3.3
**Status:** Locked
**Date:** 2026-06-01

---

## 1. PROJECT LIFECYCLE

### Project Definition

```
Project = folder in output/
    └─ Contains all data for one video processing job
    └─ Lifetime: created → active → complete → archived
    └─ Location: output/<project_name>/
```

### Project States

| State | Trigger | Description |
|---|---|---|
| **created** | User creates project (name + video) | Project folder created, session.json initialized |
| **active** | APP1 begins | Processing in progress |
| **paused** | User interrupts | All workers stopped, checkpoints saved |
| **complete** | APP4 finishes + final_manifest.json exists | All output ready |
| **archived** | User archives | No active processing |

### Project Creation

```
User:
    ├─ Set project name
    └─ Select video file

System:
    → Create: output/<project_name>/
    → Create: session.json (status: "created")
    → Copy video reference to project
    → status → "active"
```

### Project Deletion

```
User: Delete project
    → Confirm dialog
    → Delete: output/<project_name>/ (recursive)
    → Remove from project list
```

---

## 2. SESSION LIFECYCLE

### Session Definition

```
Session = instance of processing
    └─ One session per project
    └─ Tracks: current APP, progress, checkpoints
    └─ Stored in: output/<project>/session.json
```

### Session States

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

### Session Resume

```
1. Load: output/<project>/session.json
2. Check: status == "paused"?
3. Load: .state/{last_app}_checkpoint.json
4. Identify: last incomplete scene/group
5. Resume from checkpoint
```

### Session Completion

```
APP4 completes:
    → status = "complete"
    → completed_at = timestamp
    → Final output ready
```

---

## 3. APP EXECUTION ORDER

### Sequential Order (Required)

```
APP1 → APP2 → APP3 → APP4
```

### Dependency Rules

| Transition | Requirement |
|---|---|
| APP1 → APP2 | `source/` must exist and be complete |
| APP2 → APP3 | `packages/analysis/` must exist and be complete |
| APP3 → APP4 | `packages/grouping/` must exist and be complete |

### APP1 Requirements

```
APP1 complete when:
    └─ source/source_reconstruction_map.json exists
    └─ source/source_master_timeline.json exists
    └─ source/source_subtitles.json exists (if available)
    └─ User confirmed Intro/Outro selection
    └─ User triggered APP2
```

### APP2 Requirements

```
APP2 complete when:
    └─ All scenes have analysis output
    └─ packages/analysis/ complete
    └─ User triggered APP3
```

### APP3 Requirements

```
APP3 complete when:
    └─ All groups have grouping output
    └─ packages/grouping/ complete
    └─ User confirmed group review
    └─ User triggered APP4
```

### APP4 Requirements

```
APP4 complete when:
    └─ All groups have final/ output
    └─ final/final_manifest.json exists
    └─ MP4 files created by Scene ID
```

### Run Modes

| Mode | Behavior |
|---|---|
| **Full run** | APP1 → APP2 → APP3 → APP4 (triggered by user) |
| **Single APP** | User selects specific APP to run |
| **Re-run** | Re-run APP without clearing previous output (incremental) |

---

## 4. APP1: VIDEO PACKAGING SYSTEM

### Overview

```
APP1 = Video Packaging System
    └─ Prepares source data for APP2/APP3/APP4
    └─ NOT scene analysis
    └─ User must confirm before proceeding
```

### APP1 Workflow

```
STEP 1: Load Video
    └─ User selects video file
    └─ Validate video format
    └─ Extract metadata (duration, resolution, fps)

STEP 2: Load Subtitle
    └─ Auto-detect .srt/.ass/.vtt in same folder
    └─ User can override/subtitle path
    └─ Parse subtitle into timeline

STEP 3: Detect Scenes
    └─ Shot boundary detection
    └─ Extract keyframes per scene
    └─ Generate scene list with timestamps
    └─ Output: source_master_timeline.json

STEP 4: User Review Intro/Outro
    └─ User views scene list
    └─ User selects Intro scenes (flag as intro)
    └─ User selects Outro scenes (flag as outro)
    └─ Intro/Outro saved to profile
    └─ Profile: prompts_scene_analyzer/active_profile.json

STEP 5: Save Profile
    └─ Save: prompts_scene_analyzer/active_profile.json
    └─ Include: intro scenes, outro scenes, user notes
    └─ Profile persists for batch processing

STEP 6: Generate Packages
    └─ Export: source/source_reconstruction_map.json
    └─ Export: source/source_master_timeline.json
    └─ Export: source/source_subtitles.json
    └─ Export: source/source_audio_regions.json (if audio detected)

STEP 7: User Triggers APP2
    └─ User reviews source packages
    └─ User clicks "Start Scene Analysis"
    └─ APP2 begins
```

### APP1 Output

```
output/<project>/source/
├── source_reconstruction_map.json    ← Mapping: scene_id → video segment
├── source_master_timeline.json       ← All scenes with timestamps
├── source_subtitles.json             ← Subtitle timeline (if available)
└── source_audio_regions.json        ← Audio regions (if available)
```

### APP1 Checkpoint

```
output/<project>/.state/
└── app1_checkpoint.json
    ├── last_step: "generate_packages"
    ├── scenes_detected: 50
    ├── intro_scenes: [0, 1, 2]
    └── outro_scenes: [47, 48, 49]
```

### APP1 Review Loop

```
APP1 does NOT auto-transition to APP2.

User must:
    1. Review detected scenes
    2. Confirm Intro/Outro selection
    3. Click "Generate Packages"
    4. Click "Start Scene Analysis" (manual trigger)

Workflow:
    Load Video → Detect Scenes → User Review → Save Profile → Generate Package
        ↓
    USER TRIGGERS APP2 (not auto)
```

---

## 5. APP2: SCENE ANALYSIS

### Overview

```
APP2 = Scene Analysis
    └─ Analyzes each scene using AI
    └─ Uses Prompt Engine to compose Final Prompt
    └─ Supports Single Scene Test + Batch Mode
```

### APP2 Modes

| Mode | Purpose | When to Use |
|---|---|---|
| **Single Scene Test** | Prompt tuning | Before running batch |
| **Batch Mode** | Production | After prompt is stable |

### APP2 Single Scene Test Mode

```
Purpose: Tune prompt before batch run

Workflow:
    1. User selects one scene (e.g., scene_src_0012)
    2. Load scene data (keyframes, subtitles)
    3. Build Final Prompt via Prompt Engine
        └─ Load active profile (anime_a, movie_b, etc.)
        └─ Load active version (v1, v2)
        └─ Compose modules in order
        └─ Inject scene metadata
    4. Run analysis on single scene
    5. Display output for review
    6. User reviews output
    7. User edits prompt (if needed)
        └─ Enable/disable modules
        └─ Adjust module order
        └─ Edit module content
    8. Re-run on same scene
    9. Repeat until output meets requirements
    10. Switch to Batch Mode

Single Scene Test Loop:
    Select Scene → Build Prompt → Run → Review → Edit Prompt → Re-run
        ↑__________________________________________|
```

### APP2 Batch Mode

```
Purpose: Process all scenes in production

Prerequisite: Prompt is stable from Single Scene Test Mode

Workflow:
    1. User clicks "Run Batch Analysis"
    2. For each scene (sorted by scene_id):
        └─ Build Final Prompt (via Prompt Engine)
        └─ Call AI Provider (vision + text)
        └─ Validate output (schema check)
        └─ Retry on failure (max 3 attempts)
        └─ Save to: packages/analysis/scene_src_XXXX.json
        └─ Update checkpoint
    3. Generate embeddings → packages/embeddings/
    4. Report: success/fail count

Batch Processing:
    Queue: [scene_001, scene_002, ..., scene_0050]
    Worker: process scenes concurrently (max_workers = config)
    Checkpoint: after each scene completion
```

### APP2 Prompt Engine Integration

```
Prompt Engine receives:
    └─ Workspace: "app2"
    └─ Profile: anime_a | anime_b | movie_a | movie_b | custom_a
    └─ Version: v1 | v2
    └─ Module list with enabled/disabled status

Prompt Engine returns:
    └─ Final Prompt string (composed)

APP2 receives Final Prompt and:
    └─ Sends to AI Provider (with scene data)
    └─ Receives analysis output
```

### APP2 Output

```
output/<project>/packages/
├── analysis/
│   ├── scene_src_0001.json
│   ├── scene_src_0002.json
│   └── ...
└── embeddings/
    ├── scene_embeddings.json
    └── metadata.json
```

### APP2 Checkpoint

```
output/<project>/.state/
└── app2_checkpoint.json
    ├── last_scene_processed: "scene_src_0023"
    ├── total_scenes: 50
    ├── processed_scenes: 23
    ├── failed_scenes: 1
    └── failed_scene_ids: ["scene_src_0015"]
```

### APP2 User Trigger

```
APP2 does NOT auto-transition to APP3.

After batch completes:
    1. Display results summary
    2. User reviews failed scenes (if any)
    3. User clicks "Start Grouping"
    4. APP3 begins
```

---

## 6. APP3: GROUPING

### Overview

```
APP3 = Grouping
    └─ Groups scenes based on script chunks / narrative segments
    └─ Uses Matcher + Scorer + Validator
    └─ Requires user review + confirmation before APP4
```

### APP3 Workflow

```
STEP 1: Load Analysis Data
    └─ Load all scenes from: packages/analysis/
    └─ Load embeddings from: packages/embeddings/

STEP 2: Match Scenes
    └─ For each script chunk:
        └─ Match relevant scenes
        └─ Score matches (semantic + timeline + narrative)
        └─ Build candidate groups

STEP 3: Score Groups
    └─ Semantic score (entity overlap, action overlap)
    └─ Timeline score (chronological order)
    └─ Narrative flow score (story continuity)
    └─ Confidence score (overall quality)

STEP 4: Validate Groups
    └─ Group size validation
    └─ Scene overlap check
    └─ Duplicate detection
    └─ Confidence threshold check

STEP 5: Build Groups
    └─ Generate group JSON files
    └─ Save to: packages/grouping/

STEP 6: Generate Manifest
    └─ Save: packages/grouping/group_manifest.json

STEP 7: User Review (REQUIRED)
    └─ User reviews all groups
    └─ User can: Accept, Regenerate, Split, Merge, Reorder, Manual Assign
    └─ User clicks "Confirm" to proceed
```

### APP3 Review Workflow (User Intervention Required)

```
After APP3 completes automatic grouping:

USER REVIEW OPTIONS:
    ├─ Accept
    │   └─ Group is correct. No changes.
    │
    ├─ Regenerate
    │   └─ Regenerate this group from scratch
    │   └─ Apply new matching criteria
    │
    ├─ Split Group
    │   └─ Split one group into two groups
    │   └─ User selects split point
    │
    ├─ Merge Group
    │   └─ Merge two groups into one
    │   └─ User selects groups to merge
    │
    ├─ Reorder Group
    │   └─ Reorder scenes within a group
    │   └─ Drag-and-drop scene order
    │
    └─ Manual Assign Scene
        └─ Manually add/remove scene from group
        └─ Override automatic assignment

AFTER ALL REVIEWS:
    User clicks: "Confirm Groups"
    └─ Save revised grouping
    └─ Update group_manifest.json
    └─ Unlock APP4 trigger
```

### APP3 Output

```
output/<project>/packages/
└── grouping/
    ├── group_0001.json
    ├── group_0002.json
    └── group_manifest.json
```

### APP3 Checkpoint

```
output/<project>/.state/
└── app3_checkpoint.json
    ├── last_group_processed: "group_0015"
    ├── total_groups: 20
    ├── processed_groups: 15
    └── failed_groups: 0
```

### APP3 User Trigger

```
APP3 does NOT auto-transition to APP4.

After user review + confirm:
    1. Grouping is finalized
    2. User clicks "Start Reconstruction"
    3. APP4 begins
```

---

## 7. APP4: RECONSTRUCTION

### Overview

```
APP4 = Reconstruction
    └─ Cuts video clips based on groups
    └─ Output organized by Scene ID (not by clip number)
    └─ Final output. NO separate Export Phase.
```

### APP4 Output Structure (Scene ID Based)

```
output/<project>/final/
├── final_manifest.json              ← Master manifest
├── reconstruction_report.json        ← Processing report
│
├── 0001/                             ← Group ID folder
│   ├── scene_src_0008.mp4            ← Scene ID preserved
│   ├── scene_src_0012.mp4            ← Scene ID preserved
│   └── scene_src_0015.mp4            ← Scene ID preserved
│
├── 0002/                             ← Group ID folder
│   ├── scene_src_0020.mp4
│   └── scene_src_0021.mp4
│
└── 0003/
    └── ...
```

### APP4 Workflow

```
STEP 1: Load Grouping Data
    └─ Load from: packages/grouping/
    └─ Load from: packages/analysis/

STEP 2: Load Source
    └─ Load from: source/source_reconstruction_map.json
    └─ Load source video

STEP 3: For Each Group
    └─ For each scene in group:
        └─ Identify video segment from reconstruction_map
        └─ Cut clip using segment timestamps
        └─ Validate output clip
    └─ Save clips to: final/{group_id}/

STEP 4: Generate Manifests
    └─ Build final_manifest.json
    └─ Build reconstruction_report.json

STEP 5: Session Complete
    └─ MP4 files exist
    └─ No further export step needed
```

### APP4 Final Manifest Schema

```json
{
  "manifest_version": "1.0",
  "project": "naruto_review_v2",
  "total_groups": 20,
  "total_clips": 45,
  "groups": [
    {
      "group_id": "0001",
      "scenes": [
        {
          "scene_id": "scene_src_0008",
          "file": "scene_src_0008.mp4",
          "start": "00:01:30",
          "end": "00:02:15"
        },
        {
          "scene_id": "scene_src_0012",
          "file": "scene_src_0012.mp4",
          "start": "00:03:20",
          "end": "00:04:00"
        }
      ],
      "output_path": "final/0001/"
    }
  ],
  "created_at": "2026-06-01T12:45:00Z"
}
```

### APP4 Checkpoint

```
output/<project>/.state/
└── app4_checkpoint.json
    ├── last_group_processed: "00015"
    ├── total_groups: 20
    ├── processed_groups: 18
    └── failed_groups: 0
```

---

## 8. CHECKPOINT RULES

### Checkpoint Locations

```
output/<project>/
├── .state/
│   ├── app1_checkpoint.json
│   ├── app2_checkpoint.json
│   ├── app3_checkpoint.json
│   └── app4_checkpoint.json
└── session.json
```

### When Checkpoints are Saved

| APP | Trigger |
|---|---|
| APP1 | After each step: detect, review, profile save, generate |
| APP2 | After each scene processed |
| APP3 | After each group validated |
| APP4 | After each group cut |

### Checkpoint Contents

```json
{
  "app": "app2",
  "checkpoint_version": "1.0",
  "last_step": "scene_processed",
  "last_scene_id": "scene_src_0023",
  "total": 50,
  "completed": 23,
  "failed": 1,
  "failed_ids": ["scene_src_0015"],
  "timestamp": "2026-06-01T12:30:00Z"
}
```

### Resume Behavior

```
On APP re-run:
    1. Load checkpoint
    2. Identify last incomplete unit
    3. Process from checkpoint forward
    4. Do NOT re-process completed units
    5. Overwrite failed units
```

### Checkpoint Clearing

```
Checkpoint is cleared when:
    └─ User explicitly re-runs from start
    └─ User deletes project
    └─ Project status changes to "archived"
```

---

## 9. RETRY RULES

### Retry Levels

| Level | Scope | Max Attempts | Behavior on Fail |
|---|---|---|---|
| **Scene** | APP2 single scene | 3 | Skip scene, log, continue |
| **Group** | APP3 single group | 3 | Skip group, log, continue |
| **Clip** | APP4 single clip | 2 | Skip clip, log, continue |
| **Project** | Entire APP | 0 | User must intervene |

### Retry Flow (APP2 Example)

```
process_scene(scene_id):
    attempt = 0
    while attempt < max_attempts:
        try:
            result = analyze(scene_id)
            save(result)
            return SUCCESS
        except ProviderError:
            attempt += 1
            if attempt < max_attempts:
                wait(backoff * attempt)  # 2s, 4s, 8s
                continue
            else:
                mark_failed(scene_id)
                log_error(f"Scene {scene_id} failed after {max_attempts} attempts")
                return FAIL
        except ValidationError:
            mark_failed(scene_id)
            log_error(f"Scene {scene_id} validation failed")
            return FAIL
```

### Retry Backoff

```
Attempt 1 fail → wait 2 seconds
Attempt 2 fail → wait 4 seconds
Attempt 3 fail → skip, continue
```

### Error Reporting

```
After APP completes:
    Report summary:
        └─ Total scenes: 50
        └─ Successful: 48
        └─ Failed: 2
        └─ Failed IDs: [scene_src_0015, scene_src_0032]

User can:
    ├─ Review failed scenes
    ├─ Fix issue
    └─ Re-run only failed scenes
```

---

## 10. BATCH RULES

### Batch Support by APP

| APP | Batch? | Detail |
|---|---|---|
| APP1 | ❌ | Single video per project |
| APP2 | ✅ | Batch scenes within project |
| APP3 | ✅ | Batch groups within project |
| APP4 | ✅ | Batch clips within project |

### APP2 Batch Processing

```
Queue: [scene_src_0001, scene_src_0002, ..., scene_src_0050]
Workers: concurrent (max_workers = config.default: 2)

Processing:
    ├─ Worker 1: process(scene_src_0001), process(scene_src_0003), ...
    └─ Worker 2: process(scene_src_0002), process(scene_src_0004), ...

Checkpoint: after each scene
```

### APP3 Batch Processing

```
Queue: [group_0001, group_0002, ..., group_0020]
Processing: sequential (matcher + scorer per group)

Checkpoint: after each group
```

### APP4 Batch Processing

```
Queue: [group_0001, group_0002, ..., group_0020]
Processing: sequential (cutter per group)

Checkpoint: after each group
```

### No Cross-Project Batch

```
Batch is always within ONE project.
No parallel processing of multiple projects.
```

---

## 11. USER INTERVENTION RULES

### Automatic Steps (No User Input)

```
APP1: Detect scenes
APP2: Build prompts (automatic)
APP2: Call AI provider (automatic)
APP3: Match scenes (automatic)
APP3: Score groups (automatic)
APP4: Cut clips (automatic)
```

### User-Triggered Steps

| Step | Trigger | Required? |
|---|---|---|
| Create project | User | Yes |
| Select video | User | Yes |
| Review Intro/Outro (APP1) | User | Yes |
| Confirm packages (APP1) | User | Yes |
| Trigger APP2 | User | Yes |
| Select test scene (APP2) | User | For Single Mode |
| Review single scene output | User | For Single Mode |
| Edit prompt (APP2) | User | Optional |
| Trigger batch (APP2) | User | Yes |
| Review groups (APP3) | User | Yes |
| Confirm groups (APP3) | User | Yes |
| Trigger APP4 | User | Yes |
| Export final | User | Yes |

### APP1 User Loop

```
APP1 workflow requires USER input:

Load Video → Detect Scenes → User Review → Save Profile → Generate Package
                                              ↓
                                    User MUST:
                                    - View detected scenes
                                    - Select Intro scenes
                                    - Select Outro scenes
                                    - Click "Save Profile"
                                    - Click "Generate Package"
                                              ↓
                                    APP1 pauses until user confirms
```

### APP2 User Loop

```
APP2 has TWO modes:

MODE 1: Single Scene Test (prompt tuning)
    Select Scene → Build Prompt → Run → Review → Edit Prompt → Re-run
    ↑_______________________________________________|
    Loop until satisfied
    Then: User clicks "Run Batch"

MODE 2: Batch Mode
    User clicks "Run Batch" → Full auto → Report on completion
```

### APP3 User Loop

```
APP3 requires USER review:

Automatic grouping complete
    ↓
User reviews each group
    ├─ Accept
    ├─ Regenerate
    ├─ Split
    ├─ Merge
    ├─ Reorder
    └─ Manual Assign
    ↓
User clicks "Confirm Groups"
    ↓
APP3 unlocks APP4 trigger
```

---

## 12. ERROR RECOVERY RULES

### Error Types and Recovery

| Error | Detection | Recovery |
|---|---|---|
| **Provider timeout** | API call fails | Retry 3x with backoff, then skip scene |
| **Provider error** | API returns error | Switch fallback provider if available |
| **Validation fail** | Output doesn't match schema | Skip scene, log, continue |
| **Scene overlap** | APP3 duplicate scene detection | Flag for user review |
| **Cut fail** | Video cut fails | Retry 2x, then skip clip |
| **Disk full** | Storage write fails | STOP all, notify user |
| **Checkpoint corrupt** | Load checkpoint fails | Reset to start of APP |

### Provider Error Flow

```
Provider fails:
    1. Log error to logs/
    2. Check fallback provider in config
    3. Switch provider
    4. Retry scene
    5. If all providers fail → skip scene

Fallback provider priority:
    config/providers/default.json → active_provider
    config/providers/ollama.json → fallback_1
    config/providers/openai.json → fallback_2
```

### Checkpoint Corruption Flow

```
Load checkpoint fails:
    1. Log error
    2. Check for backup checkpoint
    3. If backup exists → load backup
    4. If no backup → prompt user:
        ├─ "Reset APP to start"
        └─ "Cancel"
```

### Disk Full Flow

```
Storage write fails:
    1. STOP all workers
    2. Save current state if possible
    3. Log error
    4. Notify user: "Disk full. Please free space."
    5. User frees space
    6. User resumes from checkpoint
```

---

## 13. OUTPUT COMPLETION RULES

### Project Complete Definition

```
Project is COMPLETE when:
    1. All 4 APPs have run
    2. APP1: source/ complete
    3. APP2: packages/analysis/ complete
    4. APP3: packages/grouping/ complete
    5. APP4: final/ contains MP4 files
    6. final/final_manifest.json exists
    7. session.json status = "complete"
```

### Completion Checklist

```
[ ] session.json status = "complete"
[ ] source/source_reconstruction_map.json exists
[ ] source/source_master_timeline.json exists
[ ] packages/analysis/scene_src_XXXX.json for all scenes
[ ] packages/grouping/group_manifest.json exists
[ ] final/final_manifest.json exists
[ ] final/ contains MP4 files (organized by Scene ID)
[ ] reconstruction_report.json exists
```

### Final Output Structure

```
output/naruto_review_v2/
├── session.json                  ← status: "complete"
├── source/
│   ├── source_reconstruction_map.json
│   ├── source_master_timeline.json
│   └── source_subtitles.json
├── packages/
│   ├── analysis/
│   │   ├── scene_src_0001.json
│   │   ├── scene_src_0002.json
│   │   └── ...
│   ├── grouping/
│   │   ├── group_0001.json
│   │   ├── group_0002.json
│   │   └── group_manifest.json
│   └── embeddings/
│       ├── scene_embeddings.json
│       └── metadata.json
└── final/
    ├── final_manifest.json
    ├── reconstruction_report.json
    ├── 0001/
    │   ├── scene_src_0008.mp4
    │   ├── scene_src_0012.mp4
    │   └── scene_src_0015.mp4
    ├── 0002/
    │   ├── scene_src_0020.mp4
    │   └── scene_src_0021.mp4
    └── ...
```

---

## 14. SUCCESS WORKFLOW (END-TO-END)

### Complete User Journey

```
═══════════════════════════════════════════════════════════════
STEP 0: USER OPENS APP
═══════════════════════════════════════════════════════════════
    └─ Load project list
    └─ Display recent projects

═══════════════════════════════════════════════════════════════
STEP 1: CREATE PROJECT
═══════════════════════════════════════════════════════════════
    User:
        ├─ Click "New Project"
        ├─ Set name: "naruto_review_v2"
        └─ Select video: naruto_ep1.mp4

    System:
        → Create: output/naruto_review_v2/
        → Create: session.json (status: "active")
        → Copy video reference

═══════════════════════════════════════════════════════════════
STEP 2: APP1 — VIDEO PACKAGING
═══════════════════════════════════════════════════════════════
    Load Video
        └─ Validate format
        └─ Extract metadata

    Load Subtitle
        └─ Auto-detect subtitle file
        └─ Parse into timeline

    Detect Scenes
        └─ Shot boundary detection
        └─ Extract keyframes
        └─ Generate scene list

    User Review Intro/Outro
        └─ User views detected scenes
        └─ User selects INTRO scenes (click to flag)
        └─ User selects OUTRO scenes (click to flag)
        └─ User clicks "Save Profile"

    Save Profile
        └─ Save: prompts_scene_analyzer/active_profile.json
        └─ Include: intro scenes, outro scenes

    Generate Packages
        └─ Export source/ output files
        └─ Display completion status

    [USER ACTION REQUIRED]
        └─ User clicks "Start Scene Analysis"

═══════════════════════════════════════════════════════════════
STEP 3: APP2 — SCENE ANALYSIS (SINGLE SCENE TEST MODE)
═══════════════════════════════════════════════════════════════
    User:
        └─ Select mode: "Single Scene Test"
        └─ Select scene: scene_src_0012

    Build Prompt (via Prompt Engine)
        └─ Load profile: anime_a
        └─ Load version: v1
        └─ Compose modules in order
        └─ Inject scene metadata

    Run Analysis
        └─ Call AI Provider (vision + text)
        └─ Receive analysis output

    Review Output
        └─ Display structured output
        └─ User reviews for correctness

    [USER DECISION]
        ├─ Output OK? → Go to Batch Mode
        └─ Output needs edit? → Edit Prompt → Re-run

    (Repeat Single Scene Test until prompt is stable)

═══════════════════════════════════════════════════════════════
STEP 4: APP2 — SCENE ANALYSIS (BATCH MODE)
═══════════════════════════════════════════════════════════════
    User:
        └─ Click "Run Batch Analysis"

    For each scene (scene_src_0001 to scene_src_0050):
        ├─ Build Final Prompt
        ├─ Call AI Provider
        ├─ Validate output
        ├─ Retry on failure (max 3)
        ├─ Save: packages/analysis/scene_src_XXXX.json
        └─ Update checkpoint

    Generate Embeddings
        └─ Create: packages/embeddings/scene_embeddings.json

    [USER ACTION REQUIRED]
        └─ User clicks "Start Grouping"

═══════════════════════════════════════════════════════════════
STEP 5: APP3 — GROUPING
═══════════════════════════════════════════════════════════════
    Load Analysis Data
        └─ Load: packages/analysis/
        └─ Load: packages/embeddings/

    Match Scenes
        └─ For each script chunk:
            └─ Match relevant scenes
            └─ Score matches

    Build Groups
        └─ Generate group files
        └─ Save: packages/grouping/

    [USER REVIEW (REQUIRED)]
        For each group:
            ├─ Accept
            ├─ Regenerate
            ├─ Split Group
            ├─ Merge Group
            ├─ Reorder Group
            └─ Manual Assign Scene

    User clicks "Confirm Groups"
        └─ Grouping finalized
        └─ Update group_manifest.json

    [USER ACTION REQUIRED]
        └─ User clicks "Start Reconstruction"

═══════════════════════════════════════════════════════════════
STEP 6: APP4 — RECONSTRUCTION
═══════════════════════════════════════════════════════════════
    Load Grouping Data
        └─ Load: packages/grouping/

    Load Source
        └─ Load: source/reconstruction_map.json

    For each group (0001, 0002, ...):
        For each scene in group:
            └─ Identify video segment
            └─ Cut clip
            └─ Save: final/{group_id}/scene_src_{XXXX}.mp4

    Generate Manifests
        └─ Create: final/final_manifest.json
        └─ Create: final/reconstruction_report.json

═══════════════════════════════════════════════════════════════
STEP 7: COMPLETE
═══════════════════════════════════════════════════════════════
    System:
        └─ session.json status = "complete"
        └─ completed_at = timestamp

    Output:
        output/naruto_review_v2/
        └── final/
            ├── final_manifest.json
            ├── reconstruction_report.json
            ├── 0001/
            │   ├── scene_src_0008.mp4
            │   ├── scene_src_0012.mp4
            │   └── scene_src_0015.mp4
            ├── 0002/
            │   ├── scene_src_0020.mp4
            │   └── scene_src_0021.mp4
            └── ...

═══════════════════════════════════════════════════════════════
USER DONE
═══════════════════════════════════════════════════════════════
    └─ MP4 files organized by Scene ID ready
    └─ No further export step needed
    └─ Open final/ folder to access files
```

---

## 15. STATE MACHINE

### Project State Transitions

```
created
    │
    └──→ active (APP1 starts)
              │
              ├──→ paused (user interrupt)
              │         │
              │         └──→ active (resume)
              │
              └──→ complete (APP4 done)
                        │
                        └──→ archived (user archive)

Any state can transition to: paused (on user interrupt)
Paused can transition to: active (resume)
```

### Session State Transitions

```
created
    │
    └──→ app1_in_progress
              │
              └──→ app1_complete
                        │
                        └──→ app2_in_progress
                                  │
                                  ├──→ paused
                                  │
                                  └──→ app2_complete
                                            │
                                            └──→ app3_in_progress
                                                      │
                                                      ├──→ paused
                                                      │
                                                      └──→ app3_complete
                                                                │
                                                                └──→ app4_in_progress
                                                                          │
                                                                          └──→ app4_complete
                                                                                    │
                                                                                    └──→ complete
```

---

## 16. ERROR SCENARIOS

### Scenario: APP2 Scene Fails

```
Scene src_0015 fails after 3 retries:
    1. Log error to logs/app2/
    2. Mark scene as failed in checkpoint
    3. Continue to next scene
    4. At end: display failed scenes list

User options:
    ├─ Review failed scene
    ├─ Fix prompt
    └─ Re-run failed scenes only
```

### Scenario: APP3 Group Confidence Low

```
Group 0005 confidence below threshold:
    1. Flag group for review
    2. Continue processing other groups
    3. At end: highlight low-confidence groups

User options:
    ├─ Accept low-confidence group
    ├─ Regenerate group
    ├─ Manual edit
    └─ Split group
```

### Scenario: APP4 Cut Fails

```
Clip cut fails:
    1. Retry 2 times
    2. If still fails: skip clip
    3. Log to reconstruction_report.json
    4. Continue to next clip

User options:
    ├─ Review failed clips
    └─ Re-run APP4 on failed clips only
```

### Scenario: Provider Down

```
Provider API unreachable:
    1. Log error
    2. Try fallback provider (if configured)
    3. If fallback works: continue
    4. If all providers fail: pause APP2
    5. Notify user: "All providers unavailable"

User options:
    ├─ Wait for provider recovery
    ├─ Switch provider manually
    └─ Cancel and retry later
```

---

## 17. SUMMARY: USER TRIGGER POINTS

### Manual Trigger Points (User Must Act)

| # | Trigger | Action |
|---|---|---|
| 1 | After APP1 packages | Click "Start Scene Analysis" |
| 2 | APP2 Single Mode | Click "Run Batch Analysis" after tuning |
| 3 | After APP2 batch | Click "Start Grouping" |
| 4 | APP3 review | Click "Confirm Groups" after review |
| 5 | After APP3 confirm | Click "Start Reconstruction" |

### No Auto-Transition Between APPs

```
APP1 → APP2: USER TRIGGER
APP2 → APP3: USER TRIGGER
APP3 → APP4: USER TRIGGER

No automatic transition. User must confirm and trigger each step.
```

---

*End of EXECUTION_WORKFLOW.md*