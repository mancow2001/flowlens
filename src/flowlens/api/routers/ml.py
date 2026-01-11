"""ML classification API endpoints.

Provides endpoints for ML model training, management, and status.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from flowlens.api.dependencies import AdminUser, DbSession, ViewerUser
from flowlens.classification.ml.hybrid_engine import HybridClassificationEngine
from flowlens.classification.ml.model_manager import ModelManager
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger
from flowlens.models.asset import Asset
from flowlens.models.task import TaskType
from flowlens.schemas.ml import (
    ActivateModelResponse,
    MLStatusResponse,
    ModelInfoResponse,
    ModelListResponse,
    ResetModelResponse,
    TrainingDataStatsResponse,
    TrainModelRequest,
    TrainModelResponse,
)
from flowlens.tasks.executor import TaskExecutor, run_task_in_background
from flowlens.tasks.ml_training_task import run_ml_training_task

logger = get_logger(__name__)

router = APIRouter(prefix="/ml", tags=["ML Classification"])


@router.get("/status", response_model=MLStatusResponse)
async def get_ml_status(
    db: DbSession,
    _user: ViewerUser,
) -> MLStatusResponse:
    """Get current ML classification status.

    Returns information about whether ML is enabled, the active model,
    and classification thresholds.
    """
    engine = HybridClassificationEngine(db=db)
    await engine.initialize()

    status_info = engine.get_status()

    return MLStatusResponse(
        ml_enabled=status_info["ml_enabled"],
        ml_available=status_info["ml_available"],
        model_version=status_info["model_version"],
        model_classes=status_info["model_classes"],
        ml_confidence_threshold=status_info["ml_confidence_threshold"],
        ml_min_flows=status_info["ml_min_flows"],
        heuristic_min_flows=status_info["heuristic_min_flows"],
        initialized=status_info["initialized"],
    )


@router.get("/models", response_model=ModelListResponse)
async def list_models(
    db: DbSession,
    _user: ViewerUser,
) -> ModelListResponse:
    """List all available ML models.

    Returns both the shipped model and any custom-trained models.
    """
    model_manager = ModelManager(db=db)
    models = await model_manager.list_models()

    active_version = None
    model_responses = []

    for model in models:
        if model.is_active:
            active_version = model.version

        model_responses.append(
            ModelInfoResponse(
                id=model.id,
                version=model.version,
                algorithm=model.algorithm,
                model_type=model.model_type,  # type: ignore[arg-type]
                is_active=model.is_active,
                created_at=model.created_at,
                training_samples=model.training_samples,
                accuracy=model.accuracy,
                f1_score=model.f1_score,
                file_size_bytes=model.file_size_bytes,
                notes=model.notes,
            )
        )

    return ModelListResponse(
        models=model_responses,
        active_version=active_version,
    )


@router.get("/models/{version}", response_model=ModelInfoResponse)
async def get_model(
    version: str,
    db: DbSession,
    _user: ViewerUser,
) -> ModelInfoResponse:
    """Get details for a specific model version."""
    model_manager = ModelManager(db=db)
    model = await model_manager.get_model_info(version)

    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model version '{version}' not found",
        )

    return ModelInfoResponse(
        id=model.id,
        version=model.version,
        algorithm=model.algorithm,
        model_type=model.model_type,  # type: ignore[arg-type]
        is_active=model.is_active,
        created_at=model.created_at,
        training_samples=model.training_samples,
        accuracy=model.accuracy,
        f1_score=model.f1_score,
        file_size_bytes=model.file_size_bytes,
        notes=model.notes,
    )


@router.post("/models/{version}/activate", response_model=ActivateModelResponse)
async def activate_model(
    version: str,
    db: DbSession,
    _user: AdminUser,
) -> ActivateModelResponse:
    """Activate a specific model version.

    Only one model can be active at a time. The active model is used
    for all ML classifications.
    """
    model_manager = ModelManager(db=db)

    # Check model exists
    model = await model_manager.get_model_info(version)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model version '{version}' not found",
        )

    # Cannot activate shipped model via this endpoint
    if version == "shipped":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use POST /ml/models/reset to activate the shipped model",
        )

    try:
        await model_manager.activate_model(version)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    logger.info("Model activated via API", version=version)

    return ActivateModelResponse(
        message=f"Model '{version}' is now active",
        version=version,
    )


@router.post("/models/reset", response_model=ResetModelResponse)
async def reset_to_shipped(
    db: DbSession,
    _user: AdminUser,
) -> ResetModelResponse:
    """Reset to the shipped (bundled) model.

    Deactivates all custom models and reverts to using the
    pre-trained model shipped with FlowLens.
    """
    model_manager = ModelManager(db=db)

    if not model_manager.shipped_model_exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipped model not found. The package may not include a pre-built model.",
        )

    await model_manager.reset_to_shipped()

    logger.info("Reset to shipped model via API")

    return ResetModelResponse(
        message="Reset to shipped model",
        active_version="shipped",
    )


@router.get("/training/stats", response_model=TrainingDataStatsResponse)
async def get_training_data_stats(
    db: DbSession,
    _user: ViewerUser,
) -> TrainingDataStatsResponse:
    """Get statistics about available training data.

    Shows how many confirmed assets are available for training
    and whether the minimum requirements are met.
    """
    settings = get_settings().ml_classification

    # Query confirmed assets
    query = select(Asset.asset_type, func.count(Asset.id).label("count")).where(
        Asset.deleted_at.is_(None),
        Asset.is_internal == True,  # noqa: E712
        Asset.asset_type != "unknown",
        (Asset.classification_locked == True)  # noqa: E712
        | (Asset.classification_method == "manual"),
    ).group_by(Asset.asset_type)

    result = await db.execute(query)
    rows = result.all()

    class_distribution: dict[str, int] = {}
    for row in rows:
        asset_type = str(row[0])  # asset_type
        count = int(row[1])  # count from func.count
        class_distribution[asset_type] = count
    total = sum(class_distribution.values())

    # Check minimum requirements
    min_samples = settings.min_training_samples
    min_per_class = settings.min_samples_per_class

    classes_below_minimum = [
        name for name, count in class_distribution.items()
        if count < min_per_class
    ]

    meets_requirements = (
        total >= min_samples
        and len(classes_below_minimum) == 0
    )

    return TrainingDataStatsResponse(
        total_confirmed_assets=total,
        class_distribution=class_distribution,
        meets_minimum_requirements=meets_requirements,
        minimum_samples_required=min_samples,
        minimum_per_class_required=min_per_class,
        classes_below_minimum=classes_below_minimum,
    )


@router.post("/train", response_model=TrainModelResponse)
async def start_training(
    request: TrainModelRequest,
    db: DbSession,
    _user: AdminUser,
) -> TrainModelResponse:
    """Start ML model training from confirmed classifications.

    Trains a new model using assets that have been confirmed by users
    (classification_locked=True or classification_method='manual').

    The training runs as a background task. Use the tasks API to
    monitor progress and check for completion.

    Requires admin role.
    """
    executor = TaskExecutor(db)

    # Create the background task
    task = await executor.create_task(
        task_type=TaskType.TRAIN_ML_MODEL.value,
        name="Train ML Classification Model",
        description=f"Training {request.algorithm} model from confirmed classifications",
        parameters={
            "algorithm": request.algorithm,
            "notes": request.notes,
        },
        triggered_by="api",
    )

    await db.commit()

    # Run task in background with its own session
    run_task_in_background(
        task.id,
        run_ml_training_task(task.id, request.algorithm, request.notes),
    )

    logger.info(
        "Started ML training task",
        task_id=str(task.id),
        algorithm=request.algorithm,
    )

    return TrainModelResponse(
        task_id=str(task.id),
        message=f"Training started. Monitor progress at /api/v1/tasks/{task.id}",
    )
