"""SemanticSnapshot — immutable versioned semantic state of a scene.

Records:
- Semantic state (final SceneSemantic)
- Patches that produced it
- Lineage (parent version)
- Reproducibility metadata (hashes)
- Timestamp and creator
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from aicore.semantic.contracts.semantic_patch import SemanticPatch
from aicore.semantic.schemas.scene_semantic import SceneSemantic


class SemanticSnapshot(BaseModel):
    """Single immutable version of a scene's semantic state.

    Properties:
    - Frozen after creation (frozen=True)
    - References patches that produced it
    - Tracks parent version (for lineage)
    - Stores deterministic hashes for replay verification
    - Serializable to JSON for caching
    """

    # ── Identity ──────────────────────────────────────────────────
    scene_id: str = Field(
        ..., description="Unique scene identifier"
    )
    version: str = Field(
        ..., description="Version string (e.g. 'v1.0', 'v1.1')"
    )

    # ── Semantic state ────────────────────────────────────────────
    semantic_state: SceneSemantic = Field(
        ..., description="The final frozen semantic state"
    )

    # ── Lineage ───────────────────────────────────────────────────
    parent_version: Optional[str] = Field(
        default=None,
        description="Which version this evolved from (None if root)",
    )
    patches_applied: List[SemanticPatch] = Field(
        default_factory=list,
        description="Patches applied to create this version",
    )

    # ── Reproducibility ──────────────────────────────────────────
    hash: str = Field(
        ..., description="SHA256 of canonical JSON of semantic_state"
    )
    patch_sequence_hash: str = Field(
        ..., description="SHA256 of canonical JSON of patches_applied"
    )

    # ── Metadata ──────────────────────────────────────────────────
    created_at: float = Field(
        ..., description="Unix timestamp when snapshot was created"
    )
    created_by: str = Field(
        default="unknown",
        description="Name of pipeline phase that created this",
    )
    extractor_versions: dict = Field(
        default_factory=dict,
        description="Map of extractor names to versions used",
    )

    model_config = {
        "frozen": True,
        "extra": "forbid",
    }

    def get_lineage(self) -> List[str]:
        """Get all ancestor versions in order (root to this version)."""
        # This method doesn't compute the full lineage (that's
        # SemanticVersionHistory's job), but can be overridden
        # to provide a partial lineage stored in metadata
        ancestors = []
        current = self.parent_version

        # In reality, we'd query SemanticVersionHistory to get full lineage
        # This is a placeholder
        while current is not None:
            ancestors.insert(0, current)
            current = None  # Would need version history to continue
        
        ancestors.append(self.version)
        return ancestors
