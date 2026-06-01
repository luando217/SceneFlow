"""Execution queue — async FIFO queue with state tracking, dependency resolution, and concurrency control."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Callable, Awaitable


class QueueItemState(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


@dataclass
class QueueItem:
    """A single executable unit in the queue."""

    id: str
    node_id: str
    workflow_id: str
    trace_id: str
    inputs: dict[str, Any]
    state: QueueItemState = QueueItemState.PENDING
    created_at: float = 0.0
    started_at: float = 0.0
    ended_at: float = 0.0
    result: Optional[Any] = None
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 0
    depends_on: list[str] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.ended_at and self.started_at:
            return (self.ended_at - self.started_at) * 1000
        return 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "state": self.state.value,
            "created_at": self.created_at,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class QueueState:
    """Snapshot of queue state for UI."""

    pending: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0


class ExecutionQueue:
    """
    Async FIFO execution queue with:
    - Concurrency limit (semaphore)
    - Dependency tracking (DAG ordering)
    - Retry with backoff
    - Skip support
    - Observable state for UI
    - Deterministic execution
    """

    def __init__(self, max_concurrency: int = 4) -> None:
        self._items: dict[str, QueueItem] = {}
        self._pending: asyncio.Queue[QueueItem] = asyncio.Queue()
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._running_count = 0
        self._completed_ids: set[str] = set()
        self._failed_ids: set[str] = set()
        self._skipped_ids: set[str] = set()
        self._listeners: list[Callable[[QueueItem], Awaitable[None]]] = []
        self._processor_task: Optional[asyncio.Task] = None
        self._started = False

    def enqueue(self, item: QueueItem) -> None:
        """Add an item to the queue."""
        item.created_at = time.time()
        item.state = QueueItemState.PENDING
        self._items[item.id] = item
        self._pending.put_nowait(item)

    def enqueue_many(self, items: list[QueueItem]) -> None:
        for item in items:
            self.enqueue(item)

    def skip(self, item_id: str) -> None:
        """Mark an item as skipped (e.g. downstream-only rerun skip)."""
        item = self._items.get(item_id)
        if item and item.state == QueueItemState.PENDING:
            item.state = QueueItemState.SKIPPED
            item.ended_at = time.time()
            self._skipped_ids.add(item_id)

    async def process(self, handler: Callable[[QueueItem], Awaitable[Any]]) -> None:
        """
        Start the processing loop.

        Creates a single background worker that reads from the pending
        queue and invokes ``handler`` for each ready item.
        Safe to call multiple times — only one worker runs.
        """
        if self._started:
            return
        self._started = True

        async def _worker() -> None:
            while True:
                item = await self._pending.get()
                async with self._semaphore:
                    # Check dependencies — if not met, re-queue with backoff
                    deps_met = all(d in self._completed_ids for d in item.depends_on)
                    if not deps_met:
                        # Check if any dependency has permanently failed
                        failed_deps = [d for d in item.depends_on if d in self._failed_ids]
                        if failed_deps:
                            item.state = QueueItemState.SKIPPED
                            item.error = f"Dependency failed: {failed_deps}"
                            item.ended_at = time.time()
                            self._skipped_ids.add(item.id)
                            await self._notify_listeners(item)
                            self._pending.task_done()
                            continue
                        # Re-queue with exponential backoff
                        backoff = min(0.1 * (2 ** item.retry_count), 1.0)
                        await asyncio.sleep(backoff)
                        item.retry_count += 1
                        self._pending.put_nowait(item)
                        self._pending.task_done()
                        continue

                    item.state = QueueItemState.RUNNING
                    item.started_at = time.time()
                    self._running_count += 1
                    await self._notify_listeners(item)

                    try:
                        result = await handler(item)
                        item.state = QueueItemState.COMPLETED
                        item.result = result
                        item.ended_at = time.time()
                        self._completed_ids.add(item.id)
                    except Exception as e:
                        if item.retry_count < item.max_retries:
                            item.retry_count += 1
                            item.state = QueueItemState.PENDING
                            backoff = min(0.5 * (2 ** item.retry_count), 5.0)
                            await asyncio.sleep(backoff)
                            self._pending.put_nowait(item)
                        else:
                            item.state = QueueItemState.FAILED
                            item.error = str(e)
                            item.ended_at = time.time()
                            self._failed_ids.add(item.id)
                    finally:
                        self._running_count -= 1
                        await self._notify_listeners(item)
                        self._pending.task_done()

        self._processor_task = asyncio.create_task(_worker())

    async def cancel(self, item_id: str) -> None:
        item = self._items.get(item_id)
        if item and item.state == QueueItemState.PENDING:
            item.state = QueueItemState.CANCELLED
            item.ended_at = time.time()

    async def wait_all(self) -> None:
        if self._processor_task is not None:
            await self._pending.join()

    def state(self) -> QueueState:
        return QueueState(
            pending=sum(1 for i in self._items.values() if i.state == QueueItemState.PENDING),
            running=self._running_count,
            completed=len(self._completed_ids),
            failed=len(self._failed_ids),
            skipped=len(self._skipped_ids),
            total=len(self._items),
        )

    def items(self) -> list[QueueItem]:
        return list(self._items.values())

    def item(self, item_id: str) -> Optional[QueueItem]:
        return self._items.get(item_id)

    def subscribe(self, listener: Callable[[QueueItem], Awaitable[None]]) -> None:
        self._listeners.append(listener)

    async def _notify_listeners(self, item: QueueItem) -> None:
        for listener in self._listeners:
            try:
                await listener(item)
            except Exception:
                pass

    def clear(self) -> None:
        self._items.clear()
        self._completed_ids.clear()
        self._failed_ids.clear()
        self._skipped_ids.clear()
        self._processor_task = None
        self._started = False