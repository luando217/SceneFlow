"""SemanticRetrievalIndex — deterministic retrieval index builder.

Builds immutable, deterministic retrieval indexes from SceneSemantic objects.

Architecture constraints:
- Deterministic only (same input → same output)
- frozen=True for all index entries
- extra="forbid" enforced
- Replay-safe behavior
- Stable serialization
- No hidden mutations
- No probabilistic logic
- No embeddings
- No vector DB

Phase: 3.1b — Deterministic Retrieval Index Builder
"""

from __future__ import annotations

import hashlib
import json
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
)

from aicore.semantic.contracts.index_schemas import (
    ActionIndex,
    CharacterIndex,
    ContinuityIndex,
    EnvironmentIndex,
    SceneIndex,
    SegmentIndex,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


# ============================================================================
# Constants
# ============================================================================

DIALOGUE_SNIPPET_MAX_LEN = 200
OCR_SNIPPET_MAX_LEN = 200
SCHEMA_VERSION = "Phase3.1b"


# ============================================================================
# Internal helpers
# ============================================================================


def _stable_hash(content: str) -> str:
    """Generate stable SHA-256 hex digest from string content.

    Args:
        content: String content to hash

    Returns:
        Fixed-length hex digest (64 chars)
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sorted_items(items: Sequence[str]) -> List[str]:
    """Return deterministically sorted list of items."""
    return sorted(items)


def _truncate_text(text: str, max_len: int) -> str:
    """Truncate text to max length for snippet storage."""
    if text is None:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len]


def _extract_normalized_names(
    entities: Sequence[Any],
) -> List[str]:
    """Extract normalized names from entity sequence."""
    names = []
    for entity in entities:
        if hasattr(entity, "normalized_name") and entity.normalized_name:
            names.append(entity.normalized_name.lower())
        elif hasattr(entity, "raw_name"):
            names.append(entity.raw_name.lower())
        elif hasattr(entity, "raw_action"):
            names.append(entity.raw_action.lower())
        elif hasattr(entity, "raw_environment"):
            names.append(entity.raw_environment.lower())
    return names


def _compute_scene_signature(scene: SceneSemantic) -> str:
    """Compute deterministic signature for a scene."""
    chars = sorted(_extract_normalized_names(scene.characters))
    acts = sorted(_extract_normalized_names(scene.actions))
    envs = sorted(_extract_normalized_names(scene.environments))

    content = (
        f"scene:{scene.scene_id}:"
        f"chars:{','.join(chars)}:"
        f"acts:{','.join(acts)}:"
        f"envs:{','.join(envs)}"
    )
    return _stable_hash(content)


# ============================================================================
# SemanticRetrievalIndex — main index container
# ============================================================================


class SemanticRetrievalIndex:
    """Immutable deterministic retrieval index container.

    Aggregates and indexes:
    - Scene indexes (per-scene)
    - Segment indexes (narrative segments)
    - Continuity indexes (continuity chains)
    - Character indexes (per-character aggregations)
    - Environment indexes (per-environment aggregations)
    - Action indexes (per-action aggregations)

    All indexes are frozen (immutable) and serializable.
    """

    def __init__(
        self,
        scene_indexes: Dict[str, SceneIndex],
        segment_indexes: Dict[str, SegmentIndex],
        continuity_indexes: Dict[str, ContinuityIndex],
        character_indexes: Dict[str, CharacterIndex],
        environment_indexes: Dict[str, EnvironmentIndex],
        action_indexes: Dict[str, ActionIndex],
        index_hash: str,
    ) -> None:
        self._scene_indexes = scene_indexes
        self._segment_indexes = segment_indexes
        self._continuity_indexes = continuity_indexes
        self._character_indexes = character_indexes
        self._environment_indexes = environment_indexes
        self._action_indexes = action_indexes
        self._index_hash = index_hash

    # ── Factory method ─────────────────────────────────────────────────────

    @classmethod
    def build_from_scenes(
        cls,
        scenes: List[SceneSemantic],
        include_empty: bool = False,
    ) -> SemanticRetrievalIndex:
        """Build retrieval indexes from SceneSemantic objects.

        Args:
            scenes: List of scene semantic objects to index
            include_empty: Include indexes with empty content

        Returns:
            Immutable SemanticRetrievalIndex
        """
        # Sort scenes deterministically by scene_id
        sorted_scenes = sorted(scenes, key=lambda s: s.scene_id)

        # Build scene indexes
        scene_indexes = cls._build_scene_indexes(sorted_scenes, include_empty)

        # Build character indexes
        character_indexes = cls._build_character_indexes(
            sorted_scenes, include_empty
        )

        # Build environment indexes
        environment_indexes = cls._build_environment_indexes(
            sorted_scenes, include_empty
        )

        # Build action indexes
        action_indexes = cls._build_action_indexes(
            sorted_scenes, include_empty
        )

        # Compute deterministic index hash
        index_hash = cls._compute_index_hash(
            scene_indexes,
            character_indexes,
            environment_indexes,
            action_indexes,
        )

        return cls(
            scene_indexes=scene_indexes,
            segment_indexes={},  # No segments without narrative segments
            continuity_indexes={},  # No continuity without explicit chain
            character_indexes=character_indexes,
            environment_indexes=environment_indexes,
            action_indexes=action_indexes,
            index_hash=index_hash,
        )

    # ── Scene index building ───────────────────────────────────────────────

    @classmethod
    def _build_scene_indexes(
        cls,
        scenes: Sequence[SceneSemantic],
        include_empty: bool,
    ) -> Dict[str, SceneIndex]:
        """Build scene index entries from scenes."""
        scene_indexes = {}

        for scene in scenes:
            # Extract normalized names for matching
            chars = _sorted_items(_extract_normalized_names(scene.characters))
            acts = _sorted_items(_extract_normalized_names(scene.actions))
            envs = _sorted_items(_extract_normalized_names(scene.environments))
            objs = _sorted_items(_extract_normalized_names(scene.objects))
            emos = _sorted_items(_extract_normalized_names(scene.emotions))

            # Extract tags from scene if present
            tags = _sorted_items(getattr(scene, "tags", []) or [])

            # Truncate dialogue and OCR
            dialogue = _truncate_text(scene.dialogue or "", DIALOGUE_SNIPPET_MAX_LEN)
            ocr_text = _truncate_text(scene.ocr_text or "", OCR_SNIPPET_MAX_LEN)

            # Determine action pace from scene
            action_pace = getattr(scene, "action_pace", "slow")

            # Determine motion intensity
            motion_intensity = getattr(scene, "motion_intensity", 0.0)

            # Narrative event type if present
            narrative_event_type = getattr(scene, "narrative_event_type", None)

            scene_index = SceneIndex(
                scene_id=scene.scene_id,
                video_id=scene.video_id,
                episode_id=scene.episode_id,
                start_time=scene.start_time,
                end_time=scene.end_time,
                duration=scene.duration,
                characters=chars,
                actions=acts,
                environments=envs,
                objects=objs,
                emotions=emos,
                tags=tags,
                dialogue_snippet=dialogue,
                ocr_snippet=ocr_text,
                motion_intensity=motion_intensity,
                action_pace=action_pace,
                narrative_event_type=narrative_event_type,
                schema_version=SCHEMA_VERSION,
            )

            # Include scene index (filter empty only if specified)
            if include_empty or (
                chars or acts or envs or objs or emos or dialogue or ocr_text
            ):
                scene_indexes[scene.scene_id] = scene_index

        return scene_indexes

    # ── Character index building ───────────────────────────────────────────

    @classmethod
    def _build_character_indexes(
        cls,
        scenes: Sequence[SceneSemantic],
        include_empty: bool,
    ) -> Dict[str, CharacterIndex]:
        """Build aggregated character indexes."""
        # Aggregate character data by normalized name
        char_data: Dict[str, Dict[str, Any]] = {}

        for scene in scenes:
            for char_entity in scene.characters:
                name = char_entity.normalized_name.lower()
                if name not in char_data:
                    char_data[name] = {
                        "scene_ids": [],
                        "first_appearance": float("inf"),
                        "last_appearance": 0.0,
                        "total_confidence": 0.0,
                        "confidence_count": 0,
                        "aliases": [],
                    }

                char_data[name]["scene_ids"].append(scene.scene_id)
                char_data[name]["first_appearance"] = min(
                    char_data[name]["first_appearance"], scene.start_time
                )
                char_data[name]["last_appearance"] = max(
                    char_data[name]["last_appearance"], scene.end_time
                )
                if hasattr(char_entity, "confidence"):
                    char_data[name]["total_confidence"] += char_entity.confidence
                    char_data[name]["confidence_count"] += 1

        # Build character indexes
        char_indexes = {}
        for name, data in char_data.items():
            scene_ids = _sorted_items(data["scene_ids"])

            # Calculate average confidence
            avg_confidence = (
                data["total_confidence"] / data["confidence_count"]
                if data["confidence_count"] > 0
                else 0.0
            )

            # Guard for missing first appearance
            first_app = data["first_appearance"]
            if first_app == float("inf"):
                first_app = 0.0

            char_index = CharacterIndex(
                normalized_name=name,
                aliases=_sorted_items(data["aliases"]),
                scene_ids=scene_ids,
                first_appearance=first_app,
                last_appearance=data["last_appearance"],
                appearance_count=len(scene_ids),
                average_confidence=avg_confidence,
                schema_version=SCHEMA_VERSION,
            )

            if include_empty or len(scene_ids) > 0:
                char_indexes[name] = char_index

        return char_indexes

    # ── Environment index building ─────────────────────────────────────────

    @classmethod
    def _build_environment_indexes(
        cls,
        scenes: Sequence[SceneSemantic],
        include_empty: bool,
    ) -> Dict[str, EnvironmentIndex]:
        """Build aggregated environment indexes."""
        env_data: Dict[str, Dict[str, Any]] = {}

        for scene in scenes:
            for env_entity in scene.environments:
                name = env_entity.normalized_name.lower()
                if name not in env_data:
                    env_data[name] = {
                        "scene_ids": [],
                        "total_confidence": 0.0,
                        "confidence_count": 0,
                    }

                env_data[name]["scene_ids"].append(scene.scene_id)
                if hasattr(env_entity, "confidence"):
                    env_data[name]["total_confidence"] += env_entity.confidence
                    env_data[name]["confidence_count"] += 1

        # Build environment indexes
        env_indexes = {}
        for name, data in env_data.items():
            scene_ids = _sorted_items(data["scene_ids"])

            avg_confidence = (
                data["total_confidence"] / data["confidence_count"]
                if data["confidence_count"] > 0
                else 0.0
            )

            env_index = EnvironmentIndex(
                normalized_name=name,
                location="unknown",
                time_of_day="unknown",
                weather="unknown",
                scene_ids=scene_ids,
                appearance_count=len(scene_ids),
                average_confidence=avg_confidence,
                schema_version=SCHEMA_VERSION,
            )

            if include_empty or len(scene_ids) > 0:
                env_indexes[name] = env_index

        return env_indexes

    # ── Action index building ───────────────────────────────────────────────

    @classmethod
    def _build_action_indexes(
        cls,
        scenes: Sequence[SceneSemantic],
        include_empty: bool,
    ) -> Dict[str, ActionIndex]:
        """Build aggregated action indexes with temporal ordering."""
        action_data: Dict[str, Dict[str, Any]] = {}

        # First pass: collect action data
        for scene in scenes:
            for action_entity in scene.actions:
                name = action_entity.normalized_name.lower()
                if name not in action_data:
                    action_data[name] = {
                        "scene_ids": [],  # Will be temporally sorted
                        "temporal_order": [],  # (start_time, scene_id)
                        "total_confidence": 0.0,
                        "confidence_count": 0,
                        "total_intensity": 0.0,
                        "intensity_count": 0,
                    }

                action_data[name]["temporal_order"].append(
                    (scene.start_time, scene.scene_id)
                )
                if hasattr(action_entity, "confidence"):
                    action_data[name]["total_confidence"] += action_entity.confidence
                    action_data[name]["confidence_count"] += 1
                if hasattr(action_entity, "intensity"):
                    action_data[name]["total_intensity"] += action_entity.intensity
                    action_data[name]["intensity_count"] += 1

        # Sort by temporal order and build scene_ids
        for name, data in action_data.items():
            # Sort by start_time for deterministic temporal ordering
            sorted_temporal = sorted(data["temporal_order"], key=lambda x: x[0])
            data["scene_ids"] = [sid for _, sid in sorted_temporal]

        # Build action indexes
        action_indexes = {}
        for name, data in action_data.items():
            scene_ids = data["scene_ids"]

            avg_confidence = (
                data["total_confidence"] / data["confidence_count"]
                if data["confidence_count"] > 0
                else 0.0
            )
            avg_intensity = (
                data["total_intensity"] / data["intensity_count"]
                if data["intensity_count"] > 0
                else 0.0
            )

            action_index = ActionIndex(
                normalized_name=name,
                scene_ids=scene_ids,
                appearance_count=len(scene_ids),
                average_intensity=avg_intensity,
                total_duration_frames=0,  # No frame data in semantic layer
                average_confidence=avg_confidence,
                schema_version=SCHEMA_VERSION,
            )

            if include_empty or len(scene_ids) > 0:
                action_indexes[name] = action_index

        return action_indexes

    # ── Hash computation ───────────────────────────────────────────────────

    @classmethod
    def _compute_index_hash(
        cls,
        scene_indexes: Dict[str, SceneIndex],
        character_indexes: Dict[str, CharacterIndex],
        environment_indexes: Dict[str, EnvironmentIndex],
        action_indexes: Dict[str, ActionIndex],
    ) -> str:
        """Compute deterministic hash of all indexes.
        
        Uses sorted keys and structural content only.
        """
        """Compute deterministic hash of all indexes."""
        parts = []

        # Scene signatures
        scene_sigs = []
        for sid in sorted(scene_indexes.keys()):
            scene_sigs.append(_compute_scene_signature(scene_indexes[sid]))
        parts.append(f"scenes:{len(scene_sigs)}")

        # Character count
        parts.append(f"chars:{len(character_indexes)}")

        # Environment count
        parts.append(f"envs:{len(environment_indexes)}")

        # Action count
        parts.append(f"actions:{len(action_indexes)}")

        content = "|".join(parts)
        return _stable_hash(f"retrieval_index_v1:{content}")

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def scene_indexes(self) -> Dict[str, SceneIndex]:
        """Get scene indexes (read-only)."""
        return self._scene_indexes

    @property
    def segment_indexes(self) -> Dict[str, SegmentIndex]:
        """Get segment indexes (read-only)."""
        return self._segment_indexes

    @property
    def continuity_indexes(self) -> Dict[str, ContinuityIndex]:
        """Get continuity indexes (read-only)."""
        return self._continuity_indexes

    @property
    def character_indexes(self) -> Dict[str, CharacterIndex]:
        """Get character indexes (read-only)."""
        return self._character_indexes

    @property
    def environment_indexes(self) -> Dict[str, EnvironmentIndex]:
        """Get environment indexes (read-only)."""
        return self._environment_indexes

    @property
    def action_indexes(self) -> Dict[str, ActionIndex]:
        """Get action indexes (read-only)."""
        return self._action_indexes

    @property
    def index_hash(self) -> str:
        """Get replay-safe deterministic index hash."""
        return self._index_hash

    @property
    def scene_count(self) -> int:
        """Number of scene indexes."""
        return len(self._scene_indexes)

    @property
    def segment_count(self) -> int:
        """Number of segment indexes."""
        return len(self._segment_indexes)

    @property
    def continuity_count(self) -> int:
        """Number of continuity indexes."""
        return len(self._continuity_indexes)

    @property
    def character_count(self) -> int:
        """Number of character indexes."""
        return len(self._character_indexes)

    @property
    def environment_count(self) -> int:
        """Number of environment indexes."""
        return len(self._environment_indexes)

    @property
    def action_count(self) -> int:
        """Number of action indexes."""
        return len(self._action_indexes)

    @property
    def total_indexes(self) -> int:
        """Total number of all index types."""
        return (
            self.scene_count
            + self.segment_count
            + self.continuity_count
            + self.character_count
            + self.environment_count
            + self.action_count
        )

    # ── Lookup helpers ────────────────────────────────────────────────────

    def get_scene(self, scene_id: str) -> Optional[SceneIndex]:
        """Get scene index by scene_id."""
        return self._scene_indexes.get(scene_id)

    def get_character(self, name: str) -> Optional[CharacterIndex]:
        """Get character index by normalized name."""
        return self._character_indexes.get(name.lower())

    def get_environment(self, name: str) -> Optional[EnvironmentIndex]:
        """Get environment index by normalized name."""
        return self._environment_indexes.get(name.lower())

    def get_action(self, name: str) -> Optional[ActionIndex]:
        """Get action index by normalized name."""
        return self._action_indexes.get(name.lower())

    def get_segment(self, segment_id: str) -> Optional[SegmentIndex]:
        """Get segment index by segment_id."""
        return self._segment_indexes.get(segment_id)

    def get_continuity(self, chain_id: str) -> Optional[ContinuityIndex]:
        """Get continuity index by chain_id."""
        return self._continuity_indexes.get(chain_id)

    # ── Serialization ─────────────────────────────────────────────────────

    def to_dict_deterministic(self) -> Dict[str, Any]:
        """Produce deterministic dict with sorted keys."""
        # Build index dicts for each type
        scene_dict = {
            sid: si.to_dict_deterministic()
            for sid, si in sorted(self._scene_indexes.items())
        }
        segment_dict = {
            seg_id: seg.to_dict_deterministic()
            for seg_id, seg in sorted(self._segment_indexes.items())
        }
        continuity_dict = {
            cid: ci.to_dict_deterministic()
            for cid, ci in sorted(self._continuity_indexes.items())
        }
        char_dict = {
            cname: ci.to_dict_deterministic()
            for cname, ci in sorted(self._character_indexes.items())
        }
        env_dict = {
            ename: ei.to_dict_deterministic()
            for ename, ei in sorted(self._environment_indexes.items())
        }
        action_dict = {
            aname: ai.to_dict_deterministic()
            for aname, ai in sorted(self._action_indexes.items())
        }

        # Sort all keys alphabetically for deterministic output
        data = {
            "action_count": self.action_count,
            "action_indexes": action_dict,
            "character_count": self.character_count,
            "character_indexes": char_dict,
            "continuity_count": self.continuity_count,
            "continuity_indexes": continuity_dict,
            "environment_count": self.environment_count,
            "environment_indexes": env_dict,
            "index_hash": self._index_hash,
            "scene_count": self.scene_count,
            "scene_indexes": scene_dict,
            "schema_version": SCHEMA_VERSION,
            "segment_count": self.segment_count,
            "segment_indexes": segment_dict,
            "total_indexes": self.total_indexes,
        }
        return data

    def to_json(self, indent: int = 2) -> str:
        """Produce deterministic JSON string."""
        return json.dumps(
            self.to_dict_deterministic(),
            indent=indent,
            default=str,
            sort_keys=True,
        )

    def __repr__(self) -> str:
        """Debug representation."""
        return (
            f"SemanticRetrievalIndex("
            f"scenes={self.scene_count}, "
            f"chars={self.character_count}, "
            f"envs={self.environment_count}, "
            f"actions={self.action_count}, "
            f"hash={self._index_hash[:16]}...)"
        )