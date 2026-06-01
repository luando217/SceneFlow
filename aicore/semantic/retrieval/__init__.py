"""Semantic retrieval module — Phase 3.1c deterministic query engine.

This module provides deterministic retrieval querying runtime.

Architecture:
- Deterministic only (same input → same output)
- frozen=True for all index entries and results
- extra="forbid" enforced
- Replay-safe behavior
- Stable serialization
- No hidden mutations
- No probabilistic logic
- No embeddings
- No vector DB
- No fuzzy matching
- Exact normalized matching only
"""

from aicore.semantic.retrieval.index_builder import (
    SemanticRetrievalIndex,
)
from aicore.semantic.retrieval.query_engine import (
    DeterministicQueryEngine,
)

__all__ = [
    "DeterministicQueryEngine",
    "SemanticRetrievalIndex",
]