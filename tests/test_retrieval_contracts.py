"""Schema-only tests for retrieval contracts.

Validates:
- frozen=True — models are truly immutable
- extra="forbid" — no unexpected fields allowed
- deterministic ordering — to_dict / to_json produce stable output
- replay-safe serialisation — same data → byte-identical result
- field validation — ge/le constraints enforced
- type dispatch — registries are correct
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from aicore.semantic.contracts.index_schemas import (
    SceneIndex,
    SegmentIndex,
    ContinuityIndex,
    CharacterIndex,
    EnvironmentIndex,
    ActionIndex,
    INDEX_TYPE_NAMES,
    INDEX_TYPE_MAP,
)
from aicore.semantic.contracts.query_contracts import (
    CharacterQuery,
    EnvironmentQuery,
    ActionQuery,
    TemporalQuery,
    NarrativeSegmentQuery,
    CombinedQuery,
    TemporalRange,
    QueryMode,
    QUERY_TYPE_NAMES,
    QUERY_TYPE_MAP,
)
from aicore.semantic.contracts.result_contracts import (
    QueryResult,
    RankedItem,
    RankingScore,
    ResultStatus,
)


# =========================================================================
# Helper fixtures
# =========================================================================


@pytest.fixture
def sample_scene_index() -> SceneIndex:
    return SceneIndex(
        scene_id="scene_001",
        video_id="video_01",
        episode_id="ep_01",
        start_time=10.0,
        end_time=30.0,
        duration=20.0,
        characters=["naruto", "sasuke"],
        actions=["punch", "kick"],
        environments=["forest"],
        objects=["kunai"],
        emotions=["angry"],
        tags=["battle", "ninja"],
        dialogue_snippet="I will never give up!",
        ocr_snippet="Hidden Leaf Village",
        motion_intensity=0.8,
        action_pace="fast",
        narrative_event_type="combat",
    )


# =========================================================================
# 1. Immutability tests (frozen=True)
# =========================================================================


class TestFrozenModels:
    """All retrieval contracts must be truly immutable."""

    @pytest.mark.parametrize(
        "model_cls, kwargs",
        [
            (
                SceneIndex,
                {
                    "scene_id": "s1",
                    "video_id": "v1",
                    "start_time": 0.0,
                    "end_time": 10.0,
                },
            ),
            (
                SegmentIndex,
                {"segment_id": "seg1", "scene_ids": ["s1", "s2"]},
            ),
            (
                ContinuityIndex,
                {"chain_id": "c1", "scene_ids": ["s1"]},
            ),
            (
                CharacterIndex,
                {"normalized_name": "naruto"},
            ),
            (
                EnvironmentIndex,
                {"normalized_name": "forest"},
            ),
            (
                ActionIndex,
                {"normalized_name": "punch"},
            ),
        ],
    )
    def test_cannot_mutate(self, model_cls, kwargs):
        inst = model_cls(**kwargs)
        with pytest.raises(ValidationError):
            inst.schema_version = "hacked"

    @pytest.mark.parametrize(
        "model_cls, kwargs",
        [
            (
                CharacterQuery,
                {"query_id": "q1", "characters": ["naruto"]},
            ),
            (
                EnvironmentQuery,
                {"query_id": "q1", "environments": ["forest"]},
            ),
            (
                ActionQuery,
                {"query_id": "q1", "actions": ["punch"]},
            ),
        ],
    )
    def test_query_cannot_mutate(self, model_cls, kwargs):
        inst = model_cls(**kwargs)
        with pytest.raises(ValidationError):
            inst.query_id = "hacked"

    def test_result_status_immutable(self):
        inst = QueryResult(query_id="q1", query_type="character")
        with pytest.raises(ValidationError):
            inst.status = ResultStatus.ERROR

    def test_ranked_item_immutable(self):
        inst = RankedItem(
            item_id="s1",
            index_type="scene",
            total_score=0.5,
            query_id="q1",
        )
        with pytest.raises(ValidationError):
            inst.total_score = 1.0

    def test_ranking_score_immutable(self):
        inst = RankingScore(score_type="overlap", score_value=0.5)
        with pytest.raises(ValidationError):
            inst.score_value = 0.8


# =========================================================================
# 2. Extra fields forbidden (extra="forbid")
# =========================================================================


class TestExtraFieldsForbidden:
    """No retrieval contract should accept undeclared fields."""

    @pytest.mark.parametrize(
        "model_cls, base_kwargs",
        [
            (
                SceneIndex,
                {
                    "scene_id": "s1",
                    "video_id": "v1",
                    "start_time": 0.0,
                    "end_time": 10.0,
                },
            ),
            (
                SegmentIndex,
                {"segment_id": "seg1", "scene_ids": ["s1"]},
            ),
            (
                ContinuityIndex,
                {"chain_id": "c1", "scene_ids": ["s1"]},
            ),
            (
                CharacterIndex,
                {"normalized_name": "naruto"},
            ),
            (
                EnvironmentIndex,
                {"normalized_name": "forest"},
            ),
            (
                ActionIndex,
                {"normalized_name": "punch"},
            ),
            (
                CharacterQuery,
                {"query_id": "q1", "characters": ["naruto"]},
            ),
            (
                EnvironmentQuery,
                {"query_id": "q1", "environments": ["forest"]},
            ),
            (
                ActionQuery,
                {"query_id": "q1", "actions": ["punch"]},
            ),
            (
                TemporalQuery,
                {
                    "query_id": "q1",
                    "temporal_range": {"start_time": 0.0, "end_time": 10.0},
                },
            ),
        ],
    )
    def test_extra_field_raises(self, model_cls, base_kwargs):
        with pytest.raises(ValidationError):
            model_cls(**base_kwargs, rogue_field="should not exist")


# =========================================================================
# 3. Deterministic serialisation
# =========================================================================


class TestDeterministicSerialization:
    """to_dict_deterministic and to_json must produce stable output."""

    def test_scene_index_deterministic_dict(self):
        idx = SceneIndex(
            scene_id="s1",
            video_id="v1",
            start_time=0.0,
            end_time=10.0,
            characters=["sasuke", "naruto"],
        )
        d1 = idx.to_dict_deterministic()
        d2 = idx.to_dict_deterministic()
        assert d1 == d2
        # Characters must be sorted
        assert d1["characters"] == ["naruto", "sasuke"]
        # Keys must be sorted
        keys = list(d1.keys())
        assert keys == sorted(keys)

    def test_scene_index_deterministic_json(self):
        idx = SceneIndex(
            scene_id="s1",
            video_id="v1",
            start_time=0.0,
            end_time=10.0,
        )
        j1 = idx.to_json()
        j2 = idx.to_json()
        assert j1 == j2
        # Parsed JSON must have same content
        assert json.loads(j1) == json.loads(j2)

    def test_character_index_deterministic(self):
        idx = CharacterIndex(
            normalized_name="naruto",
            aliases=["uzumaki naruto", "kyuubi host"],
            scene_ids=["s3", "s1", "s2"],
        )
        d = idx.to_dict_deterministic()
        # Should be sorted
        assert d["aliases"] == sorted(d["aliases"])
        assert d["scene_ids"] == sorted(d["scene_ids"])

    def test_ranked_item_deterministic(self):
        item = RankedItem(
            item_id="s1",
            index_type="scene",
            total_score=0.8,
            query_id="q1",
            score_components=[
                RankingScore(score_type="z_fallback", score_value=0.1),
                RankingScore(score_type="a_overlap", score_value=0.9),
                RankingScore(score_type="m_temporal", score_value=0.5),
            ],
            matched_fields=["z_field", "a_field"],
        )
        d = item.to_dict_deterministic()
        # Score components must be sorted by score_type
        types = [c["score_type"] for c in d["score_components"]]
        assert types == sorted(types)
        # Matched fields must be sorted
        assert d["matched_fields"] == sorted(d["matched_fields"])

    def test_query_result_deterministic(self):
        result = QueryResult(
            query_id="q1",
            query_type="character",
            items=[
                RankedItem(
                    item_id="s2",
                    index_type="scene",
                    total_score=0.5,
                    query_id="q1",
                ),
                RankedItem(
                    item_id="s1",
                    index_type="scene",
                    total_score=0.9,
                    query_id="q1",
                ),
                RankedItem(
                    item_id="s3",
                    index_type="scene",
                    total_score=0.5,
                    query_id="q1",
                ),
            ],
        )
        d = result.to_dict_deterministic()
        item_ids = [i["item_id"] for i in d["items"]]
        # Sort: total_score desc → item_id asc
        assert item_ids == ["s1", "s2", "s3"]

    def test_query_result_replay_safe(self):
        """Same data → byte-identical JSON."""
        r1 = QueryResult(query_id="q1", query_type="character")
        r2 = QueryResult(query_id="q1", query_type="character")
        assert r1.to_json() == r2.to_json()

    def test_temporal_query_deterministic(self):
        q = TemporalQuery(
            query_id="q1",
            temporal_range={"start_time": 5.0, "end_time": 15.0},
        )
        d1 = q.to_dict_deterministic()
        d2 = q.to_dict_deterministic()
        assert d1 == d2


# =========================================================================
# 4. Field validation — numeric constraints
# =========================================================================


class TestFieldValidation:
    """Numeric ge/le constraints must be enforced."""

    def test_scene_negative_time(self):
        with pytest.raises(ValidationError):
            SceneIndex(
                scene_id="s1",
                video_id="v1",
                start_time=-1.0,
                end_time=10.0,
            )

    def test_temporal_end_gte_start(self):
        with pytest.raises(ValidationError):
            TemporalRange(start_time=30.0, end_time=10.0)

    def test_score_out_of_range(self):
        with pytest.raises(ValidationError):
            RankingScore(score_type="overlap", score_value=1.5)

    def test_negative_weight(self):
        with pytest.raises(ValidationError):
            RankingScore(score_type="overlap", score_value=0.5, weight=-1.0)

    def test_motion_intensity_out_of_range(self):
        with pytest.raises(ValidationError):
            SceneIndex(
                scene_id="s1",
                video_id="v1",
                start_time=0.0,
                end_time=10.0,
                motion_intensity=1.5,
            )

    def test_action_pace_invalid(self):
        """Test a valid string for action_pace — no enum enforcement yet."""
        idx = SceneIndex(
            scene_id="s1",
            video_id="v1",
            start_time=0.0,
            end_time=10.0,
            action_pace="intense",
        )
        assert idx.action_pace == "intense"

    def test_continuity_score_range(self):
        with pytest.raises(ValidationError):
            SegmentIndex(
                segment_id="seg1",
                continuity_score=-0.1,
            )


# =========================================================================
# 5. Type dispatch — registries must be correct
# =========================================================================


class TestTypeRegistries:
    """INDEX_TYPE_MAP and QUERY_TYPE_MAP must contain correct types."""

    def test_index_type_map_count(self):
        assert len(INDEX_TYPE_MAP) == 6
        assert len(INDEX_TYPE_NAMES) == 6

    def test_index_type_map_keys(self):
        assert INDEX_TYPE_MAP["scene"] is SceneIndex
        assert INDEX_TYPE_MAP["segment"] is SegmentIndex
        assert INDEX_TYPE_MAP["continuity"] is ContinuityIndex
        assert INDEX_TYPE_MAP["character"] is CharacterIndex
        assert INDEX_TYPE_MAP["environment"] is EnvironmentIndex
        assert INDEX_TYPE_MAP["action"] is ActionIndex

    def test_index_type_names_ordered(self):
        assert INDEX_TYPE_NAMES == [
            "scene",
            "segment",
            "continuity",
            "character",
            "environment",
            "action",
        ]

    def test_query_type_map_count(self):
        assert len(QUERY_TYPE_MAP) == 6
        assert len(QUERY_TYPE_NAMES) == 6

    def test_query_type_map_keys(self):
        assert QUERY_TYPE_MAP["character"] is CharacterQuery
        assert QUERY_TYPE_MAP["environment"] is EnvironmentQuery
        assert QUERY_TYPE_MAP["action"] is ActionQuery
        assert QUERY_TYPE_MAP["temporal"] is TemporalQuery
        assert QUERY_TYPE_MAP["narrative_segment"] is NarrativeSegmentQuery
        assert QUERY_TYPE_MAP["combined"] is CombinedQuery


# =========================================================================
# 6. Default values and edge cases
# =========================================================================


class TestDefaultValues:
    """Models should have sensible defaults for optional fields."""

    def test_scene_index_defaults(self):
        idx = SceneIndex(
            scene_id="s1",
            video_id="v1",
            start_time=0.0,
            end_time=10.0,
        )
        assert idx.duration == 0.0
        assert idx.characters == []
        assert idx.motion_intensity == 0.0
        assert idx.action_pace == "slow"
        assert idx.schema_version == "Phase3.1"

    def test_segment_index_defaults(self):
        seg = SegmentIndex(segment_id="seg1")
        assert seg.continuity_score == 0.0
        assert seg.transition_type == "unknown"
        assert seg.dominant_environment == "unknown"

    def test_character_index_defaults(self):
        ci = CharacterIndex(normalized_name="naruto")
        assert ci.appearance_count == 0
        assert ci.average_confidence == 0.0
        assert ci.first_appearance == 0.0

    def test_query_result_defaults(self):
        r = QueryResult(query_id="q1", query_type="scene")
        assert r.status == ResultStatus.SUCCESS
        assert r.items == []
        assert r.total_results == 0
        assert r.match_count == 0
        assert r.coverage == 0.0

    def test_ranking_score_defaults(self):
        s = RankingScore(score_type="overlap", score_value=0.5)
        assert s.weight == 1.0
        assert s.detail is None

    def test_query_mode_enum(self):
        assert QueryMode.EXACT == "exact"
        assert QueryMode.OVERLAP == "overlap"
        assert QueryMode.INTERSECTION == "intersection"

    def test_result_status_enum(self):
        assert ResultStatus.SUCCESS == "success"
        assert ResultStatus.EMPTY == "empty"
        assert ResultStatus.ERROR == "error"
        assert ResultStatus.PARTIAL == "partial"


# =========================================================================
# 7. Construction and serialisation round-trips
# =========================================================================


class TestRoundTrip:
    """Construct → serialise → deserialise should preserve data."""

    def test_scene_index_roundtrip(self):
        idx = SceneIndex(
            scene_id="scene_001",
            video_id="video_01",
            start_time=10.0,
            end_time=30.0,
            characters=["naruto"],
            actions=["punch"],
        )
        raw = idx.model_dump(mode="json")
        restored = SceneIndex.model_validate(raw)
        assert idx.model_dump() == restored.model_dump()

    def test_character_query_roundtrip(self):
        q = CharacterQuery(
            query_id="q1",
            characters=["naruto", "sasuke"],
            min_appearances=2,
        )
        raw = q.model_dump(mode="json")
        restored = CharacterQuery.model_validate(raw)
        assert q.model_dump() == restored.model_dump()

    def test_query_result_roundtrip(self):
        r = QueryResult(
            query_id="q1",
            query_type="character",
            items=[
                RankedItem(
                    item_id="s1",
                    index_type="scene",
                    total_score=0.9,
                    query_id="q1",
                    score_components=[
                        RankingScore(
                            score_type="overlap",
                            score_value=0.8,
                            weight=1.0,
                        ),
                    ],
                ),
            ],
            status=ResultStatus.SUCCESS,
            total_results=1,
            match_count=1,
        )
        raw = r.model_dump(mode="json")
        restored = QueryResult.model_validate(raw)
        assert r.model_dump() == restored.model_dump()

    def test_empty_query_result_roundtrip(self):
        r = QueryResult(query_id="q0", query_type="scene", status=ResultStatus.EMPTY)
        j = r.to_json()
        assert json.loads(j) is not None


# =========================================================================
# 8. Convenience accessors
# =========================================================================


class TestConvenienceAccessors:
    """QueryResult convenience properties should work correctly."""

    def test_is_empty_true(self):
        r = QueryResult(query_id="q1", query_type="scene", status=ResultStatus.EMPTY)
        assert r.is_empty

    def test_is_empty_false(self):
        r = QueryResult(query_id="q1", query_type="scene")
        assert not r.is_empty

    def test_is_success_true(self):
        r = QueryResult(
            query_id="q1",
            query_type="scene",
            items=[
                RankedItem(
                    item_id="s1",
                    index_type="scene",
                    total_score=0.5,
                    query_id="q1",
                ),
            ],
        )
        assert r.is_success

    def test_is_success_empty_items(self):
        r = QueryResult(query_id="q1", query_type="scene")
        assert not r.is_success

    def test_top_item_returns_highest(self):
        r = QueryResult(
            query_id="q1",
            query_type="scene",
            items=[
                RankedItem(
                    item_id="s2",
                    index_type="scene",
                    total_score=0.5,
                    query_id="q1",
                ),
                RankedItem(
                    item_id="s1",
                    index_type="scene",
                    total_score=0.9,
                    query_id="q1",
                ),
            ],
        )
        assert r.top_item is not None
        assert r.top_item.item_id == "s1"

    def test_top_item_none_when_empty(self):
        r = QueryResult(query_id="q1", query_type="scene")
        assert r.top_item is None

    def test_item_ids_returns_ordered(self):
        r = QueryResult(
            query_id="q1",
            query_type="scene",
            items=[
                RankedItem(
                    item_id="s2",
                    index_type="scene",
                    total_score=0.3,
                    query_id="q1",
                ),
                RankedItem(
                    item_id="s1",
                    index_type="scene",
                    total_score=0.9,
                    query_id="q1",
                ),
            ],
        )
        assert r.item_ids() == ["s1", "s2"]