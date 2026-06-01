"""Runtime orchestrator — event-driven graph execution with cache, trace, and inspector integration."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Optional, Callable, Awaitable

from ..node.base import BaseNode, ExecutionMetadata
from ..node.registry import NodeRegistry
from ..cache import CacheManager
from ..trace import Tracer, TraceContext
from ..queue import ExecutionQueue, QueueItem, QueueItemState
from ..inspector import Inspector, NodeSnapshot, InspectorTab
from ..workflow import WorkflowGraph, GraphState, WorkflowLoader
from ..events import EventBus, EventType, NodeEvent


class RuntimeOrchestrator:
    """
    Central event-driven async runtime for graph execution.

    Lifecycle:
      1. Load graph ──> load_graph() / load_from_dict() / load_from_file()
      2. Validate   ──> validate() — tests structural + registry integrity
      3. Run partial ──> run(start_nodes=[...]) — downstream-only rerun
      4. Run full   ──> run() — execute entire graph
      5. Reset      ──> reset() — clear state for fresh execution

    Integration:
      - Emits NodeEvents on EventBus for every lifecycle transition
      - Pushes NodeSnapshots to Inspector for UI panel
      - Records TraceSpans on Tracer for execution traces
      - Checks CacheManager before each node; records hit/miss
    """

    def __init__(
        self,
        registry: Optional[NodeRegistry] = None,
        cache: Optional[CacheManager] = None,
        tracer: Optional[Tracer] = None,
        inspector: Optional[Inspector] = None,
        loader: Optional[WorkflowLoader] = None,
        event_bus: Optional[EventBus] = None,
        max_concurrency: int = 4,
    ) -> None:
        self.registry = registry or NodeRegistry
        self.cache = cache or CacheManager()
        self.tracer = tracer or Tracer()
        self.inspector = inspector or Inspector()
        self.loader = loader or WorkflowLoader(registry=self.registry)
        self.events = event_bus or EventBus()
        self.queue = ExecutionQueue(max_concurrency=max_concurrency)

        # Internal state
        self._node_instances: dict[str, BaseNode] = {}
        self._current_graph: Optional[WorkflowGraph] = None
        self._running = False
        self._current_trace_id: Optional[str] = None

        # Wire queue events -> inspector + event bus
        async def _queue_listener(item: QueueItem) -> None:
            snapshot = NodeSnapshot(
                node_id=item.node_id,
                label="",
                category="",
                status=item.state.value.lower(),
                duration_ms=item.duration_ms,
                error=item.error,
                trace_id=item.trace_id,
            )
            self.inspector.update(snapshot)

            # Map queue state changes to event bus events
            event_map = {
                QueueItemState.RUNNING: EventType.NODE_STARTED,
                QueueItemState.COMPLETED: EventType.NODE_COMPLETED,
                QueueItemState.FAILED: EventType.NODE_FAILED,
                QueueItemState.SKIPPED: EventType.NODE_SKIPPED,
            }
            evt_type = event_map.get(item.state)
            if evt_type:
                self.events.emit(NodeEvent(
                    type=evt_type,
                    node_id=item.node_id,
                    workflow_id=item.workflow_id,
                    trace_id=item.trace_id,
                    duration_ms=item.duration_ms,
                    error=item.error,
                    cache_hit=item.state == QueueItemState.COMPLETED and (
                        self._snapshot_cache_hit(item.node_id)
                    ),
                ))

        self.queue.subscribe(_queue_listener)

    # ---- Graph lifecycle ----

    def load_graph(self, graph: WorkflowGraph) -> None:
        """Load a workflow graph and instantiate its nodes."""
        self._current_graph = graph
        self._node_instances = self.loader.instantiate_nodes(graph)
        graph.state = GraphState.READY

    def load_from_dict(self, data: dict[str, Any]) -> WorkflowGraph:
        graph = self.loader.load_from_dict(data)
        self.load_graph(graph)
        return graph

    def load_from_file(self, path: str) -> WorkflowGraph:
        graph = self.loader.load_from_file(path)
        self.load_graph(graph)
        return graph

    # ---- Validation ----

    def validate(self) -> list[str]:
        """Validate the currently loaded graph."""
        if self._current_graph is None:
            return ["No graph loaded"]
        errors = self.loader.validate(self._current_graph)
        if not errors:
            self._current_graph.state = GraphState.VALID
        return errors

    # ---- Execution ----

    async def run(self, graph: Optional[WorkflowGraph] = None,
                  start_nodes: Optional[list[str]] = None) -> None:
        """
        Execute a workflow graph.

        Args:
            graph: Graph to run (uses current if None).
            start_nodes: If provided, only run these nodes + their downstream.
                         Used for partial downstream-only rerun.

        Raises:
            RuntimeError: If no graph is loaded.
            ValueError: If graph validation fails.
        """
        if graph is not None:
            self.load_graph(graph)

        if self._current_graph is None:
            raise RuntimeError("No graph loaded. Call load_graph() first.")

        # Validate before running
        errs = self.validate()
        if errs:
            raise ValueError(f"Graph validation failed: {errs}")

        self._running = True
        self._current_graph.state = GraphState.RUNNING

        workflow_id = self._current_graph.id
        trace_id = uuid.uuid4().hex[:16]
        self._current_trace_id = trace_id

        # Emit workflow started
        self.events.emit(NodeEvent(
            type=EventType.WORKFLOW_STARTED,
            node_id=workflow_id,
            workflow_id=workflow_id,
            trace_id=trace_id,
            metadata={"name": self._current_graph.name, "nodes": len(self._current_graph.nodes)},
        ))

        # Build execution set
        order = self._current_graph.execution_order()
        node_map = self._current_graph.nodes

        if start_nodes:
            # Downstream-only rerun: compute transitive downstream of start nodes
            downstream_set: set[str] = set(start_nodes)
            for sid in start_nodes:
                downstream_set |= self._current_graph.downstream_of(sid)
            # Only nodes in downstream_set (and in the graph) are executed
            order = [nid for nid in order if nid in downstream_set]

        # Create queue items
        session_items: list[QueueItem] = []
        for nid in order:
            wf_node = node_map[nid]
            node_instance = self._node_instances.get(nid)
            if node_instance is None:
                continue

            upstream_ids = [
                e.source for e in self._current_graph.edges
                if e.target == nid
            ]

            # Only depend on upstreams that are also in the execution set
            if start_nodes:
                upstream_ids = [u for u in upstream_ids if u in downstream_set]

            item = QueueItem(
                id=nid,
                node_id=nid,
                workflow_id=workflow_id,
                trace_id=trace_id,
                inputs={},
                max_retries=node_instance.retry_policy.max_retries,
                depends_on=upstream_ids,
            )
            session_items.append(item)

        # Mark skipped items (nodes not in execution set)
        for nid in self._current_graph.nodes:
            if nid not in downstream_set if start_nodes else nid not in order:
                snapshot = NodeSnapshot(
                    node_id=nid,
                    label=self._current_graph.nodes[nid].label,
                    category=self._current_graph.nodes[nid].category,
                    status="skipped",
                    trace_id=trace_id,
                )
                self.inspector.update(snapshot)

        # Enqueue all items
        # (must be done before starting the processor so the worker sees them)
        self.queue.enqueue_many(session_items)

        # Start processing
        await self.queue.process(self._execute_node)

        # Wait for completion
        await self.queue.wait_all()

        # Determine final state
        qs = self.queue.state()
        if qs.failed > 0:
            self._current_graph.state = GraphState.FAILED
            self.events.emit(NodeEvent(
                type=EventType.WORKFLOW_FAILED,
                node_id=workflow_id,
                workflow_id=workflow_id,
                trace_id=trace_id,
                metadata={"failed": qs.failed, "completed": qs.completed},
            ))
        else:
            self._current_graph.state = GraphState.COMPLETED
            self.events.emit(NodeEvent(
                type=EventType.WORKFLOW_COMPLETED,
                node_id=workflow_id,
                workflow_id=workflow_id,
                trace_id=trace_id,
                metadata={"completed": qs.completed, "skipped": qs.skipped},
            ))

        self._running = False

    async def _execute_node(self, item: QueueItem) -> dict[str, Any]:
        """Execute a single node: resolve inputs -> cache check -> process -> store outputs."""
        node = self._node_instances.get(item.node_id)
        if node is None:
            raise ValueError(f"Node instance not found: {item.node_id}")

        wf_node = self._current_graph.nodes.get(item.node_id) if self._current_graph else None
        if wf_node is None:
            raise ValueError(f"Workflow node not found: {item.node_id}")

        item.state = QueueItemState.RUNNING

        # Resolve inputs from upstream outputs via edges
        resolved_inputs: dict[str, Any] = dict(wf_node.config)
        if self._current_graph:
            for edge in self._current_graph.edges:
                if edge.target == item.node_id:
                    upstream_node = self._node_instances.get(edge.source)
                    if upstream_node and upstream_node.last_output:
                        port_val = upstream_node.last_output.get(edge.source_port)
                        if port_val is not None:
                            resolved_inputs[edge.target_port] = port_val

        item.inputs = resolved_inputs

        # Trace context
        ctx = TraceContext(trace_id=item.trace_id, workflow_id=item.workflow_id)
        span = self.tracer.start_span(item.node_id, "process", ctx)

        # Cache check
        cache_policy = node.cache_policy
        use_cache = cache_policy.enabled
        ttl = cache_policy.ttl_seconds if use_cache else None
        cached = self.cache.get(item.node_id, resolved_inputs) if use_cache else None

        if cached is not None:
            # Cache hit
            self.events.emit(NodeEvent(
                type=EventType.CACHE_HIT,
                node_id=item.node_id,
                workflow_id=item.workflow_id,
                trace_id=item.trace_id,
                cache_hit=True,
            ))
            result = cached
            node._last_input = resolved_inputs
            node._last_output = result
            node._last_metadata = ExecutionMetadata(
                node_id=item.node_id,
                workflow_id=item.workflow_id,
                trace_id=item.trace_id,
                started_at=span.started_at,
                ended_at=time.time(),
                cache_hit=True,
            )
            item.state = QueueItemState.COMPLETED
            self.tracer.end_span(span)
            return result

        # Cache miss
        if use_cache:
            self.events.emit(NodeEvent(
                type=EventType.CACHE_MISS,
                node_id=item.node_id,
                workflow_id=item.workflow_id,
                trace_id=item.trace_id,
                cache_hit=False,
            ))

        # Execute
        try:
            result = await node.process(resolved_inputs)
            self.tracer.end_span(span)

            node._last_input = resolved_inputs
            node._last_output = result

            if use_cache:
                self.cache.set(item.node_id, resolved_inputs, result, ttl=ttl)

            return result
        except Exception as e:
            self.tracer.end_span(span, error=str(e))
            raise

    def _snapshot_cache_hit(self, node_id: str) -> bool:
        """Check if the last execution of a node was a cache hit."""
        node = self._node_instances.get(node_id)
        if node and node._last_metadata:
            return node._last_metadata.cache_hit
        return False

    def reset(self) -> None:
        """Reset runtime state for a fresh execution."""
        self.queue.clear()
        self.inspector.clear()
        self.tracer.clear()
        if self._current_graph:
            self._current_graph.state = GraphState.IDLE
        self._running = False
        self._current_trace_id = None

    def skip_downstream(self, node_id: str) -> None:
        """
        Mark all downstream nodes as skipped (for UI-initiated skips).
        """
        if self._current_graph is None:
            return
        downstream = self._current_graph.downstream_of(node_id)
        for did in downstream:
            self.queue.skip(did)

    # ---- Queries ----

    @property
    def graph(self) -> Optional[WorkflowGraph]:
        return self._current_graph

    def graph_state(self) -> str:
        if self._current_graph:
            return self._current_graph.state.value
        return "IDLE"

    def is_running(self) -> bool:
        return self._running

    def node_instance(self, node_id: str) -> Optional[BaseNode]:
        return self._node_instances.get(node_id)