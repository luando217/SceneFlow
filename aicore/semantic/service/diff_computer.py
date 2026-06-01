"""DiffComputer — calculates semantic diffs between scene versions.

Produces structured comparison showing:
- Added/removed/modified entities
- Text changes
- Motion changes
- Change magnitude
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from aicore.semantic.schemas.scene_semantic import SceneSemantic
from aicore.semantic.schemas.semantic_diff import EntityChange, SemanticDiff, TextDiff


def compute_text_diff(text_a: str, text_b: str) -> Optional[TextDiff]:
    """Compute line-level diff between two texts.

    Returns:
        TextDiff or None if texts are identical
    """
    if text_a == text_b:
        return None

    lines_a = text_a.split("\n") if text_a else []
    lines_b = text_b.split("\n") if text_b else []

    added = [line for line in lines_b if line not in lines_a]
    removed = [line for line in lines_a if line not in lines_b]
    
    # Simplified modified detection (not line-by-line LCS)
    total = max(len(lines_a), len(lines_b))
    changed = len(added) + len(removed)
    change_pct = (changed / total * 100) if total > 0 else 0.0

    return TextDiff(
        text_a=text_a,
        text_b=text_b,
        lines_added=added,
        lines_removed=removed,
        lines_modified=[],  # Simplified: not computing line-by-line modifications
        total_lines_a=len(lines_a),
        total_lines_b=len(lines_b),
        line_change_percentage=change_pct,
    )


def compute_semantic_diff(
    scene_a: SceneSemantic,
    scene_b: SceneSemantic,
    version_a: str = "a",
    version_b: str = "b",
) -> SemanticDiff:
    """Compute structured diff between two semantic states.

    Args:
        scene_a: First scene
        scene_b: Second scene
        version_a: Label for first version
        version_b: Label for second version

    Returns:
        SemanticDiff describing all changes
    """
    assert scene_a.scene_id == scene_b.scene_id

    entity_changes: List[EntityChange] = []

    # ── Character diffing ─────────────────────────────────────────
    char_a_map = {c.normalized_name: c for c in scene_a.characters}
    char_b_map = {c.normalized_name: c for c in scene_b.characters}

    chars_added = 0
    for name, entity in char_b_map.items():
        if name not in char_a_map:
            entity_changes.append(
                EntityChange(
                    entity_type="character",
                    normalized_name=name,
                    change_type="added",
                    new_entity=entity.model_dump(),
                )
            )
            chars_added += 1

    chars_removed = 0
    for name, entity in char_a_map.items():
        if name not in char_b_map:
            entity_changes.append(
                EntityChange(
                    entity_type="character",
                    normalized_name=name,
                    change_type="removed",
                    old_entity=entity.model_dump(),
                )
            )
            chars_removed += 1

    chars_modified = 0
    for name in char_a_map:
        if name in char_b_map:
            old_entity = char_a_map[name]
            new_entity = char_b_map[name]

            if old_entity != new_entity:
                conf_delta = new_entity.confidence - old_entity.confidence
                prov_changed = (
                    old_entity.provenance.source != new_entity.provenance.source
                )

                entity_changes.append(
                    EntityChange(
                        entity_type="character",
                        normalized_name=name,
                        change_type="modified",
                        old_entity=old_entity.model_dump(),
                        new_entity=new_entity.model_dump(),
                        confidence_delta=conf_delta,
                        provenance_changed=prov_changed,
                    )
                )
                chars_modified += 1

    # ── Action diffing ───────────────────────────────────────────
    action_a_map = {a.normalized_name: a for a in scene_a.actions}
    action_b_map = {a.normalized_name: a for a in scene_b.actions}

    actions_added = sum(
        1 for name in action_b_map if name not in action_a_map
    )
    actions_removed = sum(
        1 for name in action_a_map if name not in action_b_map
    )
    actions_modified = sum(
        1 for name in action_a_map
        if name in action_b_map and action_a_map[name] != action_b_map[name]
    )

    # ── Object diffing ───────────────────────────────────────────
    obj_a_map = {o.normalized_name: o for o in scene_a.objects}
    obj_b_map = {o.normalized_name: o for o in scene_b.objects}

    objects_added = sum(1 for name in obj_b_map if name not in obj_a_map)
    objects_removed = sum(1 for name in obj_a_map if name not in obj_b_map)
    objects_modified = sum(
        1 for name in obj_a_map
        if name in obj_b_map and obj_a_map[name] != obj_b_map[name]
    )

    # ── Environment diffing ───────────────────────────────────────
    envs_added = len(scene_b.environments) - len(scene_a.environments)
    envs_added = max(0, envs_added)
    envs_removed = len(scene_a.environments) - len(scene_b.environments)
    envs_removed = max(0, envs_removed)

    # ── Emotion diffing ───────────────────────────────────────────
    emo_a_map = {e.normalized_name: e for e in scene_a.emotions}
    emo_b_map = {e.normalized_name: e for e in scene_b.emotions}

    emotions_added = sum(1 for name in emo_b_map if name not in emo_a_map)
    emotions_removed = sum(1 for name in emo_a_map if name not in emo_b_map)
    emotions_modified = sum(
        1 for name in emo_a_map
        if name in emo_b_map and emo_a_map[name] != emo_b_map[name]
    )

    # ── Text diffing ──────────────────────────────────────────────
    dialogue_diff = compute_text_diff(scene_a.dialogue, scene_b.dialogue)
    ocr_diff = compute_text_diff(scene_a.ocr_text, scene_b.ocr_text)

    # ── Motion diffing ────────────────────────────────────────────
    motion_intensity_changed = (
        scene_a.motion_intensity != scene_b.motion_intensity
    )
    motion_direction_changed = (
        scene_a.motion_direction != scene_b.motion_direction
    )
    action_pace_changed = (
        scene_a.action_pace != scene_b.action_pace
    )

    # ── Summary statistics ────────────────────────────────────────
    total_a = (
        len(scene_a.characters)
        + len(scene_a.actions)
        + len(scene_a.objects)
        + len(scene_a.environments)
        + len(scene_a.emotions)
    )
    total_b = (
        len(scene_b.characters)
        + len(scene_b.actions)
        + len(scene_b.objects)
        + len(scene_b.environments)
        + len(scene_b.emotions)
    )

    total_changes = (
        chars_added
        + chars_removed
        + chars_modified
        + actions_added
        + actions_removed
        + actions_modified
        + objects_added
        + objects_removed
        + objects_modified
        + envs_added
        + envs_removed
        + emotions_added
        + emotions_removed
        + emotions_modified
    )

    total_entities = max(total_a, total_b, 1)
    change_pct = (total_changes / total_entities * 100)

    is_empty = total_changes == 0

    # Determine severity
    if is_empty:
        severity = "none"
    elif change_pct < 10:
        severity = "minor"
    elif change_pct < 30:
        severity = "moderate"
    else:
        severity = "major"

    return SemanticDiff(
        scene_id=scene_a.scene_id,
        version_a=version_a,
        version_b=version_b,
        entity_changes=entity_changes,
        characters_added=chars_added,
        characters_removed=chars_removed,
        characters_modified=chars_modified,
        actions_added=actions_added,
        actions_removed=actions_removed,
        actions_modified=actions_modified,
        objects_added=objects_added,
        objects_removed=objects_removed,
        objects_modified=objects_modified,
        environments_added=envs_added,
        environments_removed=envs_removed,
        emotions_added=emotions_added,
        emotions_removed=emotions_removed,
        emotions_modified=emotions_modified,
        dialogue_diff=dialogue_diff,
        ocr_diff=ocr_diff,
        motion_intensity_a=scene_a.motion_intensity,
        motion_intensity_b=scene_b.motion_intensity,
        motion_intensity_changed=motion_intensity_changed,
        motion_direction_a=scene_a.motion_direction,
        motion_direction_b=scene_b.motion_direction,
        motion_direction_changed=motion_direction_changed,
        action_pace_a=scene_a.action_pace,
        action_pace_b=scene_b.action_pace,
        action_pace_changed=action_pace_changed,
        total_entities_a=total_a,
        total_entities_b=total_b,
        total_entity_changes=total_changes,
        entity_change_percentage=change_pct,
        is_empty=is_empty,
        change_severity=severity,
    )
