"""Workflow graph — DAG definition, node wiring, state tracking, and validation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# Schema version for workflow serialization.
# Increment when breaking changes are made to the workflow format.
WORKFLOW_SCHEMA_VERSION = 1


class GraphState(str, Enum):
    IDLE = "IDLE"
    READY = "READY"
    VALID = "VALID"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class WorkflowNode:
    """A node instance within a workflow graph."""

    id: str
    node_type: str  # Class name used by NodeRegistry
    label: str
    config: dict[str, Any] = field(default_factory=dict)
    position: tuple[float, float] = (0.0, 0.0)
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_type": self.node_type,
            "label": self.label,
            "category": self.category,
            "position": [self.position[0], self.position[1]],
            "config": dict(self.config),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowNode:
        pos = data.get("position", [0.0, 0.0])
        if isinstance(pos, list) and len(pos) == 2:
            pos = (float(pos[0]), float(pos[1]))
        return cls(
            id=data["id"],
            node_type=data["node_type"],
            label=data.get("label", data["id"]),
            config=data.get("config", {}),
            position=pos,
            category=data.get("category", ""),
        )


@dataclass
class WorkflowEdge:
    """A connection from source node output to target node input."""

    id: str
    source: str  # source node id
    source_port: str
    target: str  # target node id
    target_port: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "source_port": self.source_port,
            "target": self.target,
            "target_port": self.target_port,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowEdge:
        return cls(
            id=data["id"],
            source=data["source"],
            source_port=data["source_port"],
            target=data["target"],
            target_port=data["target_port"],
        )


@dataclass
class WorkflowGraph:
    """
    Serializable DAG of nodes and edges with schema versioning.

    Used by the runtime to determine execution order and
    by the UI for graph rendering.

    Schema version is embedded in serialized form for forward/backward compat.
    """

    id: str
    name: str
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    edges: list[WorkflowEdge] = field(default_factory=list)
    state: GraphState = GraphState.IDLE
    metadata: dict[str, Any] = field(default_factory=dict)

    # ---- Builder API ----

    def add_node(self, node_type: str, label: str = "", config: dict | None = None,
                 position: tuple[float, float] = (0.0, 0.0), category: str = "") -> WorkflowNode:
        node_id = f"{node_type.lower()}_{uuid.uuid4().hex[:6]}"
        node = WorkflowNode(
            id=node_id,
            node_type=node_type,
            label=label or node_id,
            config=config or {},
            position=position,
            category=category,
        )
        self.nodes[node_id] = node
        self.state = GraphState.READY
        return node

    def add_edge(self, source: str, source_port: str,
                 target: str, target_port: str) -> WorkflowEdge:
        edge = WorkflowEdge(
            id=f"e_{uuid.uuid4().hex[:6]}",
            source=source,
            source_port=source_port,
            target=target,
            target_port=target_port,
        )
        self.edges.append(edge)
        self.state = GraphState.READY
        return edge

    # ---- Graph queries ----

    def upstream_nodes(self, node_id: str) -> list[WorkflowNode]:
        """Return nodes that feed into the given node."""
        upstream_ids = {e.source for e in self.edges if e.target == node_id}
        return [self.nodes[nid] for nid in upstream_ids if nid in self.nodes]

    def downstream_nodes(self, node_id: str) -> list[WorkflowNode]:
        """Return nodes that consume output from the given node."""
        downstream_ids = {e.target for e in self.edges if e.source == node_id}
        return [self.nodes[nid] for nid in downstream_ids if nid in self.nodes]

    def upstream_of(self, node_id: str) -> set[str]:
        """Return all node IDs that are upstream (transitively) of the given node."""
        result: set[str] = set()
        visited: set[str] = set()
        stack = [e.source for e in self.edges if e.target == node_id]
        while stack:
            nid = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            result.add(nid)
            stack.extend(e.source for e in self.edges if e.target == nid)
        return result

    def downstream_of(self, node_id: str) -> set[str]:
        """Return all node IDs that are downstream (transitively) of the given node."""
        result: set[str] = set()
        visited: set[str] = set()
        stack = [e.target for e in self.edges if e.source == node_id]
        while stack:
            nid = stack.pop()
            if nid in visited:
                continue
            visited.add(nid)
            result.add(nid)
            stack.extend(e.target for e in self.edges if e.source == nid)
        return result

    # ---- Topological sort ----

    def execution_order(self) -> list[str]:
        """
        Topological sort of node IDs (Kahn's algorithm).

        Returns node IDs in deterministic execution order.
        Raises ValueError if cycle detected.
        """
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        adjacency: dict[str, list[str]] = {nid: [] for nid in self.nodes}

        for edge in self.edges:
            if edge.source in self.nodes and edge.target in self.nodes:
                adjacency[edge.source].append(edge.target)
                in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            # Sort for deterministic ordering when multiple nodes have degree 0
            queue.sort()
            nid = queue.pop(0)
            order.append(nid)
            for neighbor in adjacency.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.nodes):
            raise ValueError(
                f"Cycle detected in workflow '{self.name}'. "
                f"Sorted {len(order)}/{len(self.nodes)} nodes."
            )

        return order

    # ---- Validation ----

    def validate(self) -> list[str]:
        """
        Validate graph integrity.

        Returns a list of error messages (empty = valid).
        Does NOT modify state.
        """
        errors: list[str] = []

        if not self.id:
            errors.append("Workflow ID is empty")

        if not self.name:
            errors.append("Workflow name is empty")

        if not self.nodes:
            errors.append("Workflow has no nodes")
            return errors

        # Check all edge references are valid
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge '{edge.id}': source node '{edge.source}' not found")
            if edge.target not in self.nodes:
                errors.append(f"Edge '{edge.id}': target node '{edge.target}' not found")
            if edge.source == edge.target:
                errors.append(f"Edge '{edge.id}': self-loop on node '{edge.source}'")

        # Check for orphan nodes (no edges at all) — warn only, not error
        connected: set[str] = set()
        for edge in self.edges:
            connected.add(edge.source)
            connected.add(edge.target)
        orphans = [nid for nid in self.nodes if nid not in connected]
        if orphans and len(self.nodes) > 1:
            errors.append(f"Orphan nodes (disconnected): {orphans}")

        # Check for duplicate node IDs
        if len(self.nodes) != len({n.id for n in self.nodes.values()}):
            errors.append("Duplicate node IDs detected")

        # Check cycle via topological sort
        try:
            self.execution_order()
        except ValueError as e:
            errors.append(str(e))

        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    # ---- Serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "id": self.id,
            "name": self.name,
            "state": self.state.value,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowGraph:
        """Deserialize from a dictionary. Validates schema version."""
        schema_version = data.get("schema_version", 0)
        if schema_version < 1:
            raise ValueError(
                f"Unsupported schema version {schema_version}. "
                f"Minimum supported: {WORKFLOW_SCHEMA_VERSION}"
            )

        graph = cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            state=GraphState.READY,
            metadata=data.get("metadata", {}),
        )
        for nid, ndata in data.get("nodes", {}).items():
            graph.nodes[nid] = WorkflowNode.from_dict(ndata)
        for edata in data.get("edges", []):
            graph.edges.append(WorkflowEdge.from_dict(edata))
        return graph