"""ML classification Pydantic schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class TrainModelRequest(BaseModel):
    """Request to start ML model training."""

    algorithm: Literal["random_forest", "xgboost", "gradient_boosting"] = Field(
        default="random_forest",
        description="ML algorithm to use for training",
    )
    notes: str | None = Field(
        default=None,
        description="Optional notes about this training run",
    )


class TrainModelResponse(BaseModel):
    """Response after starting ML training."""

    task_id: str
    message: str


class ModelInfoResponse(BaseModel):
    """Information about an ML model."""

    id: str
    version: str
    algorithm: str
    model_type: Literal["shipped", "custom"]
    is_active: bool
    created_at: datetime
    training_samples: int
    accuracy: float
    f1_score: float | None = None
    file_size_bytes: int | None = None
    notes: str | None = None


class ModelListResponse(BaseModel):
    """List of all available models."""

    models: list[ModelInfoResponse]
    active_version: str | None


class MLStatusResponse(BaseModel):
    """Current ML classification status."""

    ml_enabled: bool
    ml_available: bool
    model_version: str | None = None
    model_classes: list[str]
    ml_confidence_threshold: float
    ml_min_flows: int
    heuristic_min_flows: int
    initialized: bool


class ResetModelResponse(BaseModel):
    """Response after resetting to shipped model."""

    message: str
    active_version: str


class ActivateModelResponse(BaseModel):
    """Response after activating a model version."""

    message: str
    version: str


class TrainingDataStatsResponse(BaseModel):
    """Statistics about available training data."""

    total_confirmed_assets: int
    class_distribution: dict[str, int]
    meets_minimum_requirements: bool
    minimum_samples_required: int
    minimum_per_class_required: int
    classes_below_minimum: list[str]
