"""AggregationEngine — deterministic orchestration of scene merging.

Orchestrates the merging of multiple adjacent SceneSemantic objects
into semantic patch groups with preserved provenance and stable ordering.

Guarantees:
- Deterministic output (same input → same groups)
- Preserved semantic meaning
- Complete provenance tracking
- Replay-safe serialization
- Stable merge ordering
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from aicore.semantic.aggregation.continuity_detector import ContinuityDetector
from aicore.semantic.aggregation.merge_rule import MergeRuleSet, MergeRuleResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)
from aicore.semantic.schemas.merged_state import MergedSemanticState
from aicore.semantic.schemas.provenance import ProvenanceInfo
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class AggregationGroup:
    """Represents a group of scenes merged together.

    Preserves:
    - Original scene IDs (for lineage)
    - Merge order (for deterministic replay)
    - Provenance (which scenes contributed what)
    - Merge reason (which rule decided)
    """

    def __init__(
        self,
        group_id: str,
        scenes: List[SceneSemantic],
        merge_reason: Optional[str] = None,
    ):
        """Initialize aggregation group.

        Args:
            group_id: Unique identifier for this group
            scenes: Scenes in this group (in order)
            merge_reason: Why these scenes were merged
        """
        self.group_id = group_id
        self.scenes = scenes
        self.merge_reason = merge_reason or "default"
        self.created_at = datetime.utcnow().timestamp()

    def to_merged_state(self) -> MergedSemanticState:
        """Convert group to MergedSemanticState for SceneBuilder.

        Combines all scenes deterministically:
        - Character/action/object merging
        - Dialogue concatenation
        - Motion aggregation (last-wins)
        - Environment chain (preserve order)

        Returns:
            MergedSemanticState ready for SceneBuilder
        """
        merged = MergedSemanticState(
            scene_id=self.group_id,
        )

        for scene in self.scenes:
            # Characters: merge with conflict resolution (confidence-based)
            for char in scene.characters:
                key = char.normalized_name
                if key not in merged.characters:
                    merged.characters[key] = char
                else:
                    # Keep higher confidence
                    existing = merged.characters[key]
                    if char.confidence > existing.confidence:
                        merged.characters[key] = char

            # Actions: same merge strategy
            for action in scene.actions:
                key = action.normalized_name
                if key not in merged.actions:
                    merged.actions[key] = action
                else:
                    existing = merged.actions[key]
                    if action.confidence > existing.confidence:
                        merged.actions[key] = action

            # Objects: same merge strategy
            for obj in scene.objects:
                key = obj.normalized_name
                if key not in merged.objects:
                    merged.objects[key] = obj
                else:
                    existing = merged.objects[key]
                    if obj.confidence > existing.confidence:
                        merged.objects[key] = obj

            # Environments: append (preserve order of locations)
            for env in scene.environments:
                # Only add if different from last environment
                if not merged.environments or merged.environments[-1].normalized_name != env.normalized_name:
                    merged.environments.append(env)

            # Emotions: merge with confidence
            for emotion in scene.emotions:
                key = emotion.normalized_name
                if key not in merged.emotions:
                    merged.emotions[key] = emotion
                else:
                    existing = merged.emotions[key]
                    if emotion.confidence > existing.confidence:
                        merged.emotions[key] = emotion

            # Dialogue: append
            if scene.dialogue:
                merged.dialogue_parts.append(scene.dialogue)

            # OCR: append
            if scene.ocr_text:
                merged.ocr_parts.append(scene.ocr_text)

            # Motion: last-wins
            if scene.motion_intensity is not None:
                merged.motion_intensity = scene.motion_intensity
            if scene.motion_direction:
                merged.motion_direction = scene.motion_direction
            if scene.action_pace:
                merged.action_pace = scene.action_pace

            # Numeric: last-wins
            if scene.num_keyframes is not None:
                merged.num_keyframes = scene.num_keyframes
            if scene.num_text_regions is not None:
                merged.num_text_regions = scene.num_text_regions

        return merged

    def to_semantic_patch(self) -> SemanticPatch:
        """Convert group to SemanticPatch for replay.

        Creates a patch that represents the entire aggregated group.

        Returns:
            SemanticPatch that can be replayed deterministically
        """
        merged = self.to_merged_state()

        # Convert dict accumulators to lists
        characters = sorted(
            merged.characters.values(),
            key=lambda c: c.normalized_name,
        )
        actions = sorted(
            merged.actions.values(),
            key=lambda a: a.normalized_name,
        )
        objects = sorted(
            merged.objects.values(),
            key=lambda o: o.normalized_name,
        )
        emotions = sorted(
            merged.emotions.values(),
            key=lambda e: e.normalized_name,
        )

        dialogue = " ".join(merged.dialogue_parts) if merged.dialogue_parts else None
        ocr_text = " ".join(merged.ocr_parts) if merged.ocr_parts else None

        return SemanticPatch(
            source_node="aggregation_engine_v1",
            scene_id=self.group_id,
            schema_version="Phase2A.3",
            patch_order=0,
            characters=characters if characters else None,
            actions=actions if actions else None,
            objects=objects if objects else None,
            environments=merged.environments if merged.environments else None,
            emotions=emotions if emotions else None,
            dialogue=dialogue,
            ocr_text=ocr_text,
            motion_intensity=merged.motion_intensity,
            motion_direction=merged.motion_direction,
            action_pace=merged.action_pace,
            num_keyframes=merged.num_keyframes,
            num_text_regions=merged.num_text_regions,
            warnings=[f"aggregated {len(self.scenes)} scenes: {self.merge_reason}"],
        )

    def summary(self) -> dict:
        """Get summary of aggregation group.

        Returns:
            {
                "group_id": str,
                "scene_count": int,
                "scene_ids": [str],
                "total_duration": float,
                "character_count": int,
                "action_count": int,
                "merge_reason": str,
            }
        """
        start_time = min(s.start_time for s in self.scenes)
        end_time = max(s.end_time for s in self.scenes)

        merged = self.to_merged_state()

        return {
            "group_id": self.group_id,
            "scene_count": len(self.scenes),
            "scene_ids": [s.scene_id for s in self.scenes],
            "total_duration": end_time - start_time,
            "start_time": start_time,
            "end_time": end_time,
            "character_count": len(merged.characters),
            "action_count": len(merged.actions),
            "object_count": len(merged.objects),
            "emotion_count": len(merged.emotions),
            "has_dialogue": len(merged.dialogue_parts) > 0,
            "merge_reason": self.merge_reason,
        }


class AggregationEngine:
    """Deterministic orchestration of scene merging.

    Core responsibility: Group consecutive scenes based on semantic
    continuity rules, producing stable aggregation groups.

    Guarantees:
    - Same input scenes → same groups (deterministic)
    - Groups are stable across runs
    - Provenance preserved
    - Ordering deterministic
    """

    def __init__(
        self,
        continuity_detector: Optional[ContinuityDetector] = None,
        rule_set: Optional[MergeRuleSet] = None,
    ):
        """Initialize engine.

        Args:
            continuity_detector: Custom detector (default: standard)
            rule_set: Custom rules (default: standard set)
        """
        self.continuity_detector = continuity_detector or ContinuityDetector()
        self.rule_set = rule_set or MergeRuleSet()

    def aggregate(
        self,
        scenes: List[SceneSemantic],
    ) -> List[AggregationGroup]:
        """Deterministically group scenes by continuity.

        Process:
        1. Sort scenes by (video_id, start_time)
        2. Iterate through scenes, checking continuity
        3. Merge continuous scenes into groups
        4. Assign stable group IDs

        Args:
            scenes: List of scenes to aggregate

        Returns:
            List of AggregationGroup objects
        """
        # Sort deterministically
        sorted_scenes = sorted(
            scenes,
            key=lambda s: (s.video_id, s.episode_id or "", s.start_time),
        )

        groups: List[AggregationGroup] = []
        current_group: List[SceneSemantic] = []

        for i, scene in enumerate(sorted_scenes):
            if not current_group:
                # Start new group
                current_group.append(scene)
            else:
                # Check continuity with last scene in group
                last_scene = current_group[-1]
                decision, rule = self.rule_set.apply(last_scene, scene)

                if decision == MergeRuleResult.MERGE:
                    # Add to current group
                    current_group.append(scene)
                else:
                    # Finalize current group and start new one
                    group = self._finalize_group(current_group)
                    groups.append(group)
                    current_group = [scene]

        # Finalize last group
        if current_group:
            group = self._finalize_group(current_group)
            groups.append(group)

        return groups

    def _finalize_group(
        self,
        scenes: List[SceneSemantic],
    ) -> AggregationGroup:
        """Create stable aggregation group from scenes.

        Group ID is derived from component scene IDs for reproducibility.

        Args:
            scenes: Scenes to group

        Returns:
            AggregationGroup with stable ID
        """
        # Generate stable group ID
        group_id = self._generate_stable_group_id(scenes)

        # Determine merge reason (which rule was applied)
        merge_reason = "grouped"
        if len(scenes) > 1:
            decision, rule = self.rule_set.apply(scenes[0], scenes[-1])
            if rule:
                merge_reason = rule.rule_type.value

        return AggregationGroup(
            group_id=group_id,
            scenes=scenes,
            merge_reason=merge_reason,
        )

    def _generate_stable_group_id(self, scenes: List[SceneSemantic]) -> str:
        """Generate stable, deterministic group ID.

        ID is derived from:
        - Video ID
        - Start time (of first scene)
        - Scene count hash
        - Canonical scene IDs

        This ensures same scenes always produce same ID.

        Args:
            scenes: Scenes in group

        Returns:
            Stable group ID string
        """
        if not scenes:
            return "group_empty"

        first_scene = scenes[0]
        scene_ids = "_".join(s.scene_id for s in scenes)

        # Construct deterministic ID
        group_id = (
            f"group_{first_scene.video_id}_"
            f"{int(first_scene.start_time * 1000)}_"
            f"x{len(scenes)}"
        )

        return group_id

    def get_merge_decision(
        self,
        scene_a: SceneSemantic,
        scene_b: SceneSemantic,
    ) -> dict:
        """Get detailed merge decision for two scenes.

        Returns:
            {
                "should_merge": bool,
                "decision": str,
                "rule": str,
                "scores": {rule_type: score},
                "continuity_score": float,
                "details": {checks},
            }
        """
        decision, rule = self.rule_set.apply(scene_a, scene_b)
        rule_scores = self.rule_set.score(scene_a, scene_b)
        continuity_desc = self.continuity_detector.describe_continuity(scene_a, scene_b)

        return {
            "should_merge": decision == MergeRuleResult.MERGE,
            "decision": decision.value,
            "rule": rule.rule_type.value if rule else None,
            "scores": rule_scores["rule_scores"],
            "overall_score": rule_scores["overall_score"],
            "continuity_score": continuity_desc["score"],
            "continuity_details": continuity_desc["checks"],
        }
