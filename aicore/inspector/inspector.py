"""Inspector — node state introspection for the debug panel."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class InspectorTab(str, Enum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    METADATA = "METADATA"
    CACHE = "CACHE"
    TRACE = "TRACE"
    ERROR = "ERROR"


@dataclass
class NodeSnapshot:
    """A frozen view of a node's state at a point in time."""

    node_id: str
    label: str
    category: str
    status: str  # idle | running | completed | failed | cached
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    cache_hit: bool = False
    error: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "category": self.category,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "cache_hit": self.cache_hit,
            "error": self.error,
            "trace_id": self.trace_id,
        }


class Inspector:
    """
    Central inspection hub.

    Collects snapshots from the runtime and exposes them
    for the right-side inspector panel in the UI.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, NodeSnapshot] = {}
        self._active_tab: InspectorTab = InspectorTab.OUTPUT
        self._selected_node_id: Optional[str] = None

    def update(self, snapshot: NodeSnapshot) -> None:
        self._snapshots[snapshot.node_id] = snapshot

    def snapshot(self, node_id: str) -> Optional[NodeSnapshot]:
        return self._snapshots.get(node_id)

    def select(self, node_id: str) -> None:
        self._selected_node_id = node_id

    @property
    def selected(self) -> Optional[NodeSnapshot]:
        if self._selected_node_id:
            return self._snapshots.get(self._selected_node_id)
        return None

    @property
    def active_tab(self) -> InspectorTab:
        return self._active_tab

    def set_tab(self, tab: InspectorTab) -> None:
        self._active_tab = tab

    def all_snapshots(self) -> list[NodeSnapshot]:
        return list(self._snapshots.values())

    def snapshots(self) -> list[NodeSnapshot]:
        """Convenience alias for all_snapshots()."""
        return self.all_snapshots()

    def clear(self) -> None:
        self._snapshots.clear()
        self._selected_node_id = None