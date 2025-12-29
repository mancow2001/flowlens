"""Background tasks API endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from flowlens.api.dependencies import AdminUser, AnalystUser, DbSession, Pagination, ViewerUser
from flowlens.common.logging import get_logger
from flowlens.models.task import BackgroundTask, TaskStatus, TaskType
from flowlens.schemas.task import (
    ApplyRulesTaskCreate,
    TaskList,
    TaskResponse,
    TaskSummary,
)
from flowlens.tasks.executor import TaskExecutor, run_task_in_background, run_classification_task_with_new_session

logger = get_logger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=TaskList)
async def list_tasks(
    db: DbSession,
    _user: ViewerUser,
    pagination: Pagination,
    status_filter: str | None = Query(None, alias="status"),
    task_type: str | None = Query(None, alias="taskType"),
) -> TaskList:
    """List background tasks with filtering and pagination."""
    query = select(BackgroundTask)

    # Apply filters
    if status_filter:
        query = query.where(BackgroundTask.status == status_filter)
    if task_type:
        query = query.where(BackgroundTask.task_type == task_type)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Order by created_at descending (newest first)
    query = query.order_by(BackgroundTask.created_at.desc())

    # Apply pagination
    query = query.offset(pagination.offset).limit(pagination.page_size)

    result = await db.execute(query)
    tasks = result.scalars().all()

    items = [
        TaskSummary(
            id=t.id,
            task_type=t.task_type,
            name=t.name,
            status=t.status,
            progress_percent=t.progress_percent,
            total_items=t.total_items,
            processed_items=t.processed_items,
            successful_items=t.successful_items,
            failed_items=t.failed_items,
            skipped_items=t.skipped_items,
            started_at=t.started_at,
            completed_at=t.completed_at,
            created_at=t.created_at,
        )
        for t in tasks
    ]

    return TaskList(
        items=items,
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: UUID,
    db: DbSession,
    _user: ViewerUser,
) -> TaskResponse:
    """Get task by ID."""
    result = await db.execute(
        select(BackgroundTask).where(BackgroundTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    return TaskResponse(
        id=task.id,
        task_type=task.task_type,
        name=task.name,
        description=task.description,
        status=task.status,
        progress_percent=task.progress_percent,
        total_items=task.total_items,
        processed_items=task.processed_items,
        successful_items=task.successful_items,
        failed_items=task.failed_items,
        skipped_items=task.skipped_items,
        started_at=task.started_at,
        completed_at=task.completed_at,
        duration_seconds=task.duration_seconds,
        parameters=task.parameters,
        result=task.result,
        error_message=task.error_message,
        error_details=task.error_details,
        triggered_by=task.triggered_by,
        related_entity_type=task.related_entity_type,
        related_entity_id=task.related_entity_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    task_id: UUID,
    db: DbSession,
    _user: AnalystUser,
) -> TaskResponse:
    """Cancel a running task."""
    executor = TaskExecutor(db)
    cancelled = await executor.cancel_task(task_id)

    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is not running or already completed",
        )

    await db.commit()

    # Return updated task
    return await get_task(task_id, db, _user)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: UUID,
    db: DbSession,
    _user: AdminUser,
) -> None:
    """Delete a completed task."""
    result = await db.execute(
        select(BackgroundTask).where(BackgroundTask.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    if not task.is_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a running task. Cancel it first.",
        )

    await db.delete(task)
    await db.commit()


@router.post("/apply-classification-rules", response_model=TaskResponse)
async def create_apply_classification_rules_task(
    data: ApplyRulesTaskCreate,
    db: DbSession,
    _user: AnalystUser,
) -> TaskResponse:
    """Create a task to apply classification rules to assets.

    This runs in the background and processes assets in batches.
    You can monitor progress by polling the task endpoint.
    """
    executor = TaskExecutor(db)

    # Create the task
    task = await executor.create_task(
        task_type=TaskType.APPLY_CLASSIFICATION_RULES.value,
        name="Apply Classification Rules",
        description="Applying CIDR classification rules to all assets",
        parameters={
            "force": data.force,
            "rule_id": str(data.rule_id) if data.rule_id else None,
        },
        triggered_by="api",
    )

    await db.commit()

    # Run task in background with its own session
    run_task_in_background(
        task.id,
        run_classification_task_with_new_session(task.id, data.force, data.rule_id),
    )

    logger.info(
        "Started classification rules task",
        task_id=str(task.id),
        force=data.force,
    )

    return await get_task(task.id, db, _user)


@router.get("/running/count", response_model=dict)
async def get_running_task_count(
    db: DbSession,
    _user: ViewerUser,
) -> dict:
    """Get count of running tasks."""
    result = await db.execute(
        select(func.count()).where(
            BackgroundTask.status.in_([
                TaskStatus.PENDING.value,
                TaskStatus.RUNNING.value,
            ])
        )
    )
    count = result.scalar() or 0

    return {"running": count}
