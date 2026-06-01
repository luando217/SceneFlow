# CONSISTENCY AUDIT REPORT

**Audit Date:** 2026-06-01
**Grill Session:** Q1-Q20
**Status:** COMPLETED

---

## Summary

| Item | Status | Path |
|------|--------|------|
| GRILL Q1-Q20 | ALL LOCKED | `docs/locks/GRILL_LOCK.md` |
| DATA_ARCHITECTURE.md | PATCHED (packages/frames → source/frames) | `docs/architecture/DATA_ARCHITECTURE.md` |
| APP1_ARCHITECTURE.md | PATCHED (packages/frames → source/frames) | `docs/architecture/APP1_ARCHITECTURE.md` |
| PROMPT_ARCHITECTURE.md | PATCHED (frames path + remove grouping_candidates) | `docs/architecture/PROMPT_ARCHITECTURE.md` |
| GRILL_LOCK.md | UPDATED | `docs/locks/GRILL_LOCK.md` |
| APP2_ARCHITECTURE.md | PENDING | — |

---

## Patches Applied

### 1. `DATA_ARCHITECTURE.md` — packages/frames → source/frames

**Reason:** GRILL 4, GRILL 11 — Contradiction resolved
**Files Changed:**
1. Section title: `### Output: frames/scene_src_XXXX.png` → `### Output: source/frames/scene_src_XXXX.png`
2. Location: `**Location:** `packages/frames/`` → `**Location:** `source/frames/``
3. APP2 Input reference: `frames/scene_src_XXXX.png` → `source/frames/scene_src_XXXX.png`
4. IMMUTABLE FIELD SUMMARY: `frames/scene_src_XXXX.png` → `source/frames/scene_src_XXXX.png`
5. DATA CONTRACT SUMMARY TABLE: `frames/scene_src_XXXX.png` → `source/frames/scene_src_XXXX.png`

### 2. `APP1_ARCHITECTURE.md` — packages/frames → source/frames

**Reason:** GRILL 4, GRILL 11 — Contradiction resolved
**Changes:**
1. Output structure: removed `packages/frames/` from tree
2. Frame Location note: `packages/frames/` → `source/frames/`

### 3. `PROMPT_ARCHITECTURE.md` — Multiple fixes

**Reason:** GRILL 11 (frames path), GRILL 15 (remove grouping_candidates)
**Changes:**
1. Section 6.1: `packages/.../0067.png` → `source/frames/.../0067.png`
2. Section 2.3: `matching_hints` description → "(confidence + temporal_context only)"
3. Section 2.5: Removed `grouping_candidates` from schema
4. Section 7.3: Removed `grouping_candidates` from matching_hints example
5. Section 7.1: `matching_hints` → `Grouping context` (removed "Grouping candidates" text)

---

## GRILL Decisions — Quick Reference

| GRILL | Topic | Decision | Status |
|-------|-------|----------|--------|
| 1 | APP1 AI Method | Traditional CV, no AI in APP1 | RESOLVED |
| 2 | Scene ID / script_chunk_id | scene_id immutable, no script_chunk_id at group level | RESOLVED |
| 3 | Reconstruction Ownership | APP1 owns reconstruction_map, APP4 is sole consumer | RESOLVED |
| 4 | Frames Location | `source/frames/` only, NOT `packages/frames/` | RESOLVED |
| 5 | User Review Loop | Batch accept + keyboard shortcuts, no auto-accept all | LOCKED |
| 6 | Checkpoint Recovery | Atomic write, backup before write, resume from output files | LOCKED |
| 7 | Missing Group Files | STOP immediately, no skip/auto-repair | LOCKED |
| 8 | APP4 Validation Depth | Collection mode, report all errors | LOCKED |
| 9 | APP2 Review Scope | Group level only, not per-scene | LOCKED |
| 10 | Grouping Mode | "review" = full scenes, no chunking in V1 | LOCKED |
| 11 | Frames Path Contradiction | Fixed in DATA_ARCHITECTURE.md | LOCKED |
| 12 | Output Path Root | Relative paths, base = `./output/<project>/` | LOCKED |
| 13 | Script Granularity | Default = sentence (1 sentence = 1 chunk) | LOCKED |
| 14 | Embeddings Ownership | APP2 = frame embeddings, APP3 = script embeddings | LOCKED |
| 15 | Matching Hints | REMOVE grouping_candidates from APP2 output | RESOLVED |
| 16 | Retry / Cost Control | Circuit breaker + fallback chain | LOCKED |
| 17 | Scene Count Metrics | Split into total_scene_references / total_unique_scenes | LOCKED |
| 18 | Final Output Scope | V1 = clips only, no merge/crossfade/render | LOCKED |
| 19 | Prompt Assembly | S_System + M_Metadata immutable, A-G configurable | LOCKED |
| 20 | Scene Reuse Waste | V1 accepts duplicate files, V2 optimization candidate | LOCKED |

---

## Pending Tasks

1. ⬜ APP2_ARCHITECTURE.md — Document APP2 generation (pending)

---

## Key Architectural Constraints

### Immutable Rules
- `scene_id` is source of truth xuyên pipeline
- APP1 owns scene boundaries, timestamps, frame_path
- APP2 only ADDS analysis fields, NEVER modifies APP1 fields
- APP3 only owns grouping logic, NOT APP2
- APP4 only reconstructs, NEVER analyzes
- S_System + M_Metadata always first in prompt

### Path Conventions
- Frame files: `source/frames/scene_src_XXXX.png`
- APP2 output: `packages/analysis/scene_src_XXXX.json`
- APP3 output: `packages/grouping/group_XXXX.json`
- APP4 output: `final/000X/scene_src_XXXX.mp4`

### Error Handling
- APP4 missing files = STOP (no skip)
- APP4 validation = COLLECTION mode (continue, report all)
- Checkpoint corruption = restore from backup, then user options
- APP2 failure = circuit breaker pauses workers

---

## Lock Enforcement

All GRILL decisions are IMMUTABLE.

Reopen ONLY if:
1. New contradiction detected
2. Missing contract discovered
3. Undefined ownership found
4. Undefined failure mode discovered

---

**END OF CONSISTENCY_AUDIT.md**