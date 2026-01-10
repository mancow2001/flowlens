"""Model manager for ML classification.

Handles model persistence, versioning, and rollback to shipped model.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from flowlens.classification.ml.classifier import MLClassifier
from flowlens.common.config import get_settings
from flowlens.common.logging import get_logger

logger = get_logger(__name__)


# Path to shipped model bundled with the package
SHIPPED_MODEL_PATH = Path(__file__).parent / "models" / "shipped_model.joblib"


@dataclass
class ModelInfo:
    """Information about a model version."""

    id: str
    version: str
    algorithm: str
    model_type: str  # 'shipped' or 'custom'
    is_active: bool
    created_at: datetime
    training_samples: int
    accuracy: float
    f1_score: float | None
    model_path: str
    file_size_bytes: int | None
    notes: str | None


@dataclass
class TrainingStats:
    """Statistics from model training."""

    training_samples: int
    accuracy: float
    f1_score: float | None = None
    class_distribution: dict[str, int] | None = None
    feature_importances: dict[str, float] | None = None
    confusion_matrix: list[list[int]] | None = None


class ModelManager:
    """Manage ML model persistence and versioning.

    Handles:
    - Loading shipped model (bundled with package)
    - Saving/loading custom models (user-trained)
    - Switching between models
    - Rollback to shipped model
    """

    def __init__(
        self,
        storage_path: Path | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        """Initialize the model manager.

        Args:
            storage_path: Path for custom model storage.
            db: Database session for registry operations.
        """
        settings = get_settings().ml_classification
        self.storage_path = storage_path or settings.model_storage_path
        self.db = db

    def _ensure_storage_dir(self) -> None:
        """Ensure storage directory exists (lazy creation)."""
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def get_shipped_model_path(self) -> Path:
        """Get path to the shipped model.

        Returns:
            Path to shipped model file.
        """
        return SHIPPED_MODEL_PATH

    def shipped_model_exists(self) -> bool:
        """Check if shipped model exists.

        Returns:
            True if shipped model file exists.
        """
        return SHIPPED_MODEL_PATH.exists()

    def load_shipped_model(self) -> MLClassifier:
        """Load the shipped (bundled) model.

        Returns:
            Loaded MLClassifier instance.

        Raises:
            FileNotFoundError: If shipped model doesn't exist.
        """
        if not self.shipped_model_exists():
            raise FileNotFoundError(
                f"Shipped model not found at {SHIPPED_MODEL_PATH}. "
                "The package may not include a pre-built model yet."
            )

        classifier = MLClassifier.load(SHIPPED_MODEL_PATH)
        classifier.model_version = "shipped"
        logger.info("Loaded shipped model")
        return classifier

    async def load_active_model(self) -> MLClassifier:
        """Load the currently active model.

        First checks for an active custom model in the registry.
        Falls back to shipped model if no custom model is active.

        Returns:
            Loaded MLClassifier instance.

        Raises:
            FileNotFoundError: If no model is available.
        """
        # Try to load active custom model from registry
        if self.db:
            active_model = await self._get_active_model_info()
            if active_model and active_model.model_type == "custom":
                model_path = Path(active_model.model_path)
                if model_path.exists():
                    classifier = MLClassifier.load(model_path)
                    classifier.model_version = active_model.version
                    logger.info(
                        "Loaded active custom model",
                        version=active_model.version,
                    )
                    return classifier
                else:
                    logger.warning(
                        "Active custom model file missing, falling back to shipped",
                        path=str(model_path),
                    )

        # Fall back to shipped model
        return self.load_shipped_model()

    async def save_model(
        self,
        classifier: MLClassifier,
        stats: TrainingStats,
        notes: str | None = None,
    ) -> str:
        """Save a trained model and register it.

        Args:
            classifier: Trained classifier to save.
            stats: Training statistics.
            notes: Optional notes about the model.

        Returns:
            Version string for the saved model.
        """
        # Ensure storage directory exists
        self._ensure_storage_dir()

        # Generate version string
        version = f"custom-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"

        # Save model file
        model_path = self.storage_path / f"{version}.joblib"
        classifier.model_version = version
        classifier.save(model_path)

        # Calculate file hash and size
        file_size = model_path.stat().st_size
        checksum = self._calculate_checksum(model_path)

        # Register in database
        if self.db:
            await self._register_model(
                version=version,
                algorithm=classifier.algorithm or "unknown",
                model_type="custom",
                stats=stats,
                model_path=str(model_path),
                file_size_bytes=file_size,
                checksum=checksum,
                notes=notes,
            )

            # Activate the new model
            await self.activate_model(version)

        logger.info(
            "Model saved and activated",
            version=version,
            accuracy=stats.accuracy,
            samples=stats.training_samples,
        )

        return version

    async def activate_model(self, version: str) -> None:
        """Activate a specific model version.

        Args:
            version: Version string to activate.

        Raises:
            ValueError: If version doesn't exist.
        """
        if not self.db:
            logger.warning("No database session, cannot activate model")
            return

        # Import here to avoid circular imports
        from flowlens.models.ml import MLModelRegistry

        # Deactivate all models
        await self.db.execute(
            update(MLModelRegistry).values(is_active=False)
        )

        # Activate the specified version
        result = await self.db.execute(
            update(MLModelRegistry)
            .where(MLModelRegistry.version == version)
            .values(is_active=True)
        )

        if result.rowcount == 0:  # type: ignore[attr-defined]
            raise ValueError(f"Model version not found: {version}")

        await self.db.commit()
        logger.info("Activated model", version=version)

    async def reset_to_shipped(self) -> None:
        """Reset to shipped model (deactivate all custom models).

        This effectively makes the system use the shipped model
        since no custom model will be active.
        """
        if not self.db:
            logger.warning("No database session, cannot reset")
            return

        from flowlens.models.ml import MLModelRegistry

        # Deactivate all models
        await self.db.execute(
            update(MLModelRegistry).values(is_active=False)
        )
        await self.db.commit()

        logger.info("Reset to shipped model")

    async def list_models(self) -> list[ModelInfo]:
        """List all available models (shipped + custom).

        Returns:
            List of ModelInfo objects.
        """
        models = []

        # Add shipped model if it exists
        if self.shipped_model_exists():
            models.append(
                ModelInfo(
                    id="shipped",
                    version="shipped",
                    algorithm="random_forest",  # Default for shipped
                    model_type="shipped",
                    is_active=not await self._has_active_custom_model(),
                    created_at=datetime.fromtimestamp(
                        SHIPPED_MODEL_PATH.stat().st_mtime,
                        tz=UTC,
                    ),
                    training_samples=0,  # Unknown for shipped
                    accuracy=0.0,  # Unknown for shipped
                    f1_score=None,
                    model_path=str(SHIPPED_MODEL_PATH),
                    file_size_bytes=SHIPPED_MODEL_PATH.stat().st_size,
                    notes="Pre-built model shipped with FlowLens",
                )
            )

        # Add custom models from registry
        if self.db:
            from flowlens.models.ml import MLModelRegistry

            result = await self.db.execute(
                select(MLModelRegistry).order_by(MLModelRegistry.created_at.desc())
            )
            for row in result.scalars():
                models.append(
                    ModelInfo(
                        id=str(row.id),
                        version=row.version,
                        algorithm=row.algorithm,
                        model_type=row.model_type,
                        is_active=row.is_active,
                        created_at=row.created_at,
                        training_samples=row.training_samples,
                        accuracy=row.accuracy,
                        f1_score=row.f1_score,
                        model_path=row.model_path,
                        file_size_bytes=row.file_size_bytes,
                        notes=row.notes,
                    )
                )

        return models

    async def get_model_info(self, version: str) -> ModelInfo | None:
        """Get info for a specific model version.

        Args:
            version: Version string.

        Returns:
            ModelInfo if found, None otherwise.
        """
        if version == "shipped":
            if not self.shipped_model_exists():
                return None
            return ModelInfo(
                id="shipped",
                version="shipped",
                algorithm="random_forest",
                model_type="shipped",
                is_active=not await self._has_active_custom_model(),
                created_at=datetime.fromtimestamp(
                    SHIPPED_MODEL_PATH.stat().st_mtime,
                    tz=UTC,
                ),
                training_samples=0,
                accuracy=0.0,
                f1_score=None,
                model_path=str(SHIPPED_MODEL_PATH),
                file_size_bytes=SHIPPED_MODEL_PATH.stat().st_size,
                notes="Pre-built model shipped with FlowLens",
            )

        if not self.db:
            return None

        from flowlens.models.ml import MLModelRegistry

        result = await self.db.execute(
            select(MLModelRegistry).where(MLModelRegistry.version == version)
        )
        row = result.scalar_one_or_none()
        if not row:
            return None

        return ModelInfo(
            id=str(row.id),
            version=row.version,
            algorithm=row.algorithm,
            model_type=row.model_type,
            is_active=row.is_active,
            created_at=row.created_at,
            training_samples=row.training_samples,
            accuracy=row.accuracy,
            f1_score=row.f1_score,
            model_path=row.model_path,
            file_size_bytes=row.file_size_bytes,
            notes=row.notes,
        )

    async def _get_active_model_info(self) -> ModelInfo | None:
        """Get info for the currently active model."""
        if not self.db:
            return None

        from flowlens.models.ml import MLModelRegistry

        result = await self.db.execute(
            select(MLModelRegistry).where(MLModelRegistry.is_active == True)  # noqa: E712
        )
        row = result.scalar_one_or_none()
        if not row:
            return None

        return ModelInfo(
            id=str(row.id),
            version=row.version,
            algorithm=row.algorithm,
            model_type=row.model_type,
            is_active=row.is_active,
            created_at=row.created_at,
            training_samples=row.training_samples,
            accuracy=row.accuracy,
            f1_score=row.f1_score,
            model_path=row.model_path,
            file_size_bytes=row.file_size_bytes,
            notes=row.notes,
        )

    async def _has_active_custom_model(self) -> bool:
        """Check if there's an active custom model."""
        if not self.db:
            return False

        from flowlens.models.ml import MLModelRegistry

        result = await self.db.execute(
            select(MLModelRegistry.id).where(
                MLModelRegistry.is_active == True,  # noqa: E712
                MLModelRegistry.model_type == "custom",
            )
        )
        return result.scalar_one_or_none() is not None

    async def _register_model(
        self,
        version: str,
        algorithm: str,
        model_type: str,
        stats: TrainingStats,
        model_path: str,
        file_size_bytes: int,
        checksum: str,
        notes: str | None,
    ) -> None:
        """Register a model in the database."""
        assert self.db is not None, "_register_model should only be called when db is set"

        from flowlens.models.ml import MLModelRegistry

        model_entry = MLModelRegistry(
            id=uuid4(),
            version=version,
            algorithm=algorithm,
            model_type=model_type,
            is_active=False,
            training_samples=stats.training_samples,
            accuracy=stats.accuracy,
            f1_score=stats.f1_score,
            class_distribution=stats.class_distribution,
            feature_importances=stats.feature_importances,
            confusion_matrix=stats.confusion_matrix,
            model_path=model_path,
            file_size_bytes=file_size_bytes,
            checksum=checksum,
            notes=notes,
        )

        self.db.add(model_entry)
        await self.db.flush()

    @staticmethod
    def _calculate_checksum(path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256 = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
