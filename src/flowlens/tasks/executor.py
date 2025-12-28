"""Task executor for running background tasks.

Provides async task execution with progress tracking and error handling.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.common.logging import get_logger
from flowlens.models.task import BackgroundTask, TaskStatus

logger = get_logger(__name__)

# Global registry of running tasks
_running_tasks: dict[UUID, asyncio.Task] = {}


class TaskExecutor:
    """Executes background tasks with progress tracking.

    Usage:
        executor = TaskExecutor(db)

        # Create and start a task
        task = await executor.create_task(
            task_type="apply_classification_rules",
            name="Apply classification rules",
            parameters={"force": True},
        )

        # Run the task in background
        await executor.run_in_background(
            task.id,
            my_task_function,
            arg1, arg2,
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize executor.

        Args:
            db: Database session.
        """
        self._db = db

    async def create_task(
        self,
        task_type: str,
        name: str,
        description: str | None = None,
        parameters: dict | None = None,
        triggered_by: str | None = None,
        related_entity_type: str | None = None,
        related_entity_id: UUID | None = None,
    ) -> BackgroundTask:
        """Create a new background task.

        Args:
            task_type: Type of task.
            name: Human-readable task name.
            description: Optional description.
            parameters: Task parameters.
            triggered_by: Who triggered the task.
            related_entity_type: Type of related entity.
            related_entity_id: ID of related entity.

        Returns:
            Created task.
        """
        task = BackgroundTask(
            task_type=task_type,
            name=name,
            description=description,
            parameters=parameters,
            triggered_by=triggered_by,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )

        self._db.add(task)
        await self._db.flush()
        await self._db.refresh(task)

        logger.info(
            "Created background task",
            task_id=str(task.id),
            task_type=task_type,
            name=name,
        )

        return task

    async def get_task(self, task_id: UUID) -> BackgroundTask | None:
        """Get task by ID.

        Args:
            task_id: Task ID.

        Returns:
            Task or None if not found.
        """
        result = await self._db.execute(
            select(BackgroundTask).where(BackgroundTask.id == task_id)
        )
        return result.scalar_one_or_none()

    async def update_task_progress(
        self,
        task_id: UUID,
        processed: int = 0,
        successful: int = 0,
        failed: int = 0,
        skipped: int = 0,
    ) -> None:
        """Update task progress.

        Args:
            task_id: Task ID.
            processed: Items processed in this batch.
            successful: Successful items in this batch.
            failed: Failed items in this batch.
            skipped: Skipped items in this batch.
        """
        task = await self.get_task(task_id)
        if task:
            task.update_progress(processed, successful, failed, skipped)
            await self._db.flush()

    async def start_task(self, task_id: UUID, total_items: int) -> None:
        """Mark task as started.

        Args:
            task_id: Task ID.
            total_items: Total items to process.
        """
        task = await self.get_task(task_id)
        if task:
            task.start(total_items)
            await self._db.flush()

    async def complete_task(self, task_id: UUID, result: dict | None = None) -> None:
        """Mark task as completed.

        Args:
            task_id: Task ID.
            result: Optional result data.
        """
        task = await self.get_task(task_id)
        if task:
            task.complete(result)
            await self._db.flush()

            logger.info(
                "Task completed",
                task_id=str(task_id),
                duration=task.duration_seconds,
                successful=task.successful_items,
                failed=task.failed_items,
            )

    async def fail_task(
        self,
        task_id: UUID,
        error_message: str,
        error_details: dict | None = None,
    ) -> None:
        """Mark task as failed.

        Args:
            task_id: Task ID.
            error_message: Error message.
            error_details: Optional error details.
        """
        task = await self.get_task(task_id)
        if task:
            task.fail(error_message, error_details)
            await self._db.flush()

            logger.error(
                "Task failed",
                task_id=str(task_id),
                error=error_message,
            )

    async def cancel_task(self, task_id: UUID) -> bool:
        """Cancel a running task.

        Args:
            task_id: Task ID.

        Returns:
            True if cancelled, False if not running.
        """
        # Cancel the asyncio task if running
        if task_id in _running_tasks:
            _running_tasks[task_id].cancel()
            del _running_tasks[task_id]

        task = await self.get_task(task_id)
        if task and not task.is_complete:
            task.cancel()
            await self._db.flush()
            logger.info("Task cancelled", task_id=str(task_id))
            return True

        return False


def run_task_in_background(
    task_id: UUID,
    coro: Coroutine[Any, Any, Any],
) -> asyncio.Task:
    """Run a task coroutine in the background.

    Args:
        task_id: Task ID for tracking.
        coro: Coroutine to run.

    Returns:
        Asyncio task.
    """
    async def wrapper():
        try:
            await coro
        finally:
            # Clean up from running tasks
            _running_tasks.pop(task_id, None)

    asyncio_task = asyncio.create_task(wrapper())
    _running_tasks[task_id] = asyncio_task

    return asyncio_task


def is_task_running(task_id: UUID) -> bool:
    """Check if a task is currently running.

    Args:
        task_id: Task ID.

    Returns:
        True if running.
    """
    return task_id in _running_tasks
