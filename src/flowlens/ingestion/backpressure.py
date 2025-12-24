"""Backpressure management for flow ingestion.

Implements queue-based backpressure with sampling and dropping
strategies to handle traffic spikes.
"""

import asyncio
import random
from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from flowlens.common.config import IngestionSettings
from flowlens.common.logging import get_logger
from flowlens.common.metrics import (
    FLOWS_DROPPED,
    FLOWS_SAMPLED,
    INGESTION_QUEUE_SIZE,
)

logger = get_logger(__name__)

T = TypeVar("T")


class BackpressureState(str, Enum):
    """Current backpressure state."""

    NORMAL = "normal"
    SAMPLING = "sampling"
    DROPPING = "dropping"


@dataclass
class BackpressureStats:
    """Statistics about backpressure handling."""

    state: BackpressureState
    queue_size: int
    queue_max_size: int
    total_received: int
    total_sampled: int
    total_dropped: int
    sample_rate: int

    @property
    def queue_utilization(self) -> float:
        """Queue utilization as percentage."""
        return (self.queue_size / self.queue_max_size) * 100


class BackpressureQueue(Generic[T]):
    """Queue with backpressure support.

    Implements a bounded queue that applies sampling or dropping
    when queue utilization exceeds configured thresholds.

    Thresholds (from SCALING_MODEL.md):
    - Normal: queue < sample_threshold
    - Sampling: sample_threshold <= queue < drop_threshold
    - Dropping: queue >= drop_threshold
    """

    def __init__(self, settings: IngestionSettings | None = None) -> None:
        """Initialize backpressure queue.

        Args:
            settings: Ingestion settings. Uses defaults if not provided.
        """
        if settings is None:
            from flowlens.common.config import get_settings
            settings = get_settings().ingestion

        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=settings.queue_max_size)
        self._max_size = settings.queue_max_size
        self._sample_threshold = settings.sample_threshold
        self._drop_threshold = settings.drop_threshold
        self._sample_rate = settings.sample_rate

        # Counters
        self._total_received = 0
        self._total_sampled = 0
        self._total_dropped = 0
        self._sample_counter = 0

        # State
        self._state = BackpressureState.NORMAL

    @property
    def state(self) -> BackpressureState:
        """Current backpressure state."""
        return self._state

    @property
    def size(self) -> int:
        """Current queue size."""
        return self._queue.qsize()

    @property
    def stats(self) -> BackpressureStats:
        """Get current statistics."""
        return BackpressureStats(
            state=self._state,
            queue_size=self.size,
            queue_max_size=self._max_size,
            total_received=self._total_received,
            total_sampled=self._total_sampled,
            total_dropped=self._total_dropped,
            sample_rate=self._sample_rate,
        )

    def _update_state(self) -> None:
        """Update backpressure state based on queue size."""
        queue_size = self.size
        INGESTION_QUEUE_SIZE.set(queue_size)

        old_state = self._state

        if queue_size >= self._drop_threshold:
            self._state = BackpressureState.DROPPING
        elif queue_size >= self._sample_threshold:
            self._state = BackpressureState.SAMPLING
        else:
            self._state = BackpressureState.NORMAL

        if self._state != old_state:
            logger.warning(
                "Backpressure state changed",
                old_state=old_state.value,
                new_state=self._state.value,
                queue_size=queue_size,
                sample_threshold=self._sample_threshold,
                drop_threshold=self._drop_threshold,
            )

    async def put(self, item: T) -> bool:
        """Add item to queue with backpressure handling.

        Args:
            item: Item to add.

        Returns:
            True if item was added, False if dropped/sampled.
        """
        self._total_received += 1
        self._update_state()

        if self._state == BackpressureState.DROPPING:
            # Drop the item
            self._total_dropped += 1
            FLOWS_DROPPED.labels(reason="backpressure_drop").inc()
            return False

        if self._state == BackpressureState.SAMPLING:
            # Sample: keep 1 in N items
            self._sample_counter += 1
            if self._sample_counter < self._sample_rate:
                self._total_sampled += 1
                FLOWS_SAMPLED.inc()
                return False
            self._sample_counter = 0

        try:
            self._queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            self._total_dropped += 1
            FLOWS_DROPPED.labels(reason="queue_full").inc()
            return False

    async def put_batch(self, items: list[T]) -> tuple[int, int]:
        """Add batch of items with backpressure handling.

        Args:
            items: List of items to add.

        Returns:
            Tuple of (added_count, dropped_count).
        """
        added = 0
        dropped = 0

        for item in items:
            if await self.put(item):
                added += 1
            else:
                dropped += 1

        return added, dropped

    async def get(self) -> T:
        """Get next item from queue.

        Blocks until an item is available.
        """
        item = await self._queue.get()
        self._update_state()
        return item

    async def get_batch(self, max_items: int, timeout: float = 0.1) -> list[T]:
        """Get batch of items from queue.

        Args:
            max_items: Maximum items to retrieve.
            timeout: Timeout in seconds for first item.

        Returns:
            List of items (may be empty if timeout).
        """
        items: list[T] = []

        try:
            # Wait for first item with timeout
            item = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            items.append(item)

            # Get remaining items without blocking
            while len(items) < max_items:
                try:
                    item = self._queue.get_nowait()
                    items.append(item)
                except asyncio.QueueEmpty:
                    break

        except asyncio.TimeoutError:
            pass

        if items:
            self._update_state()

        return items

    def get_nowait(self) -> T | None:
        """Get item without blocking.

        Returns:
            Item if available, None otherwise.
        """
        try:
            item = self._queue.get_nowait()
            self._update_state()
            return item
        except asyncio.QueueEmpty:
            return None


class AdaptiveBackpressure:
    """Adaptive backpressure that adjusts thresholds based on throughput.

    Monitors processing rate and adjusts sampling/dropping thresholds
    to maintain target throughput.
    """

    def __init__(
        self,
        target_throughput: int = 50000,
        adjustment_interval: float = 10.0,
    ) -> None:
        """Initialize adaptive backpressure.

        Args:
            target_throughput: Target flows per second.
            adjustment_interval: Seconds between adjustments.
        """
        self._target_throughput = target_throughput
        self._adjustment_interval = adjustment_interval

        # Moving average of throughput
        self._throughput_samples: list[float] = []
        self._max_samples = 10

        # Current multiplier for thresholds
        self._threshold_multiplier = 1.0

    def record_throughput(self, flows_per_second: float) -> None:
        """Record throughput sample.

        Args:
            flows_per_second: Current processing rate.
        """
        self._throughput_samples.append(flows_per_second)
        if len(self._throughput_samples) > self._max_samples:
            self._throughput_samples.pop(0)

    @property
    def average_throughput(self) -> float:
        """Get average throughput over recent samples."""
        if not self._throughput_samples:
            return 0.0
        return sum(self._throughput_samples) / len(self._throughput_samples)

    def get_adjusted_thresholds(
        self,
        base_sample_threshold: int,
        base_drop_threshold: int,
    ) -> tuple[int, int]:
        """Get adjusted thresholds based on throughput.

        Args:
            base_sample_threshold: Base sample threshold.
            base_drop_threshold: Base drop threshold.

        Returns:
            Tuple of (adjusted_sample_threshold, adjusted_drop_threshold).
        """
        avg = self.average_throughput

        if avg < 1:
            return base_sample_threshold, base_drop_threshold

        # Adjust multiplier based on how close we are to target
        ratio = avg / self._target_throughput

        if ratio < 0.8:
            # Under target - can be more lenient
            self._threshold_multiplier = min(1.5, self._threshold_multiplier * 1.05)
        elif ratio > 1.2:
            # Over target - need to be more aggressive
            self._threshold_multiplier = max(0.5, self._threshold_multiplier * 0.95)
        else:
            # Close to target - stabilize
            self._threshold_multiplier = 1.0 + (self._threshold_multiplier - 1.0) * 0.9

        return (
            int(base_sample_threshold * self._threshold_multiplier),
            int(base_drop_threshold * self._threshold_multiplier),
        )
