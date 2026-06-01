"""DeterministicQueryEngine — exact-match retrieval query runtime.

Provides deterministic exact-match querying on SemanticRetrievalIndex.
All queries use normalized exact matching only — no embeddings, no vector DB,
no probabilistic retrieval, no fuzzy matching.

Architecture constraints:
- Deterministic only (same query + same index → byte-identical result)
- frozen=True for all result contracts
- extra="forbid" enforced
- Replay-safe behavior
- Stable serialization
- No hidden mutations
- Deterministic ordering (score desc, then item_id asc)
- Deterministic exact-match scoring only

Phase: 3.1c — Deterministic Query Execution Runtime
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Sequence, Set

from aicore.semantic.contracts.index_schemas import (
    ActionIndex,
    CharacterIndex,
    EnvironmentIndex,
    SceneIndex,
    SegmentIndex,
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


# ============================================================================
# Constants
# ============================================================================

SCHEMA_VERSION = "Phase3.1c"
EXACT_MATCH_SCORE = 1.0
NO_MATCH_SCORE = 0.0


# ============================================================================
# Internal helpers
# ============================================================================


def _stable_hash(content: str) -> str:
    """Generate stable SHA-256 hex digest from string content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sorted_strings(items: Optional[List[str]]) -> List[str]:
    """Return deterministically sorted copy of list."""
    if items is None:
        return []
    return sorted(items)


def _normalize_query_terms(terms: List[str]) -> List[str]:
    """Normalize query terms for exact matching."""
    return sorted(term.lower().strip() for term in terms if term and term.strip())


def _exact_match_score(
    query_terms: List[str],
    index_terms: List[str],
) -> float:
    """Compute exact-match score between query and index terms.
    
    Returns 1.0 if any query term matches any index term (normalized exact match).
    Returns 0.0 if no matches found.
    
    This is NOT fuzzy matching — uses exact string equality after normalization.
    """
    if not query_terms or not index_terms:
        return NO_MATCH_SCORE
    
    normalized_index = set(term.lower() for term in index_terms)
    for term in query_terms:
        if term.lower() in normalized_index:
            return EXACT_MATCH_SCORE
    return NO_MATCH_SCORE


def _compute_result_hash(query_id: str, item_ids: List[str]) -> str:
    """Compute deterministic hash for result identity."""
    content = f"result:{query_id}:{','.join(item_ids)}"
    return _stable_hash(content)


# ============================================================================
# DeterministicQueryEngine — main query runtime
# ============================================================================


class DeterministicQueryEngine:
    """Immutable deterministic query execution engine.

    Provides exact-match querying on SemanticRetrievalIndex:
    - query_characters: Find scenes featuring specific characters
    - query_environments: Find scenes in specific environments
    - query_actions: Find scenes with specific actions
    - query_temporal: Find scenes within time window
    - query_segments: Find narrative segments matching criteria

    All queries use normalized exact matching only.
    Results are deterministically ordered (score desc, then item_id asc).
    
    DO NOT implement:
    - ranking algorithms
    - fuzzy matching
    - semantic search
    - embeddings
    - vector DB
    - probabilistic retrieval
    """

    def __init__(self, index: SemanticRetrievalIndex) -> None:
        """Initialize query engine with retrieval index.
        
        Args:
            index: Immutable SemanticRetrievalIndex to query against
        """
        self._index = index
        self._index_version = index.index_hash[:16]

    # ── Query: Characters ───────────────────────────────────────────────────

    def query_characters(
        self,
        query: CharacterQuery,
    ) -> QueryResult:
        """Query scenes featuring specific characters.

        Uses normalized exact matching only.
        Deterministic ordering: score desc, then item_id asc.

        Args:
            query: CharacterQuery with normalized character names

        Returns:
            QueryResult with matched scene items
        """
        start_time = time.perf_counter()
        query_id = query.query_id

        # Normalize query terms
        characters = _normalize_query_terms(query.characters)
        exclude_chars = _normalize_query_terms(query.exclude_characters)

        # If no characters specified, return empty result
        if not characters:
            return self._build_empty_result(
                query_id=query_id,
                query_type="character",
                execution_time_ms=self._elapsed_ms(start_time),
            )

        # Collect matching scene IDs
        matched_items: List[RankedItem] = []

        for scene_id, scene_idx in self._index.scene_indexes.items():
            # Check if any character matches
            score = _exact_match_score(characters, scene_idx.characters)
            if score <= 0:
                continue

            # Apply exclusion filter
            excluded_fields = []
            if exclude_chars:
                for excl_char in exclude_chars:
                    if excl_char in scene_idx.characters:
                        excluded_fields.append(f"character:{excl_char}")

            if excluded_fields and len(excluded_fields) == len(exclude_chars):
                # All excluded characters present — skip
                continue

            # Apply minimum appearances filter
            if query.min_appearances > 1:
                # Count appearances in this scene
                matches = sum(1 for c in characters if c in scene_idx.characters)
                if matches < query.min_appearances:
                    continue

            # Apply temporal filter if specified
            if query.temporal_range is not None:
                if not self._scene_overlaps_temporal(scene_idx, query.temporal_range):
                    continue

            # Video/episode filter
            if query.video_id and scene_idx.video_id != query.video_id:
                continue
            if query.episode_id and scene_idx.episode_id != query.episode_id:
                continue

            # Build matched fields list
            matched_fields = [c for c in characters if c in scene_idx.characters]

            # Create ranking score component
            score_component = RankingScore(
                score_type="z_fallback",  # Deterministic exact-match signal
                score_value=score,
                weight=1.0,
                detail={
                    "query_characters": characters,
                    "matched_characters": matched_fields,
                    "match_mode": query.mode.value,
                },
            )

            # Build rank item
            item = self._build_ranked_item(
                item_id=scene_id,
                index_type="scene",
                score_components=[score_component],
                total_score=score,
                matched_fields=matched_fields,
                excluded_fields=sorted(excluded_fields),
                query_id=query_id,
                index_entry=scene_idx.to_dict_deterministic(),
            )
            matched_items.append(item)

        # Sort deterministically: score desc, then item_id asc
        matched_items = self._sort_items(matched_items)

        # Build result
        return self._build_result(
            query_id=query_id,
            query_type="character",
            items=matched_items,
            status=ResultStatus.SUCCESS if matched_items else ResultStatus.EMPTY,
            execution_time_ms=self._elapsed_ms(start_time),
        )

    # ── Query: Environments ─────────────────────────────────────────────────

    def query_environments(
        self,
        query: EnvironmentQuery,
    ) -> QueryResult:
        """Query scenes in specific environments.

        Uses normalized exact matching only.
        Deterministic ordering: score desc, then item_id asc.

        Args:
            query: EnvironmentQuery with normalized environment names

        Returns:
            QueryResult with matched scene items
        """
        start_time = time.perf_counter()
        query_id = query.query_id

        # Normalize query terms
        environments = _normalize_query_terms(query.environments)
        exclude_envs = _normalize_query_terms(query.exclude_environments)

        if not environments:
            return self._build_empty_result(
                query_id=query_id,
                query_type="environment",
                execution_time_ms=self._elapsed_ms(start_time),
            )

        matched_items: List[RankedItem] = []

        for scene_id, scene_idx in self._index.scene_indexes.items():
            # Check environment match
            score = _exact_match_score(environments, scene_idx.environments)
            if score <= 0:
                continue

            # Apply exclusion filter
            excluded_fields = []
            if exclude_envs:
                for excl_env in exclude_envs:
                    if excl_env in scene_idx.environments:
                        excluded_fields.append(f"environment:{excl_env}")

            if excluded_fields and len(excluded_fields) == len(exclude_envs):
                continue

            # Additional environment filters
            if query.location_class and scene_idx.narrative_event_type != query.location_class:
                continue  # Using narrative_event_type as proxy for location class

            # Video/episode filter
            if query.video_id and scene_idx.video_id != query.video_id:
                continue
            if query.episode_id and scene_idx.episode_id != query.episode_id:
                continue

            # Build matched fields
            matched_fields = [e for e in environments if e in scene_idx.environments]

            # Create score component
            score_component = RankingScore(
                score_type="z_fallback",
                score_value=score,
                weight=1.0,
                detail={
                    "query_environments": environments,
                    "matched_environments": matched_fields,
                    "match_mode": query.mode.value,
                },
            )

            item = self._build_ranked_item(
                item_id=scene_id,
                index_type="scene",
                score_components=[score_component],
                total_score=score,
                matched_fields=matched_fields,
                excluded_fields=sorted(excluded_fields),
                query_id=query_id,
                index_entry=scene_idx.to_dict_deterministic(),
            )
            matched_items.append(item)

        matched_items = self._sort_items(matched_items)

        return self._build_result(
            query_id=query_id,
            query_type="environment",
            items=matched_items,
            status=ResultStatus.SUCCESS if matched_items else ResultStatus.EMPTY,
            execution_time_ms=self._elapsed_ms(start_time),
        )

    # ── Query: Actions ──────────────────────────────────────────────────────

    def query_actions(
        self,
        query: ActionQuery,
    ) -> QueryResult:
        """Query scenes with specific actions.

        Uses normalized exact matching only.
        Deterministic ordering: score desc, then item_id asc.

        Args:
            query: ActionQuery with normalized action names

        Returns:
            QueryResult with matched scene items
        """
        start_time = time.perf_counter()
        query_id = query.query_id

        # Normalize query terms
        actions = _normalize_query_terms(query.actions)
        exclude_actions = _normalize_query_terms(query.exclude_actions)

        if not actions:
            return self._build_empty_result(
                query_id=query_id,
                query_type="action",
                execution_time_ms=self._elapsed_ms(start_time),
            )

        matched_items: List[RankedItem] = []

        for scene_id, scene_idx in self._index.scene_indexes.items():
            # Check action match
            score = _exact_match_score(actions, scene_idx.actions)
            if score <= 0:
                continue

            # Apply minimum intensity filter
            if query.min_intensity > 0 and scene_idx.motion_intensity < query.min_intensity:
                continue

            # Apply action pace filter
            if query.action_pace and scene_idx.action_pace != query.action_pace:
                continue

            # Apply exclusion filter
            excluded_fields = []
            if exclude_actions:
                for excl_action in exclude_actions:
                    if excl_action in scene_idx.actions:
                        excluded_fields.append(f"action:{excl_action}")

            if excluded_fields and len(excluded_fields) == len(exclude_actions):
                continue

            # Video/episode filter
            if query.video_id and scene_idx.video_id != query.video_id:
                continue
            if query.episode_id and scene_idx.episode_id != query.episode_id:
                continue

            # Build matched fields
            matched_fields = [a for a in actions if a in scene_idx.actions]

            # Create score component
            score_component = RankingScore(
                score_type="z_fallback",
                score_value=score,
                weight=1.0,
                detail={
                    "query_actions": actions,
                    "matched_actions": matched_fields,
                    "match_mode": query.mode.value,
                },
            )

            item = self._build_ranked_item(
                item_id=scene_id,
                index_type="scene",
                score_components=[score_component],
                total_score=score,
                matched_fields=matched_fields,
                excluded_fields=sorted(excluded_fields),
                query_id=query_id,
                index_entry=scene_idx.to_dict_deterministic(),
            )
            matched_items.append(item)

        matched_items = self._sort_items(matched_items)

        return self._build_result(
            query_id=query_id,
            query_type="action",
            items=matched_items,
            status=ResultStatus.SUCCESS if matched_items else ResultStatus.EMPTY,
            execution_time_ms=self._elapsed_ms(start_time),
        )

    # ── Query: Temporal ────────────────────────────────────────────────────

    def query_temporal(
        self,
        query: TemporalQuery,
    ) -> QueryResult:
        """Query scenes within temporal range.

        Uses exact temporal range matching only.
        Deterministic ordering: score desc, then item_id asc.

        Args:
            query: TemporalQuery with time window

        Returns:
            QueryResult with matched scene items
        """
        start_time = time.perf_counter()
        query_id = query.query_id
        temporal_range = query.temporal_range

        matched_items: List[RankedItem] = []

        for scene_id, scene_idx in self._index.scene_indexes.items():
            # Check temporal overlap
            overlaps = self._scene_overlaps_temporal(scene_idx, temporal_range)
            if not overlaps:
                continue

            # Check adjacent scenes if requested
            score = EXACT_MATCH_SCORE
            adjacent = False
            if query.include_adjacent:
                adjacent = self._scene_adjacent_to_temporal(
                    scene_idx, temporal_range, query.gap_tolerance_ms / 1000.0
                )
                if adjacent:
                    score = EXACT_MATCH_SCORE * 0.5  # Slight penalty for adjacent

            # Video/episode filter
            if query.video_id and scene_idx.video_id != query.video_id:
                continue
            if query.episode_id and scene_idx.episode_id != query.episode_id:
                continue

            # Create score component
            score_component = RankingScore(
                score_type="m_temporal",
                score_value=score,
                weight=1.0,
                detail={
                    "temporal_range": {
                        "start_time": temporal_range.start_time,
                        "end_time": temporal_range.end_time,
                    },
                    "scene_start": scene_idx.start_time,
                    "scene_end": scene_idx.end_time,
                    "is_adjacent": adjacent,
                },
            )

            item = self._build_ranked_item(
                item_id=scene_id,
                index_type="scene",
                score_components=[score_component],
                total_score=score,
                matched_fields=["temporal_range"],
                excluded_fields=[],
                query_id=query_id,
                index_entry=scene_idx.to_dict_deterministic(),
            )
            matched_items.append(item)

        matched_items = self._sort_items(matched_items)

        return self._build_result(
            query_id=query_id,
            query_type="temporal",
            items=matched_items,
            status=ResultStatus.SUCCESS if matched_items else ResultStatus.EMPTY,
            execution_time_ms=self._elapsed_ms(start_time),
        )

    # ── Query: Segments ────────────────────────────────────────────────────

    def query_segments(
        self,
        query: NarrativeSegmentQuery,
    ) -> QueryResult:
        """Query narrative segments matching criteria.

        Uses normalized exact matching only.
        Deterministic ordering: score desc, then item_id asc.

        Args:
            query: NarrativeSegmentQuery with segment criteria

        Returns:
            QueryResult with matched segment items
        """
        start_time = time.perf_counter()
        query_id = query.query_id

        # Normalize query terms
        characters = _normalize_query_terms(query.characters)
        environments = _normalize_query_terms(query.environments)
        transition_types = _normalize_query_terms(query.transition_types)
        exclude_segments = _normalize_query_terms(query.exclude_segments)

        # If no segment indexes available, return empty
        if not self._index.segment_indexes:
            return self._build_empty_result(
                query_id=query_id,
                query_type="segment",
                execution_time_ms=self._elapsed_ms(start_time),
            )

        matched_items: List[RankedItem] = []

        for segment_id, segment_idx in self._index.segment_indexes.items():
            # Check exclusion
            if segment_id in exclude_segments:
                continue

            # Track matches
            matched_fields = []
            total_score = 0.0
            score_count = 0

            # Character match
            if characters:
                score = _exact_match_score(characters, segment_idx.dominant_characters)
                if score > 0:
                    matched_fields.extend(
                        c for c in characters if c in segment_idx.dominant_characters
                    )
                    total_score += score
                    score_count += 1

            # Continuity score filter
            if query.min_continuity_score > 0:
                if segment_idx.continuity_score < query.min_continuity_score:
                    continue

            # Transition type filter
            if transition_types:
                if segment_idx.transition_type not in transition_types:
                    continue
                matched_fields.append(f"transition:{segment_idx.transition_type}")

            # Calculate average score
            avg_score = total_score / score_count if score_count > 0 else 0.0
            if avg_score <= 0 and (characters or environments):
                continue  # No matching criteria met

            # Video filter from first scene in segment
            if query.video_id or query.episode_id:
                scene_ids = segment_idx.scene_ids
                if scene_ids:
                    first_scene = self._index.get_scene(scene_ids[0])
                    if first_scene:
                        if query.video_id and first_scene.video_id != query.video_id:
                            continue
                        if query.episode_id and first_scene.episode_id != query.episode_id:
                            continue

            # Create score component
            score_component = RankingScore(
                score_type="z_fallback",
                score_value=avg_score,
                weight=1.0,
                detail={
                    "matched_characters": matched_fields,
                    "continuity_score": segment_idx.continuity_score,
                },
            )

            item = self._build_ranked_item(
                item_id=segment_id,
                index_type="segment",
                score_components=[score_component],
                total_score=avg_score,
                matched_fields=sorted(set(matched_fields)),
                excluded_fields=[],
                query_id=query_id,
                index_entry=segment_idx.to_dict_deterministic(),
            )
            matched_items.append(item)

        matched_items = self._sort_items(matched_items)

        return self._build_result(
            query_id=query_id,
            query_type="segment",
            items=matched_items,
            status=ResultStatus.SUCCESS if matched_items else ResultStatus.EMPTY,
            execution_time_ms=self._elapsed_ms(start_time),
        )

    # ── Combined query ─────────────────────────────────────────────────────

    def query_combined(
        self,
        query: CombinedQuery,
    ) -> QueryResult:
        """Query scenes matching combined criteria.

        All conditions are ANDed together using exact matching.
        Deterministic ordering: score desc, then item_id asc.

        Args:
            query: CombinedQuery with multi-field criteria

        Returns:
            QueryResult with matched scene items
        """
        start_time = time.perf_counter()
        query_id = query.query_id

        # Normalize query terms
        characters = _normalize_query_terms(query.characters)
        actions = _normalize_query_terms(query.actions)
        environments = _normalize_query_terms(query.environments)
        exclude_scene_ids = set(query.exclude_scene_ids)

        matched_items: List[RankedItem] = []

        for scene_id, scene_idx in self._index.scene_indexes.items():
            # Exclusion filter
            if scene_id in exclude_scene_ids:
                continue

            # Track all scoring components
            score_components: List[RankingScore] = []
            matched_fields: List[str] = []
            total_score = 0.0
            score_count = 0

            # Character match
            if characters:
                score = _exact_match_score(characters, scene_idx.characters)
                if score > 0:
                    matched = [c for c in characters if c in scene_idx.characters]
                    matched_fields.extend(matched)
                    total_score += score
                    score_count += 1
                    score_components.append(
                        RankingScore(
                            score_type="a_overlap",
                            score_value=score,
                            weight=1.0,
                            detail={"matched": matched},
                        )
                    )
                else:
                    continue  # Character mismatch — AND logic

            # Action match
            if actions:
                score = _exact_match_score(actions, scene_idx.actions)
                if score > 0:
                    matched = [a for a in actions if a in scene_idx.actions]
                    matched_fields.extend(matched)
                    total_score += score
                    score_count += 1
                    score_components.append(
                        RankingScore(
                            score_type="a_overlap",
                            score_value=score,
                            weight=1.0,
                            detail={"matched": matched},
                        )
                    )
                else:
                    continue  # Action mismatch — AND logic

            # Environment match
            if environments:
                score = _exact_match_score(environments, scene_idx.environments)
                if score > 0:
                    matched = [e for e in environments if e in scene_idx.environments]
                    matched_fields.extend(matched)
                    total_score += score
                    score_count += 1
                    score_components.append(
                        RankingScore(
                            score_type="a_overlap",
                            score_value=score,
                            weight=1.0,
                            detail={"matched": matched},
                        )
                    )
                else:
                    continue  # Environment mismatch — AND logic

            # Motion intensity filter
            if query.motion_intensity_min > 0:
                if scene_idx.motion_intensity < query.motion_intensity_min:
                    continue

            # Temporal range filter
            if query.temporal_range is not None:
                if not self._scene_overlaps_temporal(scene_idx, query.temporal_range):
                    continue
                matched_fields.append("temporal_range")
                score_components.append(
                    RankingScore(
                        score_type="m_temporal",
                        score_value=EXACT_MATCH_SCORE,
                        weight=1.0,
                        detail={"range": query.temporal_range.model_dump()},
                    )
                )

            # Narrative type filter
            if query.narrative_event_type:
                if scene_idx.narrative_event_type != query.narrative_event_type:
                    continue
                matched_fields.append(f"narrative:{query.narrative_event_type}")

            # Calculate average score across matched criteria
            avg_score = total_score / score_count if score_count > 0 else 0.0
            if avg_score <= 0 and (characters or actions or environments):
                continue  # No matching criteria

            # Video/episode filter
            if query.video_id and scene_idx.video_id != query.video_id:
                continue
            if query.episode_id and scene_idx.episode_id != query.episode_id:
                continue

            item = self._build_ranked_item(
                item_id=scene_id,
                index_type="scene",
                score_components=score_components,
                total_score=avg_score,
                matched_fields=sorted(set(matched_fields)),
                excluded_fields=[],
                query_id=query_id,
                index_entry=scene_idx.to_dict_deterministic(),
            )
            matched_items.append(item)

        matched_items = self._sort_items(matched_items)

        return self._build_result(
            query_id=query_id,
            query_type="combined",
            items=matched_items,
            status=ResultStatus.SUCCESS if matched_items else ResultStatus.EMPTY,
            execution_time_ms=self._elapsed_ms(start_time),
        )

    # ── Temporal helpers ───────────────────────────────────────────────────

    def _scene_overlaps_temporal(
        self,
        scene_idx: SceneIndex,
        temporal_range: TemporalRange,
    ) -> bool:
        """Check if scene overlaps with temporal range.
        
        Returns True if scene has any overlap with the time window.
        """
        return (
            scene_idx.start_time < temporal_range.end_time
            and scene_idx.end_time > temporal_range.start_time
        )

    def _scene_adjacent_to_temporal(
        self,
        scene_idx: SceneIndex,
        temporal_range: TemporalRange,
        gap_tolerance: float,
    ) -> bool:
        """Check if scene is adjacent to temporal range within gap tolerance."""
        # Scene ends just before range starts
        before = (
            abs(scene_idx.end_time - temporal_range.start_time) <= gap_tolerance
            and scene_idx.end_time <= temporal_range.start_time
        )
        # Scene starts just after range ends
        after = (
            abs(scene_idx.start_time - temporal_range.end_time) <= gap_tolerance
            and scene_idx.start_time >= temporal_range.end_time
        )
        return before or after

    # ── Result building helpers ────────────────────────────────────────────

    def _build_ranked_item(
        self,
        item_id: str,
        index_type: str,
        score_components: List[RankingScore],
        total_score: float,
        matched_fields: List[str],
        excluded_fields: List[str],
        query_id: str,
        index_entry: Dict[str, Any],
    ) -> RankedItem:
        """Build deterministic RankedItem."""
        return RankedItem(
            item_id=item_id,
            index_type=index_type,
            score_components=sorted(score_components, key=lambda c: c.score_type),
            total_score=total_score,
            matched_fields=sorted(matched_fields),
            excluded_fields=sorted(excluded_fields),
            query_id=query_id,
            index_entry_snapshot=index_entry,
        )

    def _build_result(
        self,
        query_id: str,
        query_type: str,
        items: List[RankedItem],
        status: ResultStatus,
        execution_time_ms: float,
        error_message: Optional[str] = None,
    ) -> QueryResult:
        """Build deterministic QueryResult."""
        total_results = len(items)
        
        return QueryResult(
            query_id=query_id,
            query_type=query_type,
            items=items,
            status=status,
            error_message=error_message,
            total_results=total_results,
            match_count=total_results,
            coverage=min(total_results / max(self._index.scene_count, 1), 1.0),
            index_version=self._index_version,
            execution_time_ms=execution_time_ms,
        )

    def _build_empty_result(
        self,
        query_id: str,
        query_type: str,
        execution_time_ms: float,
    ) -> QueryResult:
        """Build empty QueryResult."""
        return QueryResult(
            query_id=query_id,
            query_type=query_type,
            items=[],
            status=ResultStatus.EMPTY,
            total_results=0,
            match_count=0,
            coverage=0.0,
            index_version=self._index_version,
            execution_time_ms=execution_time_ms,
        )

    def _sort_items(self, items: List[RankedItem]) -> List[RankedItem]:
        """Sort items deterministically: score desc, then item_id asc."""
        return sorted(items, key=lambda i: (-i.total_score, i.item_id))

    def _elapsed_ms(self, start_time: float) -> float:
        """Get elapsed time in milliseconds."""
        return (time.perf_counter() - start_time) * 1000.0

    # ── Replay-safe identity ───────────────────────────────────────────────

    def compute_query_hash(self, query_id: str, query_dict: Dict[str, Any]) -> str:
        """Compute deterministic hash for query replay identity.
        
        Args:
            query_id: Unique query identifier
            query_dict: Deterministic query dict
            
        Returns:
            SHA-256 hex digest for replay tracking
        """
        content = json.dumps(
            {"query_id": query_id, "query": query_dict},
            sort_keys=True,
            default=str,
        )
        return _stable_hash(content)