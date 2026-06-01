# ARCHITECTURE RECOVERY AUDIT

**Date:** 2026-06-01 12:01  
**Repository:** F:\vibeCode\SceneFlow  
**Branch:** main  

---

## Audit Scope

Cross-check all 9 locked docs listed in `docs/MEMORY.md` against actual files on disk.

---

## FOUND (9/9)

All 9 locked architecture documents are present — but **not** in `docs/`. They exist in the **project root** (`F:\vibeCode\SceneFlow\`).

| # | File | Path | Size (bytes) | Modified |
|---|------|------|-------------|----------|
| 1 | PROJECT_VISION.md | `F:\vibeCode\SceneFlow\PROJECT_VISION.md` | 8,218 | 2026-06-01 11:53 |
| 2 | DATA_ARCHITECTURE.md | `F:\vibeCode\SceneFlow\DATA_ARCHITECTURE.md` | 23,721 | 2026-06-01 11:53 |
| 3 | SYSTEM_ARCHITECTURE.md | `F:\vibeCode\SceneFlow\SYSTEM_ARCHITECTURE.md` | 39,273 | 2026-06-01 11:53 |
| 4 | EXECUTION_WORKFLOW.md | `F:\vibeCode\SceneFlow\EXECUTION_WORKFLOW.md` | 37,396 | 2026-06-01 11:53 |
| 5 | PROMPT_ARCHITECTURE.md | `F:\vibeCode\SceneFlow\PROMPT_ARCHITECTURE.md` | 26,872 | 2026-06-01 11:53 |
| 6 | APP1_ARCHITECTURE.md | `F:\vibeCode\SceneFlow\APP1_ARCHITECTURE.md` | 5,525 | 2026-06-01 11:53 |
| 7 | GROUPING_ARCHITECTURE.md | `F:\vibeCode\SceneFlow\GROUPING_ARCHITECTURE.md` | 17,618 | 2026-06-01 11:53 |
| 8 | RECONSTRUCTION_ARCHITECTURE.md | `F:\vibeCode\SceneFlow\RECONSTRUCTION_ARCHITECTURE.md` | 17,489 | 2026-06-01 11:53 |
| 9 | GRILL_LOCK.md | `F:\vibeCode\SceneFlow\GRILL_LOCK.md` | 15,623 | 2026-06-01 11:53 |

---

## MISSING (9/9 in `docs/`)

The `docs/` folder contains only:

- `MEMORY.md`
- `trace_subtitle_loading.md`

None of the 9 locked docs exist inside `docs/`. They are all stranded in the **project root** instead.

---

## Issue

**MEMORY.md** claims these 9 documents are locked, but they are located at the repository root (`F:\vibeCode\SceneFlow\`) rather than in the standard `docs/` directory. This is a structural inconsistency (misplacement), not a loss — no files are missing from the repository.

---

## Recommendation

If the intent is for these files to reside in `docs/`, they should be relocated or symlinked. Otherwise, `MEMORY.md` should be updated to reflect the actual location (project root).

---

*Audit complete. No files were created, modified, or deleted.*