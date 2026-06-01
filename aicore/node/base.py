"""Base node interface and node category enum."""

from __future__ import annotations

import enum
import uuid
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


class NodeCategory(str, enum.Enum):
    """Runtime node categories matching project architecture."""

    SOURCE = "SOURCE"
    PREPROCESS = "PREPROCESS"
    DETECTOR = "DETECTOR"
    TAGGER = "TAGGER"
    EMBEDDER = "EMBEDDER"
    RETRIEVER = "RETRIEVER"
    RERANKER = "RERANKER"
    MEMORY = "MEMORY"
    REASONER = "REASONER"
    EXPORT = "EXPORT"
    DEBUG = "DEBUG"
    CACHE = "CACHE"
    CONTROL = "CONTROL"


@dataclass
class NodeInput:
    """Schema for a single node input port."""

    name: str
    type_hint: str = "Any"
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass
class NodeOutput:
    """Schema for a single node output port."""

    name: str
    type_hint: str = "Any"
    description: str = ""


@dataclass
class CachePolicy:
    """Cache strategy for a node."""

    enabled: bool = True
    ttl_seconds: Optional[float] = None
    key_fields: tuple[str, ...] = ()


@dataclass
class RetryPolicy:
    """Retry behaviour for node execution."""

    max_retries: int = 0
    delay_seconds: float = 0.5
    backoff: float = 2.0


@dataclass
class ExecutionMetadata:
    """Metadata snapshot after a node execution."""

    node_id: str
    workflow_id: str
    trace_id: str
    started_at: float = 0.0
    ended_at: float = 0.0
    duration_ms: float = 0.0
    cache_hit: bool = False
    error: Optional[str] = None

    @property
    def elapsed(self) -> float:
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at) * 1000
        return 0.0


class BaseNode(ABC):
    """
    Abstract base for every node in the graph.

    Each node behaves like an isolated runtime:
    - declares its own I/O schema
    - owns its cache and retry policies
    - executes asynchronously via the runtime
    - produces inspectable execution metadata
    """

    node_id: str
    category: NodeCategory
    label: str

    def __init__(
        self,
        node_id: Optional[str] = None,
        label: Optional[str] = None,
        cache_policy: Optional[CachePolicy] = None,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        self.node_id = node_id or f"{self.__class__.__name__.lower()}_{uuid.uuid4().hex[:8]}"
        self.label = label or self.node_id
        self.cache_policy = cache_policy or CachePolicy()
        self.retry_policy = retry_policy or RetryPolicy()
        self._last_metadata: Optional[ExecutionMetadata] = None
        self._last_input: Optional[dict[str, Any]] = None
        self._last_output: Optional[dict[str, Any]] = None

    # ---- Schema (override in subclasses) ----

    @property
    @abstractmethod
    def inputs(self) -> list[NodeInput]:
        ...

    @property
    @abstractmethod
    def outputs(self) -> list[NodeOutput]:
        ...

    # ---- Execution contract ----

    @abstractmethod
    async def process(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute the node logic. Override in subclasses."""
        ...

    # ---- Debug helpers ----

    @property
    def last_input(self) -> Optional[dict[str, Any]]:
        return self._last_input

    @property
    def last_output(self) -> Optional[dict[str, Any]]:
        return self._last_output

    @property
    def last_metadata(self) -> Optional[ExecutionMetadata]:
        return self._last_metadata

    # ---- Serialization helpers ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "category": self.category.value,
            "label": self.label,
            "inputs": [{"name": i.name, "type_hint": i.type_hint} for i in self.inputs],
            "outputs": [{"name": o.name, "type_hint": o.type_hint} for o in self.outputs],
            "cache_policy": {
                "enabled": self.cache_policy.enabled,
                "ttl_seconds": self.cache_policy.ttl_seconds,
            },
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} id={self.node_id} cat={self.category.value}>"