"""SemanticVersionHistory — immutable version tracking for scenes.

Maintains:
- All semantic snapshots for a scene
- Version lineage (parent pointers)
- Diffs between versions
- Replay capability
"""

from __future__ import annotations

from typing import List, Optional

from aicore.semantic.schemas.semantic_diff import SemanticDiff
from aicore.semantic.schemas.semantic_snapshot import SemanticSnapshot


class VersionNotFoundError(Exception):
    """Raised when requested version doesn't exist."""

    pass


class SemanticVersionHistory:
    """Immutable version history for a scene.

    Usage:
        history = SemanticVersionHistory("scene_001")
        history.add_snapshot("v1.0", scene, patches)
        history.add_snapshot("v1.1", scene_new, patches_new, parent="v1.0")
        lineage = history.get_lineage("v1.1")
    """

    def __init__(self, scene_id: str):
        """Initialize version history.

        Args:
            scene_id: Unique scene identifier
        """
        self.scene_id = scene_id
        self._snapshots: dict[str, SemanticSnapshot] = {}
        self._version_sequence: List[str] = []
        self._parent_map: dict[str, Optional[str]] = {}

    def add_snapshot(
        self,
        version: str,
        snapshot: SemanticSnapshot,
        parent_version: Optional[str] = None,
    ) -> None:
        """Record new immutable snapshot.

        Args:
            version: Version identifier (e.g. "v1.0")
            snapshot: Frozen SemanticSnapshot
            parent_version: Which version this evolved from (None if root)

        Raises:
            ValueError: If version already exists
            VersionNotFoundError: If parent_version doesn't exist
        """
        if version in self._snapshots:
            raise ValueError(f"Version {version} already exists")

        if parent_version is not None and parent_version not in self._snapshots:
            raise VersionNotFoundError(f"Parent version {parent_version} not found")

        # Verify scene ID consistency
        if snapshot.scene_id != self.scene_id:
            raise ValueError(
                f"Snapshot targets {snapshot.scene_id}, "
                f"but history is for {self.scene_id}"
            )

        self._snapshots[version] = snapshot
        self._version_sequence.append(version)
        self._parent_map[version] = parent_version

    def get_snapshot(self, version: str) -> SemanticSnapshot:
        """Retrieve snapshot by version.

        Args:
            version: Version identifier

        Returns:
            Immutable SemanticSnapshot

        Raises:
            VersionNotFoundError: If version doesn't exist
        """
        if version not in self._snapshots:
            raise VersionNotFoundError(f"Version {version} not found")
        return self._snapshots[version]

    def get_lineage(self, version: str) -> List[SemanticSnapshot]:
        """Get full ancestor chain from root to version.

        Returns:
            List of snapshots in chronological order (root first)
        """
        lineage = []
        current = version

        while current is not None:
            if current not in self._snapshots:
                break

            snapshot = self._snapshots[current]
            lineage.insert(0, snapshot)
            current = self._parent_map.get(current)

        return lineage

    def list_versions(self) -> List[str]:
        """Get all known versions in chronological order.

        Returns:
            List of version strings
        """
        return self._version_sequence.copy()

    def get_latest_version(self) -> Optional[str]:
        """Get most recent version added.

        Returns:
            Version string or None if no versions
        """
        return self._version_sequence[-1] if self._version_sequence else None

    def get_root_version(self) -> Optional[str]:
        """Get oldest (root) version in history.

        Returns:
            Version string or None if no versions
        """
        return self._version_sequence[0] if self._version_sequence else None

    def is_ancestor(self, potential_ancestor: str, version: str) -> bool:
        """Check if version is ancestor of another version.

        Args:
            potential_ancestor: Version to check
            version: Version to check against

        Returns:
            True if potential_ancestor is in lineage of version
        """
        lineage = self.get_lineage(version)
        ancestor_versions = [s.version for s in lineage]
        return potential_ancestor in ancestor_versions

    def diff(self, version_a: str, version_b: str) -> SemanticDiff:
        """Compute diff between two versions.

        Args:
            version_a: First version
            version_b: Second version

        Returns:
            SemanticDiff describing changes

        Raises:
            VersionNotFoundError: If either version doesn't exist
        """
        snap_a = self.get_snapshot(version_a)
        snap_b = self.get_snapshot(version_b)

        # Import here to avoid circular dependency
        from aicore.semantic.service.diff_computer import compute_semantic_diff

        return compute_semantic_diff(
            snap_a.semantic_state,
            snap_b.semantic_state,
            version_a=version_a,
            version_b=version_b,
        )

    def replay(self, version: str) -> dict:
        """Recompute version by replaying all patches from root.

        This is a verification step to ensure replay determinism.

        Args:
            version: Version to replay

        Returns:
            {
                "success": bool,
                "original_hash": str,
                "replay_hash": str,
                "matches": bool,
            }
        """
        # Import here to avoid circular dependency
        from aicore.semantic.schemas.semantic_hash import SemanticHash
        from aicore.semantic.pipeline.merge_engine import PatchMergeEngine

        snapshot = self.get_snapshot(version)
        lineage = self.get_lineage(version)

        # Collect all patches from root to version
        all_patches = []
        for snap in lineage:
            all_patches.extend(snap.patches_applied)

        # Replay merge
        engine = PatchMergeEngine()
        merged = engine.merge(self.scene_id, all_patches)

        # Build scene from merged state
        from aicore.semantic.builder.scene_builder import SceneBuilder

        replayed_scene = SceneBuilder.build(self.scene_id, merged)

        # Compare hashes
        original_hash = SemanticHash.compute_scene(snapshot.semantic_state)
        replay_hash = SemanticHash.compute_scene(replayed_scene)

        return {
            "success": original_hash == replay_hash,
            "original_hash": original_hash,
            "replay_hash": replay_hash,
            "matches": original_hash == replay_hash,
        }

    def prune_lineage(self, keep_versions: List[str]) -> int:
        """Remove versions not in keep_versions list.

        Useful for garbage collection while preserving important versions.

        Args:
            keep_versions: Versions to keep

        Returns:
            Number of versions removed
        """
        to_remove = set(self._snapshots.keys()) - set(keep_versions)
        count = 0

        for version in to_remove:
            del self._snapshots[version]
            del self._parent_map[version]
            self._version_sequence.remove(version)
            count += 1

        return count

    def summary(self) -> dict:
        """Get summary of version history.

        Returns:
            {
                "scene_id": str,
                "total_versions": int,
                "versions": [str],  # all version IDs
                "root_version": str,
                "latest_version": str,
            }
        """
        return {
            "scene_id": self.scene_id,
            "total_versions": len(self._snapshots),
            "versions": self._version_sequence.copy(),
            "root_version": self.get_root_version(),
            "latest_version": self.get_latest_version(),
        }
