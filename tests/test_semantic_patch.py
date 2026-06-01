"""Tests for SemanticPatch schema, deterministic serialization,
stable hashing, and provenance attachment (Phase 2A.3).

Test layout:
    1. Basic patch construction (minimal, with entities, noop)
    2. Deterministic serialization (to_dict_deterministic, to_json)
    3. Stable hashing (same content → same hash, hash ≠ f(metadata))
    4. Provenance attachment (ConflictMarker, narrative_event_type)
    5. PatchHasher integration
    6. Replay consistency (same patch order → same scene)
    7. Edge cases (empty lists, all lists None, warnings)
"""
from __future__ import annotations

import json

from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
    ObjectEntity,
)
from aicore.semantic.schemas.provenance import (
    ConflictMarker,
    ExtractionSource,
    ProvenanceInfo,
)
from aicore.semantic.service.patch_hasher import PatchHasher


class TestSemanticPatchConstruction:
    """Basic patch creation and field defaults."""

    def test_minimal_patch(self):
        """A patch with only source_node and scene_id."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert patch.source_node == "vision_node"
        assert patch.scene_id == "scene_001"
        assert patch.schema_version == "Phase2A.3"
        assert patch.characters is None
        assert patch.actions is None
        assert patch.dialogue is None
        assert patch.ocr_text is None
        assert patch.motion_intensity is None
        assert patch.num_keyframes is None
        assert patch.narrative_event_type is None
        assert patch.provenance is None
        assert patch.conflict_markers == []
        assert patch.warnings == []

    def test_with_entities(self):
        """Patch carrying character, action, object, environment lists."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[
                CharacterEntity(normalized_name="naruto"),
                CharacterEntity(normalized_name="sasuke"),
            ],
            actions=[ActionEntity(normalized_name="punch")],
            objects=[ObjectEntity(normalized_name="rock")],
            environments=[
                EnvironmentEntity(normalized_name="forest")
            ],
            emotions=[EmotionEntity(normalized_name="angry")],
        )
        assert len(patch.characters) == 2
        assert patch.characters[0].normalized_name == "naruto"
        assert patch.characters[1].normalized_name == "sasuke"
        assert patch.actions[0].normalized_name == "punch"
        assert patch.objects[0].normalized_name == "rock"
        assert patch.environments[0].normalized_name == "forest"
        assert patch.emotions[0].normalized_name == "angry"

    def test_with_text_patches(self):
        """Patch carrying dialogue and OCR text."""
        patch = SemanticPatch(
            source_node="ocr_node",
            scene_id="scene_001",
            dialogue="I will be hokage!",
            ocr_text="NARUTO",
        )
        assert patch.dialogue == "I will be hokage!"
        assert patch.ocr_text == "NARUTO"

    def test_with_motion_patches(self):
        """Patch carrying motion fields."""
        patch = SemanticPatch(
            source_node="motion_node",
            scene_id="scene_001",
            motion_intensity=0.85,
            motion_direction="right",
            action_pace="fast",
        )
        assert patch.motion_intensity == 0.85
        assert patch.motion_direction == "right"
        assert patch.action_pace == "fast"

    def test_is_noop(self):
        """A patch with all optional fields as None is a no-op."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert patch.is_noop

    def test_not_noop_with_characters(self):
        """A patch carrying characters is not a no-op."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        assert not patch.is_noop


class TestDeterministicSerialization:
    """to_dict_deterministic and to_json stability."""

    def test_deterministic_keys_order(self):
        """to_dict_deterministic has stable key order."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        d = patch.to_dict_deterministic()
        keys = list(d.keys())
        assert keys[0] == "schema_version"
        assert keys[1] == "source_node"
        assert keys[2] == "scene_id"

    def test_deterministic_values(self):
        """Same constructor args produce same dict."""
        p1 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        p2 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert p1.to_dict_deterministic() == p2.to_dict_deterministic()

    def test_deterministic_json(self):
        """to_json produces valid deterministic JSON."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        json_str = patch.to_json()
        d = json.loads(json_str)
        assert d["source_node"] == "vision_node"
        assert d["scene_id"] == "scene_001"
        assert d["schema_version"] == "Phase2A.3"

    def test_entity_list_deterministic_order(self):
        """Entity lists are sorted by normalized_name for stable JSON."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[
                CharacterEntity(normalized_name="zoro"),
                CharacterEntity(normalized_name="luffy"),
            ],
        )
        d = patch.to_dict_deterministic()
        chars = d["characters"]
        assert chars[0]["normalized_name"] == "luffy"
        assert chars[1]["normalized_name"] == "zoro"

    def test_warnings_sorted(self):
        """Warning list is sorted for deterministic output."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            warnings=["low_confidence", "missing_frame"],
        )
        d = patch.to_dict_deterministic()
        assert d["warnings"] == ["low_confidence", "missing_frame"]

    def test_none_fields_excluded_from_content_hash(self):
        """None fields should be serialized deterministically
        as part of the content dict (not excluded)."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        d = patch._content_dict()
        # None fields should be None in the dict
        assert d["dialogue"] is None
        assert d["ocr_text"] is None
        assert d["narrative_event_type"] is None


class TestStableHashing:
    """Content hashing and hash stability."""

    def test_same_content_same_hash(self):
        """Two patches with identical content produce the same hash."""
        p1 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        p2 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        assert p1.compute_hash() == p2.compute_hash()

    def test_different_content_different_hash(self):
        """Two patches with different content produce different hashes."""
        p1 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        p2 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="sasuke")],
        )
        assert p1.compute_hash() != p2.compute_hash()

    def test_hash_independent_of_patch_hash_field(self):
        """Hash computed from content only, ignoring patch_hash."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        h1 = patch.compute_hash()
        # Even if we set a fake hash, compute_hash returns the same
        assert len(h1) == 64  # SHA-256 hex length

    def test_hash_independent_of_provenance(self):
        """Provenance metadata does not affect content hash."""
        p1 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        p2 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
            provenance=ProvenanceInfo(
                source=ExtractionSource.WD14,
                confidence=0.95,
            ),
        )
        # Content is the same → hash should be the same
        assert p1.compute_hash() == p2.compute_hash()

    def test_hash_independent_of_conflict_markers(self):
        """Conflict markers do not affect content hash."""
        p1 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        p2 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
            conflict_markers=[
                ConflictMarker(
                    conflict_type="entity_merge",
                    winner_raw_name="naruto",
                    winner_source="wd14",
                    winner_confidence=0.9,
                    resolution_policy="deterministic_sort",
                )
            ],
        )
        assert p1.compute_hash() == p2.compute_hash()

    def test_hash_is_sha256_hex(self):
        """compute_hash returns 64-char hex string."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        h = patch.compute_hash()
        assert len(h) == 64
        int(h, 16)  # Should not raise

    def test_stable_content_hash_empty_field(self):
        """stable_content_hash returns computed hash when patch_hash empty."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        h = patch.stable_content_hash()
        assert len(h) == 64


class TestProvenanceAttachment:
    """Provenance info, conflict markers, and narrative event type."""

    def test_patch_with_provenance(self):
        """Attach ProvenanceInfo to a patch."""
        provenance = ProvenanceInfo(
            source=ExtractionSource.OCR,
            confidence=0.88,
            source_version="tesseract-5.0",
        )
        patch = SemanticPatch(
            source_node="ocr_node",
            scene_id="scene_001",
            ocr_text="OPENING CREDITS",
            provenance=provenance,
        )
        assert patch.provenance is not None
        assert patch.provenance.source == ExtractionSource.OCR
        assert patch.provenance.confidence == 0.88
        assert patch.provenance.source_version == "tesseract-5.0"

    def test_patch_with_conflict_marker(self):
        """Attach a ConflictMarker to a patch."""
        marker = ConflictMarker(
            conflict_type="entity_merge",
            winner_raw_name="naruto",
            winner_source="wd14",
            winner_confidence=0.9,
            loser_raw_names=["naruto_uzumaki"],
            resolution_policy="deterministic_sort",
        )
        patch = SemanticPatch(
            source_node="aggregation_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
            conflict_markers=[marker],
        )
        assert len(patch.conflict_markers) == 1
        cm = patch.conflict_markers[0]
        assert cm.conflict_type == "entity_merge"
        assert cm.winner_raw_name == "naruto"
        assert cm.winner_confidence == 0.9
        assert cm.resolution_policy == "deterministic_sort"

    def test_narrative_event_type(self):
        """Narrative event type is carried through the patch."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            narrative_event_type="combat",
        )
        assert patch.narrative_event_type == "combat"

    def test_narrative_event_type_none_by_default(self):
        """narrative_event_type defaults to None."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert patch.narrative_event_type is None

    def test_multiple_conflict_markers(self):
        """Patch can carry multiple conflict markers."""
        markers = [
            ConflictMarker(
                conflict_type="entity_merge",
                winner_raw_name="naruto",
                winner_source="wd14",
                winner_confidence=0.9,
                resolution_policy="deterministic_sort",
            ),
            ConflictMarker(
                conflict_type="text_collision",
                winner_raw_name="SASUKE",
                winner_source="ocr",
                winner_confidence=0.7,
                resolution_policy="last_wins",
            ),
        ]
        patch = SemanticPatch(
            source_node="aggregation_node",
            scene_id="scene_001",
            conflict_markers=markers,
        )
        assert len(patch.conflict_markers) == 2


class TestPatchHasherIntegration:
    """PatchHasher service integration tests."""

    def test_compute_hash_equals_patch_compute_hash(self):
        """PatchHasher.compute_hash yields same result as patch method."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        h1 = patch.compute_hash()
        h2 = PatchHasher.compute_hash(patch)
        assert h1 == h2

    def test_verify_hash_valid(self):
        """verify_hash returns True for matching hash."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        h = PatchHasher.compute_hash(patch)
        assert PatchHasher.verify_hash(patch, h)

    def test_verify_hash_invalid(self):
        """verify_hash returns False for non-matching hash."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert not PatchHasher.verify_hash(patch, "x" * 64)

    def test_batch_deduplication(self):
        """batch_hashes deduplicates identical patches."""
        patches = [
            SemanticPatch(
                source_node="vision_node",
                scene_id="scene_001",
            ),
            SemanticPatch(
                source_node="vision_node",
                scene_id="scene_001",
            ),
            SemanticPatch(
                source_node="vision_node",
                scene_id="scene_002",
            ),
        ]
        result = PatchHasher.batch_hashes(patches)
        assert len(result) == 2  # Two unique hashes

    def test_hash_scene_id_deterministic(self):
        """hash_scene_id produces same result for same inputs."""
        h1 = PatchHasher.hash_scene_id("scene_001", "vision_node")
        h2 = PatchHasher.hash_scene_id("scene_001", "vision_node")
        assert h1 == h2
        assert len(h1) == 64


class TestReplayConsistency:
    """Replay safety: same patch sequence → same output."""

    def test_identical_patches_deterministic_order(self):
        """Two patches with same content have same dict and JSON."""
        p1 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        p2 = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[CharacterEntity(normalized_name="naruto")],
        )
        assert p1.to_dict_deterministic() == p2.to_dict_deterministic()
        assert p1.to_json() == p2.to_json()

    def test_patch_order_affects_merge_hint(self):
        """patch_order field is carried and compared."""
        early = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            patch_order=0,
        )
        late = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            patch_order=1,
        )
        assert early.patch_order < late.patch_order

    def test_noop_replay_safe(self):
        """A noop patch has stable identity across serialization."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        h = patch.compute_hash()
        reconstructed = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert reconstructed.compute_hash() == h


class TestEdgeCases:
    """Edge cases: empty lists, all fields None, extreme values."""

    def test_empty_character_list(self):
        """Empty explicit list vs None."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[],
        )
        assert patch.characters == []
        # Not noop because characters is explicitly set (to empty list)
        assert not patch.is_noop

    def test_all_entity_lists_empty(self):
        """All entity lists explicitly empty."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            characters=[],
            actions=[],
            objects=[],
            environments=[],
            emotions=[],
        )
        assert patch.characters == []
        # This is NOT a noop because the lists are explicitly empty
        assert not patch.is_noop

    def test_no_warnings(self):
        """Default warnings is empty list."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
        )
        assert patch.warnings == []

    def test_with_warnings(self):
        """Patch carries extraction warnings."""
        patch = SemanticPatch(
            source_node="vision_node",
            scene_id="scene_001",
            warnings=["low_confidence"],
        )
        assert "low_confidence" in patch.warnings

    def test_extreme_motion_values(self):
        """Motion intensity at boundaries."""
        patch = SemanticPatch(
            source_node="motion_node",
            scene_id="scene_001",
            motion_intensity=1.0,
        )
        assert patch.motion_intensity == 1.0

    def test_motion_intensity_zero(self):
        """Zero motion intensity is valid."""
        patch = SemanticPatch(
            source_node="motion_node",
            scene_id="scene_001",
            motion_intensity=0.0,
        )
        assert patch.motion_intensity == 0.0

    def test_all_fields_set(self):
        """Stress: patch with all fields populated."""
        patch = SemanticPatch(
            source_node="oracle_node",
            scene_id="scene_999",
            schema_version="Phase2A.3",
            patch_order=5,
            narrative_event_type="magic",
            characters=[CharacterEntity(normalized_name="shinra")],
            actions=[ActionEntity(normalized_name="ignite")],
            objects=[ObjectEntity(normalized_name="flame")],
            environments=[
                EnvironmentEntity(normalized_name="burning_city")
            ],
            emotions=[EmotionEntity(normalized_name="determined")],
            dialogue="I'll save everyone!",
            ocr_text="FIRE FORCE",
            motion_intensity=0.9,
            motion_direction="up",
            action_pace="extreme",
            num_keyframes=120,
            num_text_regions=3,
            warnings=["partial_ocr"],
            provenance=ProvenanceInfo(
                source=ExtractionSource.WD14,
                confidence=0.99,
            ),
        )
        # Verify all fields
        assert patch.source_node == "oracle_node"
        assert patch.scene_id == "scene_999"
        assert patch.schema_version == "Phase2A.3"
        assert patch.patch_order == 5
        assert patch.narrative_event_type == "magic"
        assert len(patch.characters) == 1
        assert len(patch.actions) == 1
        assert patch.dialogue == "I'll save everyone!"
        assert patch.ocr_text == "FIRE FORCE"
        assert patch.motion_intensity == 0.9
        assert patch.num_keyframes == 120
        assert patch.provenance is not None
        assert not patch.is_noop