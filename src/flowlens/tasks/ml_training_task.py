"""Background task for ML model training.

Runs ML training asynchronously with progress tracking through the task system.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import select

if TYPE_CHECKING:
    from uuid import UUID

from flowlens.classification.ml.trainer import MLTrainer, TrainingError
from flowlens.common.database import get_session_factory
from flowlens.common.logging import get_logger
from flowlens.models.task import BackgroundTask
from flowlens.tasks.executor import TaskExecutor

logger = get_logger(__name__)


async def run_ml_training_task(
    task_id: UUID,
    algorithm: Literal["random_forest", "xgboost", "gradient_boosting"] = "random_forest",
    notes: str | None = None,
) -> None:
    """Run ML training task with its own database session.

    This function is designed to be run as a background task via
    `run_task_in_background`. It creates its own database session
    to avoid sharing issues with the request session.

    Args:
        task_id: Background task ID for progress tracking.
        algorithm: ML algorithm to use for training.
        notes: Optional notes about this training run.
    """
    session_factory = get_session_factory()

    async with session_factory() as db:
        try:
            executor = TaskExecutor(db)
            trainer = MLTrainer(db=db, task_executor=executor)

            # Run training
            version = await trainer.train_from_confirmed(
                task_id=task_id,
                algorithm=algorithm,
                notes=notes,
            )

            # Mark task as completed
            await executor.complete_task(
                task_id,
                result={
                    "model_version": version,
                    "status": "trained_and_activated",
                    "algorithm": algorithm,
                },
            )
            await db.commit()

            logger.info(
                "ML training task completed",
                task_id=str(task_id),
                version=version,
            )

        except TrainingError as e:
            # Training-specific error (low accuracy, insufficient data, etc.)
            logger.warning(
                "ML training task failed",
                task_id=str(task_id),
                error=str(e),
            )
            try:
                result = await db.execute(
                    select(BackgroundTask).where(BackgroundTask.id == task_id)
                )
                bg_task = result.scalar_one_or_none()
                if bg_task and not bg_task.is_complete:
                    bg_task.fail(
                        str(e),
                        {"error_type": "training_error"},
                    )
                    await db.commit()
            except Exception:
                pass

        except Exception as e:
            # Unexpected error
            logger.exception(
                "ML training task failed unexpectedly",
                task_id=str(task_id),
            )
            try:
                result = await db.execute(
                    select(BackgroundTask).where(BackgroundTask.id == task_id)
                )
                bg_task = result.scalar_one_or_none()
                if bg_task and not bg_task.is_complete:
                    bg_task.fail(
                        str(e),
                        {"error_type": "unexpected_error", "exception": type(e).__name__},
                    )
                    await db.commit()
            except Exception:
                pass
            raise
