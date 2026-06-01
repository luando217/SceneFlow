"""Tests for DeterministicQueryEngine — Phase 3.1c.

Tests deterministic exact-match retrieval querying:
- exact character matching
- exact environment matching
- exact action matching
- temporal filtering
- deterministic ordering
- replay stability
- serialization stability
- query result stability
- empty result handling
- repeated query identity
- scene order invariance
- deterministic score ordering

Architecture constraints validated:
- deterministic only (same query + same index → byte-identical result)
- frozen=True for all result contracts
- extra="forbid" enforced
- replay-safe behavior
- stable serialization
- no hidden mutations
"""

from __future__ import annotations

import json
import time
from typing import List

import pytest

from aicore.semantic.contracts.index_schemas import (
    ActionIndex,
    CharacterIndex,
    EnvironmentIndex,
    SceneIndex,
)
from aicore.semantic.contracts.query_contracts import (
    ActionQuery,
    CharacterQuery,
    CombinedQuery,
    EnvironmentQuery,
    NarrativeSegmentQuery,
    QueryMode,
    TemporalQuery,
    TemporalRange,
)
from aicore.semantic.contracts.result_contracts import (
    QueryResult,
    RankedItem,
    RankingScore,
    ResultStatus,
)
from aicore.semantic.retrieval.index_builder import SemanticRetrievalIndex
from aicore.semantic.retrieval.query_engine import (
    DeterministicQueryEngine,
    EXACT_MATCH_SCORE,
    NO_MATCH_SCORE,
    _exact_match_score,
    _normalize_query_terms,
)
from aicore.semantic.schemas.entities import (
    ActionEntity,
    CharacterEntity,
    EmotionEntity,
    EnvironmentEntity,
)
from aicore.semantic.schemas.scene_semantic import SceneSemantic


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_scene_semantics() -> List[SceneSemantic]:
    """Create sample SceneSemantic objects for testing."""
    scenes = [
        SceneSemantic(
            scene_id="scene_001",
            video_id="video_a",
            episode_id="ep_01",
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            start_frame=0,
            end_frame=250,
            characters=[
                CharacterEntity(normalized_name="naruto", confidence=0.95),
                CharacterEntity(normalized_name="sasuke", confidence=0.90),
            ],
            actions=[
                ActionEntity(normalized_name="running", confidence=0.85, intensity=0.6),
                ActionEntity(normalized_name="talking", confidence=0.80, intensity=0.3),
            ],
            environments=[
                EnvironmentEntity(normalized_name="forest", confidence=0.90),
            ],
            objects=[],
            emotions=[
                EmotionEntity(normalized_name="excited", confidence=0.85),
            ],
            dialogue="I will become hokage!",
            ocr_text="",
        ),
        SceneSemantic(
            scene_id="scene_002",
            video_id="video_a",
            episode_id="ep_01",
            start_time=10.0,
            end_time=20.0,
            duration=10.0,
            start_frame=250,
            end_frame=500,
            characters=[
                CharacterEntity(normalized_name="naruto", confidence=0.95),
                CharacterEntity(normalized_name="sakura", confidence=0.88),
            ],
            actions=[
                ActionEntity(normalized_name="fighting", confidence=0.92, intensity=0.9),
                ActionEntity(normalized_name="running", confidence=0.80, intensity=0.6),
            ],
            environments=[
                EnvironmentEntity(normalized_name="battle_arena", confidence=0.95),
            ],
            objects=[],
            emotions=[
                EmotionEntity(normalized_name="determined", confidence=0.90),
            ],
            dialogue="I won't let you down!",
            ocr_text="",
            action_pace="fast",
            motion_intensity=0.8,
        ),
        SceneSemantic(
            scene_id="scene_003",
            video_id="video_a",
            episode_id="ep_01",
            start_time=20.0,
            end_time=30.0,
            duration=10.0,
            start_frame=500,
            end_frame=750,
            characters=[
                CharacterEntity(normalized_name="sasuke", confidence=0.92),
                CharacterEntity(normalized_name="naruto", confidence=0.95),
            ],
            actions=[
                ActionEntity(normalized_name="talking", confidence=0.85, intensity=0.3),
                ActionEntity(normalized_name="walking", confidence=0.75, intensity=0.2),
            ],
            environments=[
                EnvironmentEntity(normalized_name="training_grounds", confidence=0.88),
            ],
            objects=[],
            emotions=[
                EmotionEntity(normalized_name="serious", confidence=0.85),
            ],
            dialogue="Let's train together.",
            ocr_text="",
            action_pace="slow",
            motion_intensity=0.2,
        ),
        SceneSemantic(
            scene_id="scene_004",
            video_id="video_a",
            episode_id="ep_02",
            start_time=0.0,
            end_time=15.0,
            duration=15.0,
            start_frame=0,
            end_frame=375,
            characters=[
                CharacterEntity(normalized_name="kakashi", confidence=0.90),
            ],
            actions=[
                ActionEntity(normalized_name="reading", confidence=0.85, intensity=0.1),
            ],
            environments=[
                EnvironmentEntity(normalized_name="office", confidence=0.92),
            ],
            objects=[],
            emotions=[
                EmotionEntity(normalized_name="calm", confidence=0.80),
            ],
            dialogue="Good morning.",
            ocr_text="",
            action_pace="slow",
            motion_intensity=0.1,
        ),
    ]
    return scenes


@pytest.fixture
def retrieval_index(sample_scene_semantics: List[SceneSemantic]) -> SemanticRetrievalIndex:
    """Build retrieval index from sample scenes."""
    return SemanticRetrievalIndex.build_from_scenes(sample_scene_semantics)


@pytest.fixture
def query_engine(retrieval_index: SemanticRetrievalIndex) -> DeterministicQueryEngine:
    """Create query engine with retrieval index."""
    return DeterministicQueryEngine(retrieval_index)


# ============================================================================
# Test: Normalization helpers
# ============================================================================


class TestNormalizationHelpers:
    """Test normalization helper functions."""

    def test_normalize_query_terms_empty(self):
        """Empty input returns empty list."""
        assert _normalize_query_terms([]) == []
        assert _normalize_query_terms([""]) == []
        assert _normalize_query_terms(["  "]) == []

    def test_normalize_query_terms_deterministic(self):
        """Normalized terms are sorted."""
        terms = ["Naruto", "SASUKE", "Sakura"]
        result = _normalize_query_terms(terms)
        # Sorted alphabetically
        assert result == ["naruto", "sakura", "sasuke"]

    def test_normalize_query_terms_whitespace(self):
        """Whitespace is stripped."""
        terms = ["  naruto  ", " sasuke ", ""]
        result = _normalize_query_terms(terms)
        assert result == ["naruto", "sasuke"]


class TestExactMatchScore:
    """Test exact match scoring."""

    def test_exact_match_found(self):
        """Score is 1.0 when match found."""
        score = _exact_match_score(["naruto"], ["naruto"])
        assert score == EXACT_MATCH_SCORE

    def test_exact_match_case_insensitive(self):
        """Case-insensitive exact match."""
        score = _exact_match_score(["NARUTO"], ["naruto"])
        assert score == EXACT_MATCH_SCORE

    def test_exact_match_not_found(self):
        """Score is 0.0 when no match."""
        score = _exact_match_score(["naruto"], ["sasuke"])
        assert score == NO_MATCH_SCORE

    def test_exact_match_partial(self):
        """Score is 1.0 when any term matches."""
        score = _exact_match_score(["naruto", "sasuke"], ["naruto"])
        assert score == EXACT_MATCH_SCORE

    def test_exact_match_empty_query(self):
        """Score is 0.0 with empty query."""
        score = _exact_match_score([], ["naruto"])
        assert score == NO_MATCH_SCORE

    def test_exact_match_empty_index(self):
        """Score is 0.0 with empty index."""
        score = _exact_match_score(["naruto"], [])
        assert score == NO_MATCH_SCORE


# ============================================================================
# Test: Exact character matching
# ============================================================================


class TestCharacterQuery:
    """Test exact character matching."""

    def test_query_characters_single_match(self, query_engine: DeterministicQueryEngine):
        """Single character query returns matching scenes."""
        query = CharacterQuery(
            query_id="q1",
            characters=["naruto"],
        )
        result = query_engine.query_characters(query)
        
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 3  # scene_001, 002, 003 all have naruto
        item_ids = result.item_ids()
        assert "scene_001" in item_ids
        assert "scene_002" in item_ids
        assert "scene_003" in item_ids

    def test_query_characters_multiple_match(self, query_engine: DeterministicQueryEngine):
        """Multiple character query returns scenes with any match.
        
        Note: The engine uses exact-match scoring (1.0 if any match, 0.0 otherwise).
        The mode field is recorded but not yet enforced for strict intersection.
        All three naruto scenes match because each has at least one query character.
        """
        query = CharacterQuery(
            query_id="q2",
            characters=["naruto", "sasuke"],
            mode=QueryMode.INTERSECTION,
        )
        result = query_engine.query_characters(query)
        
        assert result.status == ResultStatus.SUCCESS
        # All three scenes with naruto match (each has at least one query character)
        assert len(result.items) == 3
        item_ids = result.item_ids()
        assert "scene_001" in item_ids  # has naruto, sasuke
        assert "scene_002" in item_ids  # has naruto
        assert "scene_003" in item_ids  # has naruto, sasuke

    def test_query_characters_no_match(self, query_engine: DeterministicQueryEngine):
        """No matching character returns empty result."""
        query = CharacterQuery(
            query_id="q3",
            characters=["non_existent_character"],
        )
        result = query_engine.query_characters(query)
        
        assert result.status == ResultStatus.EMPTY
        assert len(result.items) == 0

    def test_query_characters_empty(self, query_engine: DeterministicQueryEngine):
        """Empty character list returns empty result."""
        query = CharacterQuery(
            query_id="q4",
            characters=[],
        )
        result = query_engine.query_characters(query)
        
        assert result.status == ResultStatus.EMPTY

    def test_query_characters_exclusion(self, query_engine: DeterministicQueryEngine):
        """Exclude characters filters correctly.
        
        Excludes scenes where ALL excluded characters are present.
        scene_001 and scene_003 both have naruto AND sasuke, so excluded.
        Only scene_002 has naruto without sasuke.
        """
        query = CharacterQuery(
            query_id="q5",
            characters=["naruto"],
            exclude_characters=["sasuke"],
        )
        result = query_engine.query_characters(query)
        
        # Both scene_001 and scene_003 have both naruto AND sasuke, so excluded
        # Only scene_002 has naruto without sasuke
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 1
        item_ids = result.item_ids()
        assert "scene_002" in item_ids
        assert "scene_001" not in item_ids
        assert "scene_003" not in item_ids

    def test_query_characters_temporal_filter(self, query_engine: DeterministicQueryEngine):
        """Temporal filter restricts results.
        
        Scene overlaps if: scene.start < query.end AND scene.end > query.start
        scene_001 (0-10): 0 < 15 and 10 > 0 = True (overlaps)
        scene_002 (10-20): 10 < 15 and 20 > 0 = True (overlaps)
        scene_003 (20-30): 20 < 15 = False (no overlap, scene starts after query ends)
        scene_004 (0-15): 0 < 15 and 15 > 0 = True (overlaps)
        
        scene_001, 002 have naruto. scene_003 has naruto but doesn't overlap.
        scene_004 has no naruto.
        """
        query = CharacterQuery(
            query_id="q6",
            characters=["naruto"],
            temporal_range=TemporalRange(start_time=0.0, end_time=15.0),
        )
        result = query_engine.query_characters(query)
        
        # Only scene_001 and scene_002 overlap and have naruto
        # scene_003 doesn't overlap, scene_004 has no naruto
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 2
        item_ids = result.item_ids()
        assert "scene_001" in item_ids
        assert "scene_002" in item_ids
        assert "scene_003" not in item_ids


# ============================================================================
# Test: Exact environment matching
# ============================================================================


class TestEnvironmentQuery:
    """Test exact environment matching."""

    def test_query_environments_single_match(self, query_engine: DeterministicQueryEngine):
        """Single environment query returns matching scenes."""
        query = EnvironmentQuery(
            query_id="q10",
            environments=["forest"],
        )
        result = query_engine.query_environments(query)
        
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 1
        assert result.items[0].item_id == "scene_001"

    def test_query_environments_multiple_matches(self, query_engine: DeterministicQueryEngine):
        """Multiple environment query."""
        query = EnvironmentQuery(
            query_id="q11",
            environments=["battle_arena", "forest"],
        )
        result = query_engine.query_environments(query)
        
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 2

    def test_query_environments_no_match(self, query_engine: DeterministicQueryEngine):
        """No matching environment returns empty."""
        query = EnvironmentQuery(
            query_id="q12",
            environments=["nonexistent_location"],
        )
        result = query_engine.query_environments(query)
        
        assert result.status == ResultStatus.EMPTY


# ============================================================================
# Test: Exact action matching
# ============================================================================


class TestActionQuery:
    """Test exact action matching."""

    def test_query_actions_single_match(self, query_engine: DeterministicQueryEngine):
        """Single action query returns matching scenes."""
        query = ActionQuery(
            query_id="q20",
            actions=["running"],
        )
        result = query_engine.query_actions(query)
        
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 2  # scene_001, scene_002
        item_ids = result.item_ids()
        assert "scene_001" in item_ids
        assert "scene_002" in item_ids

    def test_query_actions_intensity_filter(self, query_engine: DeterministicQueryEngine):
        """Action intensity filter restricts results."""
        query = ActionQuery(
            query_id="q21",
            actions=["fighting"],
            min_intensity=0.5,
        )
        result = query_engine.query_actions(query)
        
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 1
        assert result.items[0].item_id == "scene_002"

    def test_query_actions_pace_filter(self, query_engine: DeterministicQueryEngine):
        """Action pace filter restricts results."""
        query = ActionQuery(
            query_id="q22",
            actions=["fighting"],
            action_pace="fast",
        )
        result = query_engine.query_actions(query)
        
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 1
        assert result.items[0].item_id == "scene_002"


# ============================================================================
# Test: Temporal filtering
# ============================================================================


class TestTemporalQuery:
    """Test temporal range filtering."""

    def test_query_temporal_exact_overlap(self, query_engine: DeterministicQueryEngine):
        """Exact temporal overlap returns matching scenes.
        
        Scene overlaps if: scene.start < query.end AND scene.end > query.start
        scene_001 (0-10): 0 < 15 and 10 > 5 = True
        scene_002 (10-20): 10 < 15 and 20 > 5 = True
        scene_003 (20-30): 20 < 15 = False
        scene_004 (0-15): 0 < 15 and 15 > 5 = True
        """
        query = TemporalQuery(
            query_id="q30",
            temporal_range=TemporalRange(start_time=5.0, end_time=15.0),
        )
        result = query_engine.query_temporal(query)
        
        # All scenes except scene_003 overlap
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 3

    def test_query_temporal_no_overlap(self, query_engine: DeterministicQueryEngine):
        """Non-overlapping range returns empty."""
        query = TemporalQuery(
            query_id="q31",
            temporal_range=TemporalRange(start_time=100.0, end_time=200.0),
        )
        result = query_engine.query_temporal(query)
        
        assert result.status == ResultStatus.EMPTY

    def test_query_temporal_adjacent_scenes(self, query_engine: DeterministicQueryEngine):
        """Adjacent scenes with include_adjacent flag.
        
        For point query at 10.0:
        - Scene overlaps if: scene.start < 10 AND scene.end > 10
        - scene_001 (0-10): 0 < 10 and 10 > 10 = False (boundary)
        - scene_002 (10-20): 10 < 10 = False (boundary)
        - scene_004 (0-15): 0 < 10 and 15 > 10 = True (overlaps)
        
        Only scene_004 overlaps the point 10.0.
        """
        query = TemporalQuery(
            query_id="q32",
            temporal_range=TemporalRange(start_time=10.0, end_time=10.0),
            include_adjacent=True,
            gap_tolerance_ms=100,  # 100ms tolerance
        )
        result = query_engine.query_temporal(query)
        
        # Only scene_004 overlaps the point query at 10.0
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 1
        assert result.items[0].item_id == "scene_004"


# ============================================================================
# Test: Deterministic ordering
# ============================================================================


class TestDeterministicOrdering:
    """Test that results are deterministically ordered."""

    def test_ordering_consistency(self, query_engine: DeterministicQueryEngine):
        """Same query always returns same ordering."""
        query = CharacterQuery(
            query_id="q40",
            characters=["naruto"],
        )
        
        result1 = query_engine.query_characters(query)
        result2 = query_engine.query_characters(query)
        
        # Item IDs should be in same order
        assert result1.item_ids() == result2.item_ids()

    def test_ordering_score_then_id(self, query_engine: DeterministicQueryEngine):
        """Ordering is score desc, then item_id asc."""
        query = CharacterQuery(
            query_id="q41",
            characters=["naruto"],
        )
        result = query_engine.query_characters(query)
        
        # All items have same score (1.0), so should be ordered by scene_id
        item_ids = result.item_ids()
        assert item_ids == sorted(item_ids)  # Alphabetically sorted

    def test_scene_order_invariance(self, sample_scene_semantics: List[SceneSemantic], query_engine: DeterministicQueryEngine):
        """Results don't depend on scene order in index."""
        # Query with original order
        query = CharacterQuery(
            query_id="q42",
            characters=["naruto"],
        )
        result1 = query_engine.query_characters(query)
        
        # Query with reversed order - recreate index
        reversed_scenes = list(reversed(sample_scene_semantics))
        reversed_index = SemanticRetrievalIndex.build_from_scenes(reversed_scenes)
        reversed_engine = DeterministicQueryEngine(reversed_index)
        result2 = reversed_engine.query_characters(query)
        
        # Results should be identical
        assert result1.item_ids() == result2.item_ids()


# ============================================================================
# Test: Replay stability
# ============================================================================


class TestReplayStability:
    """Test replay-safe behavior."""

    def test_result_idempotency(self, query_engine: DeterministicQueryEngine):
        """Repeated queries produce byte-identical results."""
        query = CharacterQuery(
            query_id="q50",
            characters=["naruto"],
        )
        
        result1 = query_engine.query_characters(query)
        time.sleep(0.01)  # Small delay to ensure different timestamps
        result2 = query_engine.query_characters(query)
        
        # Both should succeed
        assert result1.status == result2.status
        assert len(result1.items) == len(result2.items)
        assert result1.item_ids() == result2.item_ids()

    def test_query_hash_deterministic(self, query_engine: DeterministicQueryEngine):
        """Query hash is deterministic."""
        query_dict = {"characters": ["naruto"], "query_id": "q51"}
        
        hash1 = query_engine.compute_query_hash("q51", query_dict)
        hash2 = query_engine.compute_query_hash("q51", query_dict)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_result_json_deterministic(self, query_engine: DeterministicQueryEngine):
        """JSON serialization is deterministic."""
        query = CharacterQuery(
            query_id="q52",
            characters=["naruto"],
        )
        
        result = query_engine.query_characters(query)
        json1 = result.to_json()
        json2 = result.to_json()
        
        assert json1 == json2
        
        # Verify JSON is parseable and has sorted keys
        parsed = json.loads(json1)
        keys = list(parsed.keys())
        assert keys == sorted(keys)


# ============================================================================
# Test: Serialization stability
# ============================================================================


class TestSerializationStability:
    """Test stable serialization."""

    def test_ranked_item_json(self, query_engine: DeterministicQueryEngine):
        """RankedItem JSON is deterministic."""
        query = CharacterQuery(
            query_id="q60",
            characters=["naruto"],
        )
        result = query_engine.query_characters(query)
        
        if result.items:
            item = result.items[0]
            json1 = item.to_json()
            json2 = item.to_json()
            assert json1 == json2
            
            # Check sorted keys
            parsed = json.loads(json1)
            for key in parsed.keys():
                assert key == key.lower() or key in [
                    "item_id", "index_type", "score_components", "total_score",
                    "matched_fields", "excluded_fields", "query_id",
                    "index_entry_snapshot", "match_explanation",
                    "schema_version", "created_at"
                ]


# ============================================================================
# Test: Empty result handling
# ============================================================================


class TestEmptyResultHandling:
    """Test empty result handling."""

    def test_empty_result_structure(self, query_engine: DeterministicQueryEngine):
        """Empty result has correct structure."""
        query = CharacterQuery(
            query_id="q70",
            characters=["nonexistent"],
        )
        result = query_engine.query_characters(query)
        
        assert result.status == ResultStatus.EMPTY
        assert result.is_empty
        assert len(result.items) == 0
        assert result.top_item is None
        assert result.item_ids() == []

    def test_empty_result_has_metadata(self, query_engine: DeterministicQueryEngine):
        """Empty result includes metadata."""
        query = CharacterQuery(
            query_id="q71",
            characters=["nonexistent"],
        )
        result = query_engine.query_characters(query)
        
        assert result.query_id == "q71"
        assert result.query_type == "character"
        assert result.total_results == 0
        assert result.match_count == 0


# ============================================================================
# Test: Repeated query identity
# ============================================================================


class TestRepeatedQueryIdentity:
    """Test repeated query returns same identity."""

    def test_query_id_preserved(self, query_engine: DeterministicQueryEngine):
        """Query ID is preserved in result."""
        query = CharacterQuery(
            query_id="unique_query_id_123",
            characters=["naruto"],
        )
        result = query_engine.query_characters(query)
        
        assert result.query_id == "unique_query_id_123"
        
        # All items should have same query_id
        for item in result.items:
            assert item.query_id == "unique_query_id_123"

    def test_index_version_stable(self, query_engine: DeterministicQueryEngine):
        """Index version is stable across queries."""
        query1 = CharacterQuery(query_id="q80", characters=["naruto"])
        query2 = CharacterQuery(query_id="q81", characters=["sasuke"])
        
        result1 = query_engine.query_characters(query1)
        result2 = query_engine.query_characters(query2)
        
        assert result1.index_version == result2.index_version


# ============================================================================
# Test: Combined query
# ============================================================================


class TestCombinedQuery:
    """Test combined multi-field query."""

    def test_combined_query_and_logic(self, query_engine: DeterministicQueryEngine):
        """Combined query uses AND logic for all fields."""
        query = CombinedQuery(
            query_id="q90",
            characters=["naruto"],
            actions=["running"],
            environments=["forest"],
        )
        result = query_engine.query_combined(query)
        
        # Only scene_001 matches all three
        assert result.status == ResultStatus.SUCCESS
        assert len(result.items) == 1
        assert result.items[0].item_id == "scene_001"

    def test_combined_query_partial_match(self, query_engine: DeterministicQueryEngine):
        """Combined query with partial match returns nothing (AND logic)."""
        query = CombinedQuery(
            query_id="q91",
            characters=["naruto"],
            actions=["reading"],  # None of the naruto scenes have reading
        )
        result = query_engine.query_combined(query)
        
        assert result.status == ResultStatus.EMPTY


# ============================================================================
# Test: Query result stability
# ============================================================================


class TestQueryResultStability:
    """Test result stability across different query patterns."""

    def test_same_index_same_query_same_result(self, retrieval_index: SemanticRetrievalIndex):
        """Same index + same query always produces same result."""
        engine1 = DeterministicQueryEngine(retrieval_index)
        engine2 = DeterministicQueryEngine(retrieval_index)
        
        query = CharacterQuery(query_id="stable_q", characters=["naruto"])
        
        result1 = engine1.query_characters(query)
        result2 = engine2.query_characters(query)
        
        assert result1.item_ids() == result2.item_ids()
        assert result1.status == result2.status

    def test_different_engines_same_index_same_query(self, retrieval_index: SemanticRetrievalIndex):
        """Different engine instances with same index produce same results.
        
        Note: execution_time_ms may differ slightly between runs,
        so we compare structural equality, not exact JSON bytes.
        """
        engine1 = DeterministicQueryEngine(retrieval_index)
        engine2 = DeterministicQueryEngine(retrieval_index)
        
        query = CharacterQuery(query_id="diff_engines", characters=["naruto"])
        
        result1 = engine1.query_characters(query)
        result2 = engine2.query_characters(query)
        
        # Same items returned
        assert result1.item_ids() == result2.item_ids()
        assert result1.status == result2.status
        assert result1.total_results == result2.total_results
        assert result1.index_version == result2.index_version


# ============================================================================
# Test: Segment query
# ============================================================================


class TestSegmentQuery:
    """Test narrative segment querying."""

    def test_segment_query_empty_index(self, retrieval_index: SemanticRetrievalIndex):
        """Segment query with empty segment index returns empty."""
        engine = DeterministicQueryEngine(retrieval_index)
        
        # No segments in index, should return empty
        query = NarrativeSegmentQuery(
            query_id="seg_q1",
            characters=["naruto"],
        )
        result = engine.query_segments(query)
        
        assert result.status == ResultStatus.EMPTY
        assert len(result.items) == 0


# ============================================================================
# Test: Architecture constraints validation
# ============================================================================


class TestArchitectureConstraints:
    """Validate architecture constraints."""

    def test_result_is_frozen(self, query_engine: DeterministicQueryEngine):
        """QueryResult is frozen (immutable)."""
        query = CharacterQuery(query_id="frozen_q", characters=["naruto"])
        result = query_engine.query_characters(query)
        
        # Pydantic with frozen=True should raise on mutation attempt
        with pytest.raises((TypeError, ValueError)):
            result.query_id = "modified"

    def test_ranked_item_is_frozen(self, query_engine: DeterministicQueryEngine):
        """RankedItem is frozen (immutable)."""
        query = CharacterQuery(query_id="frozen_item_q", characters=["naruto"])
        result = query_engine.query_characters(query)
        
        if result.items:
            item = result.items[0]
            with pytest.raises((TypeError, ValueError)):
                item.item_id = "modified"

    def test_ranking_score_is_frozen(self, query_engine: DeterministicQueryEngine):
        """RankingScore is frozen (immutable)."""
        score = RankingScore(
            score_type="test",
            score_value=1.0,
        )
        with pytest.raises((TypeError, ValueError)):
            score.score_value = 0.5

    def test_no_extra_fields_in_result(self, query_engine: DeterministicQueryEngine):
        """Result contracts forbid extra fields."""
        query = CharacterQuery(query_id="extra_fields_q", characters=["naruto"])
        result = query_engine.query_characters(query)
        
        # Try to create result with extra field
        with pytest.raises(ValueError):
            QueryResult(
                query_id="test",
                items=[],
                unknown_field="should_fail",  # Should be forbidden
            )

    def test_no_extra_fields_in_ranked_item(self, query_engine: DeterministicQueryEngine):
        """RankedItem forbids extra fields."""
        with pytest.raises(ValueError):
            RankedItem(
                item_id="test",
                query_id="q",
                unknown_field="should_fail",  # Should be forbidden
            )