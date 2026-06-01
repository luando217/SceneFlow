"""
AICut — Semantic Anime Retrieval OS
Core runtime package for modular DAG execution.
"""

__version__ = "0.1.0"

from .node.base import (
    BaseNode,
    NodeCategory,
    NodeInput,
    NodeOutput,
    CachePolicy,
    RetryPolicy,
    ExecutionMetadata,
)
from .node.registry import NodeRegistry
from .cache import CacheManager, CacheEntry, CacheStats
from .trace import Tracer, TraceSpan, TraceContext
from .queue import ExecutionQueue, QueueItem, QueueItemState, QueueState
from .workflow import WorkflowGraph, WorkflowNode, WorkflowEdge, GraphState, WorkflowLoader
from .inspector import Inspector, NodeSnapshot, InspectorTab
from .runtime import RuntimeOrchestrator
from .events import EventBus, EventType, NodeEvent

__all__ = [
    # Node
    "BaseNode",
    "NodeCategory",
    "NodeInput",
    "NodeOutput",
    "CachePolicy",
    "RetryPolicy",
    "ExecutionMetadata",
    "NodeRegistry",
    # Cache
    "CacheManager",
    "CacheEntry",
    "CacheStats",
    # Trace
    "Tracer",
    "TraceSpan",
    "TraceContext",
    # Queue
    "ExecutionQueue",
    "QueueItem",
    "QueueItemState",
    "QueueState",
    # Workflow
    "WorkflowGraph",
    "WorkflowNode",
    "WorkflowEdge",
    "GraphState",
    "WorkflowLoader",
    # Inspector
    "Inspector",
    "NodeSnapshot",
    "InspectorTab",
    # Runtime
    "RuntimeOrchestrator",
    # Events
    "EventBus",
    "EventType",
    "NodeEvent",
]
