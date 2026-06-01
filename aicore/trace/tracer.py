"""Tracer — lightweight execution tracing with span nesting and timing."""

from __future__ import annotations

import uuid
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TraceContext:
    """Immutable trace context propagated through the execution graph."""

    trace_id: str
    workflow_id: str


@dataclass
class TraceSpan:
    """A single execution span recording timing and metadata."""

    span_id: str
    parent_id: Optional[str]
    node_id: str
    trace_id: str
    workflow_id: str
    operation: str
    started_at: float = 0.0
    ended_at: float = 0.0
    tags: dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at) * 1000
        return 0.0

    def close(self) -> None:
        self.ended_at = time.time()


class Tracer:
    """
    Tracer that records execution spans.

    Spans are stored in-memory and exposed for the inspector UI.
    """

    def __init__(self) -> None:
        self._spans: list[TraceSpan] = []
        self._stack: list[str] = []

    def start_span(
        self,
        node_id: str,
        operation: str,
        ctx: TraceContext,
        tags: Optional[dict[str, str]] = None,
    ) -> TraceSpan:
        parent_id = self._stack[-1] if self._stack else None
        span = TraceSpan(
            span_id=uuid.uuid4().hex[:12],
            parent_id=parent_id,
            node_id=node_id,
            trace_id=ctx.trace_id,
            workflow_id=ctx.workflow_id,
            operation=operation,
            started_at=time.time(),
            tags=tags or {},
        )
        self._spans.append(span)
        self._stack.append(span.span_id)
        return span

    def end_span(self, span: TraceSpan, error: Optional[str] = None) -> None:
        span.close()
        span.error = error
        if self._stack and self._stack[-1] == span.span_id:
            self._stack.pop()

    def spans_for_trace(self, trace_id: str) -> list[TraceSpan]:
        return [s for s in self._spans if s.trace_id == trace_id]

    def clear(self) -> None:
        self._spans.clear()
        self._stack.clear()