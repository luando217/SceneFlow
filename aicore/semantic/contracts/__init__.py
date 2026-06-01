"""Contracts — typed extraction payloads and node metadata
for semantic nodes."""

from aicore.semantic.contracts.extraction_result import ExtractionResult
from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.contracts.node_metadata import NodeMetadata
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
    BaseQuery,
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

__all__ = [
    "ExtractionResult",
    "SemanticPatch",
    "NodeMetadata",
    "SceneIndex",
    "SegmentIndex",
    "ContinuityIndex",
    "CharacterIndex",
    "EnvironmentIndex",
    "ActionIndex",
    "INDEX_TYPE_NAMES",
    "INDEX_TYPE_MAP",
    "BaseQuery",
    "CharacterQuery",
    "EnvironmentQuery",
    "ActionQuery",
    "TemporalQuery",
    "NarrativeSegmentQuery",
    "CombinedQuery",
    "TemporalRange",
    "QueryMode",
    "QUERY_TYPE_NAMES",
    "QUERY_TYPE_MAP",
    "QueryResult",
    "RankedItem",
    "RankingScore",
    "ResultStatus",
]
