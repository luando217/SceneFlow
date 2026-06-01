# RB3 ARCHITECTURE MASTER — FINAL SOURCE OF TRUTH

**Version:** 3.2  
**Type:** Architecture Specification  
**Status:** LOCKED  
**Date:** 2026-05-29  
**Phase:** RB3.MERGE — Architecture Consolidation

---

## MANDATORY DECISIONS (LOCKED)

| # | Decision | Answer |
|---|----------|--------|
| 1 | Prompt System Global? | **YES** |
| 2 | Prompt System location? | `prompts_scene_analyzer/` ONLY |
| 3 | Prompt System inside output/? | **NO** |
| 4 | Prompt System inside package/? | **NO** |
| 5 | One Prompt System for all packages? | **YES** |
| 6 | Preview = Runtime? | **YES** |
| 7 | One Compiler? | **YES** |
| 8 | Unlimited Modules? | **YES** |
| 9 | Module = 1 .txt file? | **YES** |
| 10 | Profile owns modules? | **NO** |
| 11 | Profile owns STATE only? | **YES** |
| 12 | Profile STATE = order + enabled? | **YES** |
| 13 | Order comes from profile? | **YES** |
| 14 | CATEGORY_ORDER exists? | **NO** |
| 15 | MODULE_CATALOG.json exists? | **NO** |
| 16 | scene_id single source of truth? | **YES** |
| 17 | OUTPUT BLOCK contract? | **YES** |
| 18 | OUTPUT BLOCK marker locked? | **YES** |
| 19 | Batch = Same Compiler? | **YES** |
| 20 | One Compiler for all modes? | **YES** |
 
---

## GLOBAL PROMPT SYSTEM LOCATION

```
F:/vibeCode/anime-semantic-engine-phase-3.3-stable/
└── prompts_scene_analyzer/
    ├── modules/
    │   └── *.txt           # Module content files
    ├── profiles/
    │   └── *.json          # Profile state files
    └── active_profile.json # Current active profile reference
```

**RULE:** Prompt System exists in ONE location. It is GLOBAL. All packages reference this system.

**FORBIDDEN LOCATIONS:**
- `output/*/prompts_scene_analyzer/` — NO
- `output/*/packages/prompts_scene_analyzer/` — NO
- `output/*/analysis/prompts/` — NO
- `output/*/frames/prompts/` — NO
- `output/*/metadata/prompts/` — NO
- `source/prompts_scene_analyzer/` — NO
- `packages/*/prompts/` — NO
- `analysis/prompts/` — NO
- `frames/prompts/` — NO
- `metadata/prompts/` — NO

---

## SECTION 1: PROMPT MODULE ARCHITECTURE

### What is a Prompt Module?

A Prompt Module is a **plain text file** that contributes part of the final prompt for scene analysis.

### Module Definition

**ONE module = ONE .txt file**

```
Example modules:
├── scene_analysis_prompt.txt
├── context_memory_prompt.txt
├── character_ontology.txt
├── anime_rules.txt
├── output_schema.txt
├── custom_module.txt
└── ... (unlimited)
```

### Module Rules

1. **Plain text only** — No JSON, no YAML, no structured formats
2. **One file per module** — Simplicity
3. **No hardcoded names** — Users may create/rename/delete any .txt file
4. **No categories** — Modules are just files in the modules/ directory
5. **Flat structure** — modules/ contains .txt files only, no subdirectories

### User Module Operations

| Operation | Behavior |
|-----------|----------|
| Create | User may create unlimited .txt files |
| Delete | User may delete any .txt file |
| Rename | User may rename any .txt file |
| Duplicate | User may duplicate any .txt file |
| Enable | Module contributes to final prompt (in profile) |
| Disable | Module excluded from compilation (not in profile) |

### Module States

| State | Description |
|-------|-------------|
| `enabled` | Module in profile with `enabled: true` |
| `disabled` | Module not in profile or `enabled: false` |
| `missing` | Module deleted from filesystem but still in profile |

---

## SECTION 2: PROMPT STORAGE ARCHITECTURE

### Directory Structure

```
prompts_scene_analyzer/
│
├── modules/                     # Individual module files (.txt only)
│   ├── scene_analysis_prompt.txt
│   ├── context_memory_prompt.txt
│   ├── character_ontology.txt
│   ├── anime_rules.txt
│   ├── output_schema.txt
│   └── ... (any user-created .txt files)
│
├── profiles/                    # Profile state files
│   ├── anime_profile.json
│   ├── fast_profile.json
│   ├── debug_profile.json
│   └── ... (any user-created profiles)
│
└── active_profile.json          # Reference to current profile
```

### REMOVED FROM RB3.0

| Removed Item | Reason |
|--------------|--------|
| `MODULE_CATALOG.json` | Not needed — filesystem is the catalog |
| `VARIABLE_REGISTRY.json` | Not centralized — runtime only |
| `COMPILER_CONFIG.json` | Not needed — profile controls order |
| Category subdirectories | Not needed — flat structure |
| `AI_CONTRACT/` | Not needed — categories removed |
| `SCENE_ANALYSIS/` | Not needed — categories removed |
| `CHARACTER_RULES/` | Not needed — categories removed |
| `OUTPUT_SCHEMA/` | Not needed — categories removed |
| `CUSTOM/` | Not needed — categories removed |
| `FUTURE/` | Not needed — categories removed |

### Storage Rules

1. **Module files are .txt** — Plain text, simple
2. **One module per file** — No JSON, no structure
3. **No catalog** — Filesystem IS the catalog
4. **No category ordering** — Order comes from profile only
5. **Flat structure** — No subdirectories in modules/

---

## SECTION 3: PROFILE ARCHITECTURE

### Profile Owns STATE Only

**CRITICAL RULES:**

```
Profile owns STATE only.
STATE = module order + enabled state.
```

```
Profile does NOT own:
  - module content
  - module files
  - module definitions
  - variable syntax
  - merge separators
  - output schemas
```

```
Profile does NOT contain module content.
Profile does NOT define module structure.
Profile does NOT manage module files.
```

### Profile STATE Structure

```json
{
  "profile_id": "anime_profile",
  "name": "Anime Profile",
  "description": "Standard anime analysis profile",
  "modules": [
    {
      "filename": "scene_analysis_prompt.txt",
      "enabled": true
    },
    {
      "filename": "context_memory_prompt.txt",
      "enabled": true
    },
    {
      "filename": "character_ontology.txt",
      "enabled": true
    }
  ],
  "created_at": "2026-05-29T00:00:00Z",
  "updated_at": "2026-05-29T00:00:00Z"
}
```

### Profile Controls

| Control | Function |
|---------|----------|
| order | Module position in modules array determines compilation order |
| enable | Add entry with `enabled: true` to include in compilation |
| disable | Set `enabled: false` or remove entry to exclude from compilation |

### Profile States

| State | Description |
|-------|-------------|
| `active` | Used for compilation (referenced in active_profile.json) |
| `inactive` | Stored in profiles/ but not active |

---

## SECTION 4: ACTIVE PROFILE

### active_profile.json

```json
{
  "active_profile": "anime_profile",
  "updated_at": "2026-05-29T00:00:00Z"
}
```

### Purpose

Simply stores which profile is currently active.

---

## SECTION 5: COMPILER CONTRACT

### Single Compiler Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    COMPILER (SINGLE)                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  1. READ ACTIVE PROFILE                                  │
│     │                                                    │
│     ▼                                                    │
│  2. LOAD ENABLED MODULES FROM FILESYSTEM                 │
│     │                                                    │
│     ▼                                                    │
│  3. RESOLVE VARIABLES (runtime metadata provided)         │
│     │                                                    │
│     ▼                                                    │
│  4. MERGE IN PROFILE ORDER                               │
│     │                                                    │
│     ▼                                                    │
│  5. ATTACH RUNTIME METADATA                              │
│     │                                                    │
│     ▼                                                    │
│  6. RETURN FINAL PROMPT                                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### Compiler Does NOT Know

```
Compiler does NOT know:
├── AI Contract (if exists in modules)
├── Character Rules (if exists in modules)
├── Scene Analysis (if exists in modules)
├── Output Schema (if exists in modules)
├── Custom Modules (any modules)
├── Category Order (doesn't exist)
├── Dependency Graph (doesn't exist)
├── MODULE_CATALOG.json (doesn't exist)
├── VARIABLE_REGISTRY.json (doesn't exist)
└── Module Content (only reads filenames from profile)
```

### Compiler Contract

Compiler knows ONLY:
- Enabled modules (from profile.modules where enabled=true)
- Module order (from profile array order)
- Runtime metadata (scene_id, frame_path, etc.)

### REMOVED FROM RB3.0

| Removed Item | Reason |
|--------------|--------|
| Category ordering step | CATEGORY_ORDER doesn't exist |
| Dependency resolution | No module dependencies |
| Topological sort | Not needed without dependencies |
| Module validation against catalog | Not needed |

## SECTION 5B: BATCH CONTRACT

### Single Compiler for All Modes

**CRITICAL RULE:**
```
Single Scene and Multi Scene
MUST use the SAME compiler.

Mode is runtime input only.
```

### FORBIDDEN Structures

```
SingleCompiler      ← FORBIDDEN
BatchCompiler       ← FORBIDDEN
PreviewCompiler     ← FORBIDDEN
RuntimeCompiler     ← FORBIDDEN
```

### REQUIRED Structure

```
Compiler(mode)

One compiler only.
```

### Batch Compilation

```python
# CORRECT: Single compiler handles all modes
def compile(scene_ids: list[str], mode: str = "single") -> dict:
    """
    Single compiler entry point.
    Mode is input parameter only.
    """
    compiler = Compiler()
    
    if mode == "single":
        return compiler.compile_single(scene_ids[0])
    elif mode == "batch":
        return compiler.compile_batch(scene_ids)
    elif mode == "preview":
        return compiler.compile_single(scene_ids[0])
    
def compile_single(scene_id: str) -> dict:
    return Compiler().compile(scene_id)

def compile_batch(scene_ids: list[str]) -> dict:
    return Compiler().compile_batch(scene_ids)
```

### Batch vs Single

| Mode | Behavior |
|------|----------|
| `single` | Compile one scene, return one prompt |
| `batch` | Compile multiple scenes, return multiple prompts |
| `preview` | Compile one scene (alias for single) |

All modes use the same Compiler class.

### Output Schema Module is Optional

```
OUTPUT_BLOCK is mandatory.
Output Schema module is OPTIONAL.
```

Users may create an `output_schema.txt` module.
Users may delete it.
Users may replace it.
Users may ignore it entirely.

```
output_schema.txt — Optional content example:
  Return your response in this JSON format inside [OUTPUT_BLOCK]:
  {
    "scene_summary": "...",
    "characters": [...],
    "relationships": [...]
  }
```

**IMPORTANT:** `output_schema.txt` is a Prompt Module like any other.
- It is NOT required
- It is NOT special
- It does NOT have privileged compiler access
- It can be created, deleted, renamed, duplicated like any module
- It can be enabled/disabled per profile
- The system works without it

---

## SECTION 6: PREVIEW CONTRACT

### Hard Rule

```
Preview MUST EQUAL Runtime
```

### Implementation

```python
def get_prompt(scene_id: str, mode: str = "preview") -> dict:
    """
    Single entry point for both preview and runtime.
    Both modes return IDENTICAL output.
    """
    return compile(scene_id)

def preview(scene_id: str) -> dict:
    return compile(scene_id)

def runtime(scene_id: str) -> dict:
    return compile(scene_id)
```

### Preview Output Structure

```json
{
  "prompt": "merged prompt text from all enabled modules",
  "modules_used": ["scene_analysis_prompt.txt", "context_memory_prompt.txt"],
  "scene_id": "scene_src_0028",
  "profile_id": "anime_profile",
  "variables_resolved": {
    "scene_id": "scene_src_0028"
  },
  "preview_mode": true,
  "runtime_mode": true,
  "is_identical": true,
  "compiler_version": "3.2"
}
```

### NO Separate Builders

```
FORBIDDEN:
  - PreviewBuilder
  - RuntimeBuilder
  - PreviewCompiler
  - RuntimeCompiler
  - compile_preview()
  - compile_runtime()

REQUIRED:
  - Compiler (single)
  - compile() function (single entry point)
```

---

## SECTION 7: ORDERING CONTRACT

### Order Comes ONLY From Profile

**CRITICAL RULE:**
```
NO CATEGORY_ORDER.
NO hardcoded ordering.
NO implicit ordering.
USER ORDER = FINAL ORDER.
```

### How Ordering Works

```json
// profile.json
{
  "modules": [
    { "filename": "scene_analysis_prompt.txt", "enabled": true },
    { "filename": "context_memory_prompt.txt", "enabled": true },
    { "filename": "character_ontology.txt", "enabled": true }
  ]
}
```

Module at index 0 → First in final prompt
Module at index 1 → Second in final prompt
Module at index 2 → Third in final prompt

### Profile Ordering Operations

| Operation | What it does |
|-----------|--------------|
| Drag & Drop | Reorder entries in modules array |
| Move Up | Swap with previous entry |
| Move Down | Swap with next entry |
| Remove | Remove from modules array (not deleted from filesystem) |

---

## SECTION 8: SCENE IDENTITY CONTRACT

### Single Source of Truth

| Pattern | Status |
|---------|--------|
| `scene_src_XXXX` | **ONLY VALID** |
| `scene_src_XXXX.png` | **ONLY VALID** |
| `scene_src_XXXX.json` | **ONLY VALID** |

### Forbidden Patterns

| Pattern | Reason |
|---------|--------|
| `scene_uuid_*` | Not valid |
| `scene_hash_*` | Not valid |
| `scene_alias_*` | Not valid |
| `scene_<anything else>` | Not valid |

---

## SECTION 9: OUTPUT BLOCK CONTRACT (NEW HARD LOCK)

### Purpose

The OUTPUT BLOCK is the **only runtime contract** for downstream applications.

### The Contract

Prompt content may change.
Prompt modules may change.
Profile order may change.
Output schema may change.
Output fields may change.
Output structure inside the block may change.

HOWEVER:

Every Ollama response MUST contain exactly one machine-readable OUTPUT BLOCK.

The OUTPUT BLOCK is the only runtime contract.

### Downstream Rules

```
Downstream applications must read ONLY the OUTPUT BLOCK.

Downstream applications must NOT depend on:
├── scene_summary
├── characters
├── relationships
├── audio_context
├── subtitle_context
├── any specific field name
└── any specific output structure outside the block
```

### What IS Locked

```
OUTPUT_BLOCK container is locked.
```

### What IS NOT Locked

```
Content inside the OUTPUT BLOCK is NOT locked.
```

### Parser Contract

```
Parser must extract data ONLY from:
  [OUTPUT_BLOCK]
  ...content...
  [/OUTPUT_BLOCK]

Parser must ignore everything outside the OUTPUT_BLOCK.
```

### Save Contract

```
Save pipeline persists OUTPUT_BLOCK content only.

Downstream applications must read OUTPUT_BLOCK content only.
```

---

## SECTION 10: OUTPUT BLOCK MARKER LOCK (NEW HARD LOCK)

### Marker Format is Immutable

**LOCKED FORMAT:**

```
[OUTPUT_BLOCK]

...content...

[/OUTPUT_BLOCK]
```

### Required Usage

All future profiles MUST use these markers.
All future modules MUST use these markers.
All future prompt systems MUST use these markers.

### FORBIDDEN Formats

```
<OUTPUT>                  </OUTPUT>       ← FORBIDDEN
===OUTPUT===              ===/OUTPUT===   ← FORBIDDEN
===RESULT===              ===/RESULT===   ← FORBIDDEN
<result>                  </result>       ← FORBIDDEN
{ "output": ... }                             ← FORBIDDEN
Custom markers of any kind                   ← FORBIDDEN
Profile-specific markers                      ← FORBIDDEN
Module-specific markers                       ← FORBIDDEN
```

### Rationale

The marker format is a permanent runtime contract.
Downstream parsers rely on these exact strings.

---

## SECTION 11: PROMPT STORAGE LOCATION LOCK (NEW HARD LOCK)

### Location is Locked

```
prompts_scene_analyzer/
```

### Structure is Locked

```
prompts_scene_analyzer/
├── modules/
│   └── *.txt
├── profiles/
│   └── *.json
└── active_profile.json
```

### Forbidden

```
No module content inside output/         ← FORBIDDEN
No module content inside packages/        ← FORBIDDEN
No module content anywhere else          ← FORBIDDEN
```

---

## SECTION 12: FORBIDDEN STRUCTURES

### REMOVED FROM RB3.0

| Item | Status |
|------|--------|
| `modules.json` | **REMOVED** — Database-style storage |
| `MODULE_CATALOG.json` | **REMOVED** — Not needed |
| `CATEGORY_ORDER` | **REMOVED** — Order from profile only |
| `VARIABLE_REGISTRY.json` | **REMOVED** — Runtime only |
| `COMPILER_CONFIG.json` | **REMOVED** — Not needed |
| Category subdirectories | **REMOVED** — Flat structure only |
| AI_CONTRACT/ folder | **REMOVED** — Categories removed |
| SCENE_ANALYSIS/ folder | **REMOVED** — Categories removed |
| CHARACTER_RULES/ folder | **REMOVED** — Categories removed |
| OUTPUT_SCHEMA/ folder | **REMOVED** — Categories removed |
| CUSTOM/ folder | **REMOVED** — Categories removed |
| FUTURE/ folder | **REMOVED** — Categories removed |

### Prompt System Locations

| Location | Status |
|----------|--------|
| `prompts_scene_analyzer/` | **VALID** — Global only location |
| `output/*/prompts_scene_analyzer/` | **FORBIDDEN** |
| `output/*/packages/` | **FORBIDDEN** |
| `output/*/prompts/` | **FORBIDDEN** |
| `packages/*/prompts/` | **FORBIDDEN** |

### Module Storage

| Format | Status |
|--------|--------|
| `.txt` files | **VALID** |
| `.json` files (module content) | **FORBIDDEN** |
| `MODULE_CATALOG.json` | **FORBIDDEN** |
| Subdirectories in modules/ | **FORBIDDEN** |

### Compiler Structures

| Structure | Status |
|-----------|--------|
| Single Compiler | **VALID** |
| Category ordering | **FORBIDDEN** |
| Dependency resolution | **FORBIDDEN** |
| Topological sort | **FORBIDDEN** |
| MODULE_CATALOG.json lookup | **FORBIDDEN** |

### Scene Identity

| Pattern | Status |
|---------|--------|
| `scene_src_XXXX` | **VALID** |
| `scene_uuid_*` | **FORBIDDEN** |
| `scene_hash_*` | **FORBIDDEN** |
| `scene_alias_*` | **FORBIDDEN** |

---

## SECTION 13: ARCHITECTURE COMPARISON

### RB3.0 vs RB3.1.1 vs RB3 (MASTER)

| Aspect | RB3.0 | RB3.1.1 | RB3 MASTER |
|--------|-------|---------|------------|
| Module = | JSON data structure | .txt file | .txt file |
| Module storage | JSON files in subdirectories | Flat .txt files | Flat .txt files |
| Module catalog | MODULE_CATALOG.json | None | None |
| Category system | AI_CONTRACT, SCENE_ANALYSIS, etc. | None | None |
| Category ordering | Hardcoded CATEGORY_ORDER | None | None |
| Order source | Category priority | Profile array order | Profile array order |
| Profile owns | Everything (modules, order, settings) | Order and enabled state only | Order and enabled state only |
| Variable registry | Centralized VARIABLE_REGISTRY.json | Runtime only | Runtime only |
| Compiler knows | Categories, dependencies, order | Profile order only | Profile order only |
| OUTPUT BLOCK | Not specified | Not specified | **LOCKED** |
| OUTPUT BLOCK marker | Not specified | Not specified | **LOCKED** |

---

## SECTION 14: STORAGE LAYOUT SUMMARY

### FINAL STRUCTURE

```
prompts_scene_analyzer/
│
├── modules/                     # .txt files only
│   ├── scene_analysis_prompt.txt
│   ├── context_memory_prompt.txt
│   ├── character_ontology.txt
│   ├── anime_rules.txt
│   ├── output_schema.txt
│   └── ... (unlimited, user-created)
│
├── profiles/                    # Profile state only
│   ├── anime_profile.json
│   ├── fast_profile.json
│   ├── debug_profile.json
│   └── ... (user-created profiles)
│
└── active_profile.json          # Single reference file
```

### Profile JSON Structure

```json
{
  "profile_id": "string",
  "name": "string",
  "modules": [
    {
      "filename": "module_name.txt",
      "enabled": true/false
    }
  ],
  "settings": {}
}
```

---

## SECTION 15: SUCCESS CRITERIA

| Criteria | Status |
|----------|--------|
| Prompt System Global | ✅ YES |
| Prompt System outside output/ | ✅ YES |
| Prompt System outside packages/ | ✅ YES |
| Modules Unlimited | ✅ YES |
| Modules as .txt files | ✅ YES |
| Profiles Own State Only | ✅ YES |
| Compiler Count | ✅ 1 |
| Preview Equals Runtime | ✅ YES |
| scene_id Single Source of Truth | ✅ YES |
| OUTPUT BLOCK Contract | ✅ YES |
| OUTPUT BLOCK Marker Locked | ✅ YES |
| Package Contains Prompts | ❌ NO |
| Output Contains Prompts | ❌ NO |
| CATEGORY_ORDER | ❌ NO |
| MODULE_CATALOG.json | ❌ NO |
| modules.json | ❌ NO |
| Category subdirectories | ❌ NO |

---

## SUMMARY

### Architecture Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   prompts_scene_analyzer/          ← GLOBAL, SINGLE         │
│   │                                 ← ONE INSTANCE           │
│   │                                                       │
│   ├── modules/                     ← .TXT FILES ONLY         │
│   │   ├── *.txt                   ← UNLIMITED MODULES       │
│   │   └── ...                     ← NO CATEGORIES           │
│   │                                                       │
│   ├── profiles/                   ← PROFILE STATE ONLY      │
│   │   ├── *.json                  ← ORDER + ENABLED ONLY    │
│   │   └── ...                     ← NO MODULE CONTENT       │
│   │                                                       │
│   └── active_profile.json         ← SINGLE REFERENCE        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   output/                           ← PACKAGES               │
│   └── {package_name}/              ← MANY INSTANCES          │
│       ├── frames/                  ← RUNTIME DATA            │
│       ├── analysis/                ← RUNTIME DATA           │
│       ├── runtime_manifest.json    ← RUNTIME DATA            │
│       └── ...                      ← NO PROMPTS HERE         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Key Contracts

| Contract | Rule |
|----------|------|
| Single Source | scene_id is the only identity |
| Global Prompt System | prompts_scene_analyzer/ is global |
| One Compiler | Preview = Runtime |
| One-to-Many | One Prompt System, Many Packages |
| Single Identity | scene_id only, no UUID, no hash |
| Flat Modules | .txt files, no subdirectories |
| Profile State | Order and enabled only, no content |
| No Category Order | Order comes from profile only |
| OUTPUT BLOCK | Only runtime contract for downstream |
| OUTPUT BLOCK Marker | Immutable: `[OUTPUT_BLOCK]` / `[/OUTPUT_BLOCK]` |

---

**END OF ARCHITECTURE MASTER LOCK**