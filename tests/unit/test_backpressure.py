"""Unit tests for backpressure management."""

import pytest

from flowlens.common.config import IngestionSettings
from flowlens.ingestion.backpressure import BackpressureQueue, BackpressureState


class TestBackpressureQueue:
    """Test cases for BackpressureQueue."""

    @pytest.fixture
    def settings(self) -> IngestionSettings:
        """Create test settings with small thresholds."""
        return IngestionSettings(
            queue_max_size=100,
            sample_threshold=50,
            drop_threshold=80,
            sample_rate=2,
        )

    @pytest.fixture
    def queue(self, settings: IngestionSettings) -> BackpressureQueue[int]:
        """Create queue with test settings."""
        return BackpressureQueue(settings)

    @pytest.mark.asyncio
    async def test_initial_state(self, queue: BackpressureQueue[int]):
        """Test queue starts in normal state."""
        assert queue.state == BackpressureState.NORMAL
        assert queue.size == 0

    @pytest.mark.asyncio
    async def test_put_success(self, queue: BackpressureQueue[int]):
        """Test putting items in normal state."""
        result = await queue.put(1)
        assert result is True
        assert queue.size == 1

    @pytest.mark.asyncio
    async def test_get_item(self, queue: BackpressureQueue[int]):
        """Test getting items from queue."""
        await queue.put(42)
        item = await queue.get()
        assert item == 42
        assert queue.size == 0

    @pytest.mark.asyncio
    async def test_get_batch(self, queue: BackpressureQueue[int]):
        """Test getting batch of items."""
        for i in range(10):
            await queue.put(i)

        batch = await queue.get_batch(max_items=5, timeout=0.1)
        assert len(batch) == 5
        assert batch == [0, 1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_sampling_state(self, queue: BackpressureQueue[int]):
        """Test queue enters sampling state at threshold."""
        # Fill queue to sampling threshold
        for i in range(55):
            await queue.put(i)

        assert queue.state == BackpressureState.SAMPLING

    @pytest.mark.asyncio
    async def test_sampling_behavior(self, queue: BackpressureQueue[int]):
        """Test sampling drops every Nth item."""
        # Fill to sampling threshold
        for i in range(55):
            await queue.put(i)

        initial_size = queue.size
        stats_before = queue.stats

        # Add more items - some should be sampled
        for i in range(10):
            await queue.put(100 + i)

        stats_after = queue.stats

        # With sample_rate=2, about half should be sampled
        assert stats_after.total_sampled > stats_before.total_sampled

    @pytest.mark.asyncio
    async def test_dropping_state(self, queue: BackpressureQueue[int]):
        """Test queue enters dropping state at high utilization."""
        # Fill queue past drop threshold
        for i in range(85):
            await queue.put(i)

        assert queue.state == BackpressureState.DROPPING

    @pytest.mark.asyncio
    async def test_dropping_behavior(self, queue: BackpressureQueue[int]):
        """Test items are dropped in dropping state."""
        # Fill past drop threshold
        for i in range(85):
            await queue.put(i)

        stats_before = queue.stats

        # Try to add more - should be dropped
        result = await queue.put(999)
        assert result is False

        stats_after = queue.stats
        assert stats_after.total_dropped > stats_before.total_dropped

    @pytest.mark.asyncio
    async def test_state_recovery(self, queue: BackpressureQueue[int]):
        """Test queue recovers to normal state."""
        # Fill to dropping state
        for i in range(85):
            await queue.put(i)
        assert queue.state == BackpressureState.DROPPING

        # Drain the queue
        while queue.size > 0:
            await queue.get_batch(max_items=100, timeout=0.1)

        assert queue.state == BackpressureState.NORMAL

    @pytest.mark.asyncio
    async def test_put_batch(self, queue: BackpressureQueue[int]):
        """Test putting batch of items."""
        items = list(range(10))
        added, dropped = await queue.put_batch(items)

        assert added == 10
        assert dropped == 0
        assert queue.size == 10

    @pytest.mark.asyncio
    async def test_stats(self, queue: BackpressureQueue[int]):
        """Test statistics tracking."""
        for i in range(5):
            await queue.put(i)

        stats = queue.stats
        assert stats.queue_size == 5
        assert stats.queue_max_size == 100
        assert stats.total_received == 5
        assert stats.queue_utilization == 5.0

    @pytest.mark.asyncio
    async def test_get_nowait_empty(self, queue: BackpressureQueue[int]):
        """Test get_nowait on empty queue."""
        result = queue.get_nowait()
        assert result is None

    @pytest.mark.asyncio
    async def test_get_nowait_with_item(self, queue: BackpressureQueue[int]):
        """Test get_nowait with available item."""
        await queue.put(42)
        result = queue.get_nowait()
        assert result == 42
