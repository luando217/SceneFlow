"""Event bus — typed pub/sub for node execution lifecycle."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class EventType(str, enum.Enum):
    """All node execution lifecycle events."""

    NODE_STARTED = "NODE_STARTED"
    NODE_COMPLETED = "NODE_COMPLETED"
    NODE_FAILED = "NODE_FAILED"
    NODE_CACHED = "NODE_CACHED"
    NODE_SKIPPED = "NODE_SKIPPED"
    NODE_RETRYING = "NODE_RETRYING"
    WORKFLOW_STARTED = "WORKFLOW_STARTED"
    WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
    WORKFLOW_FAILED = "WORKFLOW_FAILED"
    DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"
    CACHE_HIT = "CACHE_HIT"
    CACHE_MISS = "CACHE_MISS"


@dataclass
class NodeEvent:
    """Typed execution event with provenance."""

    type: EventType
    node_id: str
    workflow_id: str
    trace_id: str
    duration_ms: float = 0.0
    error: Optional[str] = None
    cache_hit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# Type alias for event listeners
EventListener = Callable[[NodeEvent], None]


class EventBus:
    """
    Synchronous pub/sub event bus.

    Dispatches typed NodeEvent to registered listeners.
    Used by RuntimeOrchestrator to push state to Inspector and UI.
    """

    def __init__(self) -> None:
        self._listeners: dict[EventType, list[EventListener]] = {}

    def on(self, event_type: EventType, listener: EventListener) -> None:
        """Subscribe to a specific event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(listener)

    def on_any(self, listener: EventListener) -> None:
        """Subscribe to all events."""
        for et in EventType:
            self.on(et, listener)

    def emit(self, event: NodeEvent) -> None:
        """Dispatch an event to all registered listeners."""
        handlers = self._listeners.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                pass  # isolate listener failures

    def off(self, event_type: EventType, listener: EventListener) -> None:
        """Unsubscribe a listener."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                l for l in self._listeners[event_type] if l is not listener
            ]

    def clear(self) -> None:
        self._listeners.clear()