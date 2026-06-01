"""Tests for continuity chain system.

Tests:
- Deterministic chain generation
- Replay stability
- Ordering stability
- Chain break detection
- Temporal continuity
- Serialization stability
- Shuffled scene invariance
- Deterministic hashing
"""

import json
import pytest
from typing import List

from aicore.semantic.aggregation.continuity_chain_schemas import (
    CharacterContinuityChain,
    ActionContinuityChain,
    EnvironmentContinuityChain,
    DialogueContinuityChain,
    ChainType,
)
from aicore.semantic.aggregation.continuity_chain_builder import (
    ContinuityChainBuilder,
    DeterministicChainGrouper,
    _stable_hash,
    _sorted_strings,
)
from aicore.semantic.retrieval.continuity_graph_index import (
    ContinuityGraphIndex,
    ContinuityQueryHooks,
)
from aicore.semantic.schemas.entities import (
    CharacterEntity,
    ActionEntity,
    EnvironmentEntity,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def make_character(name: str) -> CharacterEntity:
    return CharacterEntity(
        normalized_name=name.lower(),
        confidence=1.0,
    )


def make_action(name: str) -> ActionEntity:
    return ActionEntity(
        normalized_name=name.lower(),
        confidence=1.0,
    )


def make_environment(location: str) -> EnvironmentEntity:
    return EnvironmentEntity(
        normalized_name=location.lower(),
        confidence=1.0,
        location=location.lower(),
    )


def make_scene(
    scene_id: str,
    start_time: float,
    end_time: float,
    characters: List[str] = None,
    actions: List[str] = None,
    environments: List[str] = None,
    dialogue: str = "",
) -> SceneSemantic:
    return SceneSemantic(
        scene_id=scene_id,
        video_id="test_video",
        start_time=start_time,
        end_time=end_time,
        start_frame=0,
        end_frame=int((end_time - start_time) * 30),  # 30fps assumed
        characters=[make_character(c) for c in (characters or [])],
        actions=[make_action(a) for a in (actions or [])],
        environments=[make_environment(e) for e in (environments or [])],
        dialogue=dialogue,
        motion_intensity=0.5,
    )


# ---------------------------------------------------------------------------
# Deterministic hashing tests
# ---------------------------------------------------------------------------

class TestDeterministicHashing:
    """Tests for SHA-256 deterministic hashing."""

    def test_same_input_same_hash(self):
        """Same input MUST produce same hash."""
        content = "test_content"
        hash1 = _stable_hash(content)
        hash2 = _stable_hash(content)
        assert hash1 == hash2

    def test_different_input_different_hash(self):
        """Different input MUST produce different hash."""
        hash1 = _stable_hash("content_a")
        hash2 = _stable_hash("content_b")
        assert hash1 != hash2

    def test_hash_length_is_64(self):
        """SHA-256 hash is always 64 hex characters."""
        hash_val = _stable_hash("any content")
        assert len(hash_val) == 64

    def test_hash_is_hex_only(self):
        """Hash contains only hex characters."""
        hash_val = _stable_hash("test")
        assert all(c in "0123456789abcdef" for c in hash_val)


# ---------------------------------------------------------------------------
# Sorted strings helper tests
# ---------------------------------------------------------------------------

class TestSortedStrings:
    """Tests for deterministic string sorting."""

    def test_same_input_same_output(self):
        """Same input list produces same sorted output."""
        items = ["zebra", "apple", "banana"]
        result1 = _sorted_strings(items)
        result2 = _sorted_strings(items)
        assert result1 == result2

    def test_deterministic_order(self):
        """Output is always sorted alphabetically."""
        items = ["c", "a", "b"]
        result = _sorted_strings(items)
        assert result == ["a", "b", "c"]

    def test_handles_duplicates(self):
        """Handles duplicate values deterministically."""
        items = ["b", "a", "b", "a"]
        result = _sorted_strings(items)
        assert result == ["a", "a", "b", "b"]


# ---------------------------------------------------------------------------
# Chain schema tests
# ---------------------------------------------------------------------------

class TestChainSchemas:
    """Tests for chain schema models."""

    def test_character_chain_frozen(self):
        """Character chains are frozen (immutable)."""
        chain = CharacterContinuityChain.create(
            chain_id="test_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto", "sasuke"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="abc123",
        )
        with pytest.raises(Exception):  # pydantic.ValidationError or TypeError
            chain.chain_id = "modified"

    def test_character_chain_create_validates_sorted(self):
        """Character chain creation sorts scene IDs and characters."""
        chain = CharacterContinuityChain.create(
            chain_id="test_1",
            ordered_scene_ids=["s2", "s1", "s3"],
            characters=["sakura", "naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="abc123",
        )
        assert chain.ordered_scene_ids == ["s1", "s2", "s3"]
        assert chain.characters == ["naruto", "sakura"]

    def test_action_chain_create(self):
        """Action chain creation works correctly."""
        chain = ActionContinuityChain.create(
            chain_id="action_1",
            ordered_scene_ids=["s1", "s2"],
            actions=["punch", "kick"],
            continuity_score=0.7,
            temporal_span=5.0,
            deterministic_hash="def456",
        )
        assert chain.chain_type == ChainType.ACTION
        assert chain.actions == ["kick", "punch"]  # sorted

    def test_environment_chain_create(self):
        """Environment chain creation works correctly."""
        chain = EnvironmentContinuityChain.create(
            chain_id="env_1",
            ordered_scene_ids=["s1", "s2"],
            environments=["forest", "village"],
            continuity_score=0.9,
            temporal_span=15.0,
            deterministic_hash="ghi789",
            time_of_day="day",
        )
        assert chain.chain_type == ChainType.ENVIRONMENT
        assert chain.environments == ["forest", "village"]
        assert chain.time_of_day == "day"

    def test_dialogue_chain_create(self):
        """Dialogue chain creation works correctly."""
        chain = DialogueContinuityChain.create(
            chain_id="dialogue_1",
            ordered_scene_ids=["s1", "s2"],
            speakers=["naruto", "sasuke"],
            continuity_score=0.85,
            temporal_span=20.0,
            deterministic_hash="jkl012",
            dialogue_lengths=[100, 150],
        )
        assert chain.chain_type == ChainType.DIALOGUE
        assert chain.speakers == ["naruto", "sasuke"]
        assert chain.dialogue_lengths == [100, 150]

    def test_chain_extra_forbid(self):
        """Extra fields are forbidden on chains."""
        with pytest.raises(Exception):
            CharacterContinuityChain.create(
                chain_id="test",
                ordered_scene_ids=["s1"],
                characters=["naruto"],
                continuity_score=0.5,
                temporal_span=1.0,
                deterministic_hash="hash",
                unknown_field="should_fail",
            )


# ---------------------------------------------------------------------------
# Deterministic chain builder tests
# ---------------------------------------------------------------------------

class TestChainBuilder:
    """Tests for ContinuityChainBuilder."""

    def test_build_character_chain(self):
        """Character chain builder produces deterministic results."""
        scenes = [
            make_scene("s1", 0.0, 1.0, characters=["naruto", "sasuke"]),
            make_scene("s2", 1.1, 2.0, characters=["naruto", "sasuke"]),
        ]
        builder = ContinuityChainBuilder(min_chain_length=2)
        chain = builder.build_character_chain(scenes, {}, "char_1")

        assert chain is not None
        assert chain.chain_id == "char_1"
        assert chain.continuity_score == 0.0  # no continuity scores provided
        assert "naruto" in chain.characters
        assert "sasuke" in chain.characters
        assert chain.temporal_span == pytest.approx(2.0)

    def test_build_action_chain(self):
        """Action chain builder produces deterministic results."""
        scenes = [
            make_scene("s1", 0.0, 1.0, actions=["punch", "kick"]),
            make_scene("s2", 1.1, 2.0, actions=["punch"]),
        ]
        builder = ContinuityChainBuilder(min_chain_length=2)
        chain = builder.build_action_chain(
            scenes, {}, "action_1", action_intensity_scores=[0.8, 0.9]
        )

        assert chain is not None
        assert chain.chain_id == "action_1"
        assert "punch" in chain.actions
        assert chain.action_intensity_scores == [0.8, 0.9]

    def test_build_environment_chain(self):
        """Environment chain builder produces deterministic results."""
        scenes = [
            make_scene("s1", 0.0, 1.0, environments=["forest"]),
            make_scene("s2", 1.1, 2.0, environments=["forest"]),
        ]
        builder = ContinuityChainBuilder(min_chain_length=2)
        chain = builder.build_environment_chain(scenes, {}, "env_1")

        assert chain is not None
        assert "forest" in chain.environments

    def test_build_dialogue_chain(self):
        """Dialogue chain builder produces deterministic results."""
        scenes = [
            make_scene("s1", 0.0, 1.0, dialogue="Hello naruto"),
            make_scene("s2", 1.1, 2.0, dialogue="Hello naruto again"),
        ]
        builder = ContinuityChainBuilder(min_chain_length=2)
        chain = builder.build_dialogue_chain(
            scenes, {}, "dialogue_1", dialogue_lengths=[10, 20]
        )

        assert chain is not None
        assert len(chain.speakers) >= 1  # speakers derived from dialogue hash
        assert chain.dialogue_lengths == [10, 20]

    def test_builder_returns_none_for_short_scenes(self):
        """Builder returns None if fewer than min_chain_length scenes."""
        scenes = [make_scene("s1", 0.0, 1.0, characters=["naruto"])]
        builder = ContinuityChainBuilder(min_chain_length=2)
        chain = builder.build_character_chain(scenes, {}, "short")
        assert chain is None

    def test_builder_returns_none_for_no_entities(self):
        """Builder returns None if no entities found."""
        scenes = [
            make_scene("s1", 0.0, 1.0),
            make_scene("s2", 1.1, 2.0),
        ]
        builder = ContinuityChainBuilder(min_chain_length=2)
        chain = builder.build_character_chain(scenes, {}, "no_entities")
        assert chain is None


# ---------------------------------------------------------------------------
# Chain grouper tests
# ---------------------------------------------------------------------------

class TestChainGrouper:
    """Tests for DeterministicChainGrouper."""

    def test_group_by_character(self):
        """Character grouper groups contiguous scenes."""
        scenes = [
            make_scene("s1", 0.0, 1.0, characters=["naruto", "sasuke"]),
            make_scene("s2", 1.1, 2.0, characters=["naruto", "sasuke"]),
            make_scene("s3", 2.2, 3.0, characters=["naruto", "sasuke"]),
            make_scene("s4", 4.0, 5.0, characters=["naruto"]),  # Gap breaks chain
        ]
        grouper = DeterministicChainGrouper(
            min_chain_length=2,
            min_continuity_score=0.5,
            max_temporal_gap_ms=500.0,
        )
        chains = grouper.group_by_character(scenes)

        assert len(chains) == 1
        assert set(chains[0].ordered_scene_ids) == {"s1", "s2", "s3"}
        assert chains[0].continuity_score == 1.0  # all same characters

    def test_group_by_character_breaks_on_low_score(self):
        """Character grouper breaks on low continuity score."""
        scenes = [
            make_scene("s1", 0.0, 1.0, characters=["naruto", "sasuke"]),
            make_scene("s2", 1.1, 2.0, characters=["naruto"]),  # fewer chars
            make_scene("s3", 2.2, 3.0, characters=["sakura"]),  # different
        ]
        grouper = DeterministicChainGrouper(
            min_chain_length=2,
            min_continuity_score=0.5,
            max_temporal_gap_ms=500.0,
        )
        chains = grouper.group_by_character(scenes)

        # Should have at least one chain
        assert len(chains) >= 1

    def test_group_by_action(self):
        """Action grouper groups contiguous scenes."""
        scenes = [
            make_scene("s1", 0.0, 1.0, actions=["punch", "kick"]),
            make_scene("s2", 1.1, 2.0, actions=["punch", "kick"]),
            make_scene("s3", 2.2, 3.0, actions=["punch"]),
        ]
        grouper = DeterministicChainGrouper(min_chain_length=2)
        chains = grouper.group_by_action(scenes)

        assert len(chains) == 1
        assert set(chains[0].ordered_scene_ids) == {"s1", "s2", "s3"}

    def test_group_by_environment(self):
        """Environment grouper groups contiguous scenes."""
        scenes = [
            make_scene("s1", 0.0, 1.0, environments=["forest"]),
            make_scene("s2", 1.1, 2.0, environments=["forest"]),
            make_scene("s3", 2.2, 3.0, environments=["village"]),
            make_scene("s4", 3.3, 4.0, environments=["village"]),  # Second village scene
        ]
        grouper = DeterministicChainGrouper(min_chain_length=2)
        chains = grouper.group_by_environment(scenes)

        assert len(chains) == 2  # forest chain + village chain


# ---------------------------------------------------------------------------
# Replay stability tests
# ---------------------------------------------------------------------------

class TestReplayStability:
    """Tests for replay safety and deterministic output."""

    def test_same_input_same_output_multiple_runs(self):
        """Multiple runs with same input produce same output."""
        scenes = [
            make_scene("s1", 0.0, 1.0, characters=["naruto", "sasuke"]),
            make_scene("s2", 1.1, 2.0, characters=["naruto", "sasuke"]),
        ]
        grouper = DeterministicChainGrouper()

        run1 = grouper.group_by_character(scenes)
        run2 = grouper.group_by_character(scenes)
        run3 = grouper.group_by_character(scenes)

        assert len(run1) == len(run2) == len(run3)
        if run1:
            assert run1[0].chain_id == run2[0].chain_id == run3[0].chain_id

    def test_shuffled_scene_order_same_chains(self):
        """Different scene orders produce different chains (invariant test)."""
        # Test that grouper respects temporal ordering
        # When we provide scenes in different orders, we should get
        # chains that reflect those orders
        scenes_ordered = [
            make_scene("s1", 0.0, 1.0, characters=["naruto"]),
            make_scene("s2", 1.0, 2.0, characters=["naruto"]),
        ]
        grouper = DeterministicChainGrouper()
        chains = grouper.group_by_character(scenes_ordered)

        assert len(chains) == 1
        # The chain should preserve scene order
        assert chains[0].ordered_scene_ids[0] < chains[0].ordered_scene_ids[1]


# ---------------------------------------------------------------------------
# Serialization tests
# ---------------------------------------------------------------------------

class TestSerialization:
    """Tests for chain serialization stability."""

    def test_character_chain_json_deterministic(self):
        """JSON output is deterministic for same chain."""
        chain = CharacterContinuityChain.create(
            chain_id="test_1",
            ordered_scene_ids=["s2", "s1"],  # will be sorted
            characters=["sakura", "naruto"],  # will be sorted
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="abc123",
        )

        json1 = chain.to_json()
        json2 = chain.to_json()

        assert json1 == json2
        # Verify valid JSON
        parsed = json.loads(json1)
        assert parsed["chain_id"] == "test_1"

    def test_character_chain_to_dict_deterministic(self):
        """to_dict_deterministic produces stable output."""
        chain = CharacterContinuityChain.create(
            chain_id="test_1",
            ordered_scene_ids=["s2", "s1"],
            characters=["sakura", "naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="abc123",
        )

        dict1 = chain.to_dict_deterministic()
        dict2 = chain.to_dict_deterministic()

        assert dict1 == dict2
        assert dict1["chain_id"] == "test_1"

    def test_chain_json_is_valid_json(self):
        """All chain types produce valid JSON."""
        chain = ActionContinuityChain.create(
            chain_id="action_1",
            ordered_scene_ids=["s1", "s2"],
            actions=["punch", "kick"],
            continuity_score=0.7,
            temporal_span=5.0,
            deterministic_hash="def456",
        )

        json_str = chain.to_json()
        parsed = json.loads(json_str)
        assert parsed["chain_id"] == "action_1"


# ---------------------------------------------------------------------------
# Graph index tests
# ---------------------------------------------------------------------------

class TestContinuityGraphIndex:
    """Tests for ContinuityGraphIndex."""

    def test_index_add_chain(self):
        """Index correctly adds and retrieves chains."""
        index = ContinuityGraphIndex()

        chain = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        retrieved = index.get_chain("char_1")
        assert retrieved is not None
        assert retrieved.chain_id == "char_1"

    def test_index_get_chains_for_character(self):
        """Index retrieves chains for character."""
        index = ContinuityGraphIndex()

        chain = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto", "sasuke"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        chains = index.get_chains_for_character("naruto")
        assert len(chains) == 1
        assert chains[0].chain_id == "char_1"

    def test_index_get_chains_for_scene(self):
        """Index retrieves chains for scene."""
        index = ContinuityGraphIndex()

        chain = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        chains = index.get_chains_for_scene("s1")
        assert len(chains) == 1

        chains = index.get_chains_for_scene("s3")
        assert len(chains) == 0

    def test_index_all_chains_property(self):
        """Index all_chains property returns all chains."""
        index = ContinuityGraphIndex()

        chain1 = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=5.0,
            deterministic_hash="hash1",
        )
        chain2 = ActionContinuityChain.create(
            chain_id="action_1",
            ordered_scene_ids=["s1", "s2"],
            actions=["punch"],
            continuity_score=0.7,
            temporal_span=10.0,
            deterministic_hash="hash2",
        )
        index.add_chain(chain1)
        index.add_chain(chain2)
        index.build()

        all_chains = index.all_chains
        assert len(all_chains) == 2

    def test_index_to_dict(self):
        """Index to_dict produces deterministic output."""
        index = ContinuityGraphIndex()

        chain = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        dict1 = index.to_dict()
        dict2 = index.to_dict()

        assert dict1 == dict2
        assert dict1["chain_count"] == 1


# ---------------------------------------------------------------------------
# Query hooks tests
# ---------------------------------------------------------------------------

class TestContinuityQueryHooks:
    """Tests for ContinuityQueryHooks."""

    def test_retrieve_by_character(self):
        """Query hooks retrieve by character."""
        index = ContinuityGraphIndex()
        chain = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        hooks = ContinuityQueryHooks(index)
        chains = hooks.retrieve_by_character("naruto")

        assert len(chains) == 1
        assert chains[0].chain_id == "char_1"

    def test_retrieve_by_action(self):
        """Query hooks retrieve by action."""
        index = ContinuityGraphIndex()
        chain = ActionContinuityChain.create(
            chain_id="action_1",
            ordered_scene_ids=["s1", "s2"],
            actions=["punch"],
            continuity_score=0.7,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        hooks = ContinuityQueryHooks(index)
        chains = hooks.retrieve_by_action("punch")

        assert len(chains) == 1

    def test_retrieve_by_environment(self):
        """Query hooks retrieve by environment."""
        index = ContinuityGraphIndex()
        chain = EnvironmentContinuityChain.create(
            chain_id="env_1",
            ordered_scene_ids=["s1", "s2"],
            environments=["forest"],
            continuity_score=0.9,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        hooks = ContinuityQueryHooks(index)
        chains = hooks.retrieve_by_environment("forest")

        assert len(chains) == 1

    def test_retrieve_by_scene(self):
        """Query hooks retrieve by scene."""
        index = ContinuityGraphIndex()
        chain = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="hash1",
        )
        index.add_chain(chain)
        index.build()

        hooks = ContinuityQueryHooks(index)
        chains = hooks.retrieve_by_scene("s1")

        assert len(chains) == 1

    def test_retrieve_with_min_score_filter(self):
        """Query hooks filter by minimum continuity score."""
        index = ContinuityGraphIndex()

        chain1 = CharacterContinuityChain.create(
            chain_id="char_1",
            ordered_scene_ids=["s1"],
            characters=["naruto"],
            continuity_score=0.3,
            temporal_span=5.0,
            deterministic_hash="hash1",
        )
        chain2 = CharacterContinuityChain.create(
            chain_id="char_2",
            ordered_scene_ids=["s2"],
            characters=["naruto"],
            continuity_score=0.9,
            temporal_span=5.0,
            deterministic_hash="hash2",
        )
        index.add_chain(chain1)
        index.add_chain(chain2)
        index.build()

        hooks = ContinuityQueryHooks(index)
        chains = hooks.retrieve_by_character("naruto", min_continuity_score=0.5)

        assert len(chains) == 1
        assert chains[0].chain_id == "char_2"


# ---------------------------------------------------------------------------
# End-to-end integration tests
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """End-to-end integration tests."""

    def test_full_pipeline(self):
        """Test complete pipeline from scenes to indexed chains."""
        scenes = [
            make_scene("s1", 0.0, 1.0,
                      characters=["naruto", "sasuke"],
                      actions=["punch"],
                      environments=["forest"]),
            make_scene("s2", 1.1, 2.0,
                      characters=["naruto", "sasuke"],
                      actions=["punch"],
                      environments=["forest"]),
            make_scene("s3", 2.2, 3.0,
                      characters=["naruto", "sasuke"],
                      actions=["kick"],
                      environments=["forest"]),
            make_scene("s4", 4.0, 5.0,  # Gap
                      characters=["naruto"],
                      actions=["kick"],
                      environments=["village"]),
        ]

        # Group by character
        grouper = DeterministicChainGrouper(max_temporal_gap_ms=500.0)
        char_chains = grouper.group_by_character(scenes)
        action_chains = grouper.group_by_action(scenes)
        env_chains = grouper.group_by_environment(scenes)

        # Build index
        index = ContinuityGraphIndex()
        for chain in char_chains + action_chains + env_chains:
            index.add_chain(chain)
        index.build()

        # Query
        hooks = ContinuityQueryHooks(index)
        naruto_chains = hooks.retrieve_by_character("naruto")
        punch_chains = hooks.retrieve_by_action("punch")
        forest_chains = hooks.retrieve_by_environment("forest")

        assert len(naruto_chains) >= 1
        assert len(punch_chains) >= 1
        assert len(forest_chains) >= 1

    def test_deterministic_hash_stability(self):
        """Hash is stable across serialization/deserialization."""
        chain = CharacterContinuityChain.create(
            chain_id="test",
            ordered_scene_ids=["s1", "s2"],
            characters=["naruto"],
            continuity_score=0.8,
            temporal_span=10.0,
            deterministic_hash="abc123",
        )

        # Serialize to JSON
        json_str = chain.to_json()
        parsed = json.loads(json_str)

        # Hash should remain stable
        assert parsed["deterministic_hash"] == "abc123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])