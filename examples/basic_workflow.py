"""
Minimal runnable workflow example.

Demonstrates:
- Node definition (2 simple nodes)
- Graph construction
- Workflow serialization/deserialization
- Full async execution via RuntimeOrchestrator
- Event bus integration (cache hit/miss)
- Inspector snapshots
- Execution trace
- Cache hit/miss tracking
- Downstream-only rerun
"""

import asyncio
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Minimal node implementations
# ---------------------------------------------------------------------------

from aicore import (
    BaseNode, NodeCategory, NodeInput, NodeOutput, CachePolicy, RetryPolicy,
    NodeRegistry,
    WorkflowGraph, WorkflowNode, WorkflowEdge, GraphState,
    RuntimeOrchestrator, ExecutionQueue, QueueItem, QueueItemState,
    Tracer, TraceContext,
    CacheManager,
    Inspector, NodeSnapshot, InspectorTab,
    EventBus, EventType, NodeEvent,
)


class SourceNode(BaseNode):
    """Simple source node: produces a greeting."""

    category = NodeCategory.SOURCE

    @property
    def inputs(self) -> list[NodeInput]:
        return []

    @property
    def outputs(self) -> list[NodeOutput]:
        return [NodeOutput(name="greeting", type_hint="str")]

    async def process(self, inputs: dict) -> dict:
        await asyncio.sleep(0.05)  # simulate work
        return {"greeting": f"Hello from {self.label}"}


class ShoutNode(BaseNode):
    """Transforms input: uppercases the greeting."""

    category = NodeCategory.PREPROCESS

    @property
    def inputs(self) -> list[NodeInput]:
        return [NodeInput(name="greeting", type_hint="str")]

    @property
    def outputs(self) -> list[NodeOutput]:
        return [NodeOutput(name="shouted", type_hint="str")]

    async def process(self, inputs: dict) -> dict:
        await asyncio.sleep(0.03)
        greeting = inputs.get("greeting", "")
        return {"shouted": greeting.upper() + "!!!"}


# ---------------------------------------------------------------------------
# Event logging callback
# ---------------------------------------------------------------------------

event_log: list[str] = []

def on_event(event: NodeEvent) -> None:
    msg = f"[{event.type.value:20s}] node={event.node_id[:12]:12s}  dur={event.duration_ms:7.2f}ms"
    if event.cache_hit:
        msg += "  CACHE HIT"
    if event.error:
        msg += f"  ERROR={event.error}"
    event_log.append(msg)
    print(f"  EVENT: {msg}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    # --- 0. Register custom node types ---
    NodeRegistry.register(SourceNode)
    NodeRegistry.register(ShoutNode)

    # --- 1. Create the event bus and attach listener ---
    events = EventBus()
    events.on_any(on_event)

    # --- 2. Build shared services ---
    cache = CacheManager()
    tracer = Tracer()
    inspector = Inspector()
    orchestrator = RuntimeOrchestrator(
        cache=cache,
        tracer=tracer,
        inspector=inspector,
        event_bus=events,
        max_concurrency=2,
    )

    # --- 3. Build a simple workflow graph ---
    print("\n=== BUILD GRAPH ===")
    g = WorkflowGraph(id="demo-1", name="Basic Demo")
    src = g.add_node("SourceNode", label="Greeter", category="SOURCE")
    shouter = g.add_node("ShoutNode", label="Shouter", category="PREPROCESS")
    g.add_edge(src.id, "greeting", shouter.id, "greeting")

    print(f"  Nodes: {len(g.nodes)}  Edges: {len(g.edges)}")
    print(f"  Execution order: {g.execution_order()}")
    print(f"  Valid: {g.is_valid()}")

    # --- 4. Serialize / Deserialize round-trip ---
    print("\n=== SERIALIZATION ROUND-TRIP ===")
    serialized = g.to_dict()
    print(f"  Schema version: {serialized['schema_version']}")
    restored = WorkflowGraph.from_dict(serialized)
    print(f"  Restored: id={restored.id} nodes={len(restored.nodes)}")
    assert restored.id == g.id
    assert len(restored.nodes) == len(g.nodes)

    # --- 5. Run full workflow (first time — cache miss) ---
    print("\n=== RUN FULL (first run — should be cache miss) ===")
    await orchestrator.run(g)
    qs = orchestrator.queue.state()
    print(f"  Queue: {qs.completed} completed, {qs.failed} failed, {qs.skipped} skipped")
    print(f"  Graph state: {orchestrator.graph_state()}")

    # Inspect node outputs
    src_out = orchestrator.node_instance(src.id)
    shout_out = orchestrator.node_instance(shouter.id)
    print(f"  Source output: {src_out.last_output}")
    print(f"  Shouter output: {shout_out.last_output}")
    assert shout_out.last_output["shouted"] == "HELLO FROM GREETER!!!"

    # --- 6. Run full workflow again (second time — cache hit) ---
    print("\n=== RUN FULL (second run — should be cache hit) ===")
    orchestrator.reset()
    await orchestrator.run(g)
    qs2 = orchestrator.queue.state()
    print(f"  Queue: {qs2.completed} completed, {qs2.failed} failed, {qs2.skipped} skipped")
    # At least one cache hit should have been recorded
    cache_stats = cache.stats
    print(f"  Cache stats: hits={cache_stats.hits} misses={cache_stats.misses} rate={cache_stats.hit_rate:.1%}")

    # --- 7. Downstream-only rerun ---
    print("\n=== DOWNSTREAM-ONLY RERUN (modify Source config) ===")
    orchestrator.reset()
    # Simulate changing source config by modifying the graph node config
    g.nodes[src.id].config["change"] = "force-rerun"
    await orchestrator.run(g, start_nodes=[src.id])
    qs3 = orchestrator.queue.state()
    print(f"  Queue: {qs3.completed} completed, {qs3.failed} failed, {qs3.skipped} skipped")
    # Shouter should have been re-executed because it's downstream of source
    assert qs3.skipped == 0, f"Expected 0 skipped, got {qs3.skipped}"
    # Source was re-run with new config -> new output
    src_out3 = orchestrator.node_instance(src.id)
    print(f"  Source output after rerun: {src_out3.last_output}")

    # --- 8. Inspect trace ---
    print("\n=== TRACES ===")
    all_spans = tracer._spans  # internal access for demo
    print(f"  Total spans recorded: {len(all_spans)}")

    # --- 9. Inspect snapshots ---
    print("\n=== INSPECTOR SNAPSHOTS ===")
    for snap in inspector.snapshots():
        print(f"  [{snap.status:10s}] {snap.node_id[:12]:12s}  dur={snap.duration_ms:.2f}ms  err={snap.error}")

    # --- 10. Event log summary ---
    print("\n=== EVENT LOG ===")
    for entry in event_log:
        print(f"  {entry}")

    print("\n=== ALL CHECKS PASSED ===")


if __name__ == "__main__":
    asyncio.run(main())