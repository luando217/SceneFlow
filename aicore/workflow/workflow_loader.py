"""Workflow loader — deserialize/serialize graphs and instantiate nodes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from ..node.registry import NodeRegistry
from .workflow_graph import WorkflowGraph, WorkflowNode, WorkflowEdge, GraphState


class WorkflowLoader:
    """
    Loads and saves workflow graphs from serialized formats.

    Handles:
    - Deserialization from dict / JSON file
    - Serialization to dict / JSON file
    - Node instantiation via NodeRegistry
    - Registry-level validation (node type existence)
    - Save with schema versioning
    """

    def __init__(self, registry: Optional[NodeRegistry] = None) -> None:
        self._registry = registry or NodeRegistry

    def load_from_dict(self, data: dict[str, Any]) -> WorkflowGraph:
        """Reconstruct a WorkflowGraph from a serialized dict."""
        return WorkflowGraph.from_dict(data)

    def load_from_file(self, path: str | Path) -> WorkflowGraph:
        """Load a workflow graph from a JSON file."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return self.load_from_dict(data)

    def save_to_file(self, graph: WorkflowGraph, path: str | Path) -> None:
        """Serialize a workflow graph to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(graph.to_dict(), f, indent=2)

    def validate(self, graph: WorkflowGraph) -> list[str]:
        """
        Validate that all node types in the graph are registered.

        Returns a list of errors (empty = valid).
        """
        errors: list[str] = []

        for nid, node in graph.nodes.items():
            if not self._registry.get(node.node_type):
                errors.append(f"Node '{nid}': unknown type '{node.node_type}'")

        # Also run structural validation from graph itself
        errors.extend(graph.validate())

        return errors

    def instantiate_nodes(self, graph: WorkflowGraph) -> dict[str, Any]:
        """Create runtime node instances for all nodes in the graph."""
        instances: dict[str, Any] = {}
        for nid, wfn in graph.nodes.items():
            node_instance = self._registry.instantiate(
                wfn.node_type,
                node_id=nid,
                label=wfn.label,
            )
            instances[nid] = node_instance
        return instances